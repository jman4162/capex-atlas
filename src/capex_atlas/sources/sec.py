"""SEC EDGAR access.

Two endpoints carry most of the work: ``submissions`` for filing metadata and
``companyfacts`` for XBRL-tagged statement items. Full instance-document parsing
via Arelle comes later, when dimensions and extension taxonomies matter.

Everything fetched lands in the raw store before anything reads it, so an
analysis can be rebuilt offline from bytes whose hashes are recorded.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, Self

import httpx

from capex_atlas.schemas.source import SourceKind
from capex_atlas.sources.rate_limit import DEFAULT_REQUESTS_PER_SECOND, TokenBucket
from capex_atlas.sources.raw import RawArtifact, RawStore

DATA_HOST = "https://data.sec.gov"
WWW_HOST = "https://www.sec.gov"
TICKER_INDEX_URL = f"{WWW_HOST}/files/company_tickers.json"
USER_AGENT_ENV = "CAPEX_ATLAS_SEC_USER_AGENT"
PARSER_VERSION = "sec-json/1"

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4


class OfflineError(RuntimeError):
    """Asked to reach SEC while offline, with no usable cached copy."""


def _versioned(name: str, content: bytes) -> str:
    """``companyfacts.json`` becomes ``companyfacts-2430f1a2ad29.json``.

    Named by content rather than by clock. A timestamp to the second collides
    when a script refetches twice quickly, and the store rejects changed bytes at
    an existing path, so the collision would surface as a hard error. Hashing
    also makes an unchanged refetch land on the copy it matches instead of
    accumulating identical files.
    """
    base, _, suffix = name.rpartition(".")
    return f"{base}-{hashlib.sha256(content).hexdigest()[:12]}.{suffix}"


def _is_version_of(relative_path: str, name: str) -> bool:
    """Whether a stored artifact is a copy of *name*, content-tagged or not.

    Stores written before names carried a content tag hold the bare name, and
    they keep working.
    """
    base, _, suffix = name.rpartition(".")
    filename = relative_path.rsplit("/", 1)[-1]
    return filename == name or (filename.startswith(f"{base}-") and filename.endswith(f".{suffix}"))


class MissingUserAgentError(RuntimeError):
    """No contact string was configured.

    SEC asks automated clients to identify themselves with a name and address.
    Rather than ship a default that would misattribute this package's traffic to
    whoever wrote it, the caller has to supply one.
    """


class SecRequestError(RuntimeError):
    pass


class UnknownTickerError(KeyError):
    pass


def resolve_user_agent(explicit: str | None = None) -> str:
    agent = explicit or os.environ.get(USER_AGENT_ENV)
    if not agent or "@" not in agent:
        raise MissingUserAgentError(
            f"Set {USER_AGENT_ENV} to a contact string SEC can reach, for example "
            '"Capex Atlas research (you@example.com)". SEC asks automated clients to '
            "identify themselves, and this package will not guess on your behalf."
        )
    return agent


def cik_to_padded(cik: int | str) -> str:
    """SEC paths use the CIK zero-padded to ten digits."""
    return f"{int(cik):010d}"


class SecClient:
    """Rate-limited, caching reader for the SEC JSON APIs."""

    def __init__(
        self,
        *,
        store: RawStore,
        user_agent: str | None = None,
        client: httpx.Client | None = None,
        bucket: TokenBucket | None = None,
        rate_per_second: float = DEFAULT_REQUESTS_PER_SECOND,
        refresh: bool = False,
        max_age: timedelta | None = None,
        offline: bool = False,
    ) -> None:
        self.user_agent = resolve_user_agent(user_agent)
        self.store = store
        # Freshness policy, applied to every fetch this client makes.
        #
        # There was none. The first stored copy of a filer's Company Facts was
        # returned forever: no age check, no conditional request, no way to ask
        # for a new one, and the recorded retrieval timestamp was written and
        # never read. A data directory became a permanent snapshot on first use,
        # and a bundle built a year later cited the original download date.
        self.refresh = refresh
        self.max_age = max_age
        self.offline = offline
        self._bucket = bucket or TokenBucket(rate_per_second)
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=30.0, follow_redirects=True)
        self._ticker_index: dict[str, int] | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch(self, url: str) -> bytes:
        """GET *url*, rate-limited, retrying the statuses worth retrying."""
        last_error: str = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._bucket.acquire()
            response = self._client.get(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
            )
            if response.status_code == httpx.codes.OK:
                return response.content
            last_error = f"HTTP {response.status_code}"
            if response.status_code not in RETRY_STATUS or attempt == MAX_ATTEMPTS:
                break
        raise SecRequestError(f"{url} failed after {MAX_ATTEMPTS} attempts: {last_error}")

    def company_facts(self, cik: int | str, entity_id: str) -> tuple[RawArtifact, dict[str, Any]]:
        """XBRL facts the filer tagged, across all their filings."""
        padded = cik_to_padded(cik)
        url = f"{DATA_HOST}/api/xbrl/companyfacts/CIK{padded}.json"
        return self._fetch_json(url, name="companyfacts.json", entity_id=entity_id)

    def submissions(self, cik: int | str, entity_id: str) -> tuple[RawArtifact, dict[str, Any]]:
        """Filing history and metadata."""
        padded = cik_to_padded(cik)
        url = f"{DATA_HOST}/submissions/CIK{padded}.json"
        return self._fetch_json(url, name="submissions.json", entity_id=entity_id)

    def cik_for_ticker(self, ticker: str) -> int:
        if self._ticker_index is None:
            _, payload = self._fetch_json(
                TICKER_INDEX_URL, name="company_tickers.json", entity_id="_index"
            )
            self._ticker_index = {
                str(row["ticker"]).upper(): int(row["cik_str"]) for row in payload.values()
            }
        try:
            return self._ticker_index[ticker.upper()]
        except KeyError:
            raise UnknownTickerError(f"{ticker!r} is not in the SEC ticker index") from None

    def _fetch_json(
        self, url: str, *, name: str, entity_id: str
    ) -> tuple[RawArtifact, dict[str, Any]]:
        cached = None if self.refresh else self._cached(entity_id, name)
        if cached is not None:
            artifact, content = cached
        else:
            if self.offline:
                raise OfflineError(
                    f"no acceptable cached copy of {name} for {entity_id}, and this "
                    "client is offline. Drop --offline to fetch it."
                )
            retrieved_at = datetime.now(UTC)
            content = self.fetch(url)
            # Stored under a timestamped name so a refresh lands beside the copy
            # it supersedes instead of colliding with it. The store treats
            # artifacts as immutable and rejects changed bytes at a path, which
            # would otherwise make refreshing impossible rather than merely absent.
            artifact = self.store.store(
                content,
                name=_versioned(name, content),
                url=url,
                kind=SourceKind.SEC_FILING,
                entity_id=entity_id,
                parser_version=PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        payload: dict[str, Any] = json.loads(content)
        return artifact, payload

    def _cached(self, entity_id: str, name: str) -> tuple[RawArtifact, bytes] | None:
        """The newest stored copy, if it is young enough to use."""
        matches = [
            artifact
            for artifact in self.store.manifest(SourceKind.SEC_FILING, entity_id, None)
            if _is_version_of(artifact.relative_path, name)
        ]
        if not matches:
            return None
        newest = max(matches, key=lambda artifact: artifact.retrieved_at)
        if self.max_age is not None and datetime.now(UTC) - newest.retrieved_at > self.max_age:
            return None
        return newest, self.store.read(newest)
