"""Ingestion tests. All offline: nothing here touches the network."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from capex_atlas.schemas.source import SourceKind
from capex_atlas.sources.rate_limit import TokenBucket
from capex_atlas.sources.raw import ArtifactConflictError, MissingArtifactError, RawStore
from capex_atlas.sources.sec import (
    MissingUserAgentError,
    OfflineError,
    SecClient,
    SecRequestError,
    UnknownTickerError,
    cik_to_padded,
    resolve_user_agent,
)

AGENT = "Capex Atlas tests (tests@example.invalid)"


class FakeClock:
    """Drives TokenBucket without real waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class TestTokenBucket:
    def test_first_call_does_not_wait(self):
        clock = FakeClock()
        bucket = TokenBucket(2.0, monotonic=clock.monotonic, sleep=clock.sleep)
        assert bucket.acquire() == 0.0

    def test_second_call_waits_for_the_rate(self):
        clock = FakeClock()
        bucket = TokenBucket(2.0, monotonic=clock.monotonic, sleep=clock.sleep)
        bucket.acquire()
        assert bucket.acquire() == pytest.approx(0.5)

    def test_elapsed_time_refills(self):
        clock = FakeClock()
        bucket = TokenBucket(2.0, monotonic=clock.monotonic, sleep=clock.sleep)
        bucket.acquire()
        clock.now += 10
        assert bucket.acquire() == 0.0

    def test_burst_allows_a_few_immediate_calls(self):
        clock = FakeClock()
        bucket = TokenBucket(1.0, burst=3, monotonic=clock.monotonic, sleep=clock.sleep)
        assert [bucket.acquire() for _ in range(3)] == [0.0, 0.0, 0.0]
        assert bucket.acquire() > 0

    @pytest.mark.parametrize("rate", [0, -1])
    def test_rejects_nonpositive_rates(self, rate: float):
        with pytest.raises(ValueError, match="must be positive"):
            TokenBucket(rate)


class TestRawStore:
    def test_stores_content_and_records_the_hash(self, tmp_path: Path):
        store = RawStore(tmp_path)
        artifact = store.store(
            b'{"a": 1}',
            name="companyfacts.json",
            url="https://example.invalid/facts",
            kind=SourceKind.SEC_FILING,
            entity_id="GOOGL",
        )
        assert artifact.byte_count == 8
        assert store.read(artifact) == b'{"a": 1}'
        assert (tmp_path / "sec_filing" / "GOOGL" / "companyfacts.json").exists()

    def test_restoring_identical_bytes_is_idempotent(self, tmp_path: Path):
        store = RawStore(tmp_path)
        kwargs = {
            "name": "f.json",
            "url": "https://example.invalid/f",
            "kind": SourceKind.SEC_FILING,
            "entity_id": "GOOGL",
        }
        first = store.store(b"same", **kwargs)  # type: ignore[arg-type]
        second = store.store(b"same", **kwargs)  # type: ignore[arg-type]
        assert first == second

    def test_conflicting_bytes_are_refused(self, tmp_path: Path):
        store = RawStore(tmp_path)
        kwargs = {
            "name": "f.json",
            "url": "https://example.invalid/f",
            "kind": SourceKind.SEC_FILING,
            "entity_id": "GOOGL",
        }
        store.store(b"original", **kwargs)  # type: ignore[arg-type]
        with pytest.raises(ArtifactConflictError, match="immutable"):
            store.store(b"revised", **kwargs)  # type: ignore[arg-type]

    def test_tampering_is_detected_on_read(self, tmp_path: Path):
        store = RawStore(tmp_path)
        artifact = store.store(
            b"trusted",
            name="f.json",
            url="https://example.invalid/f",
            kind=SourceKind.SEC_FILING,
            entity_id="GOOGL",
        )
        (tmp_path / artifact.relative_path).write_bytes(b"tampered")
        with pytest.raises(ArtifactConflictError, match="no longer matches"):
            store.read(artifact)

    def test_manifest_round_trips(self, tmp_path: Path):
        store = RawStore(tmp_path)
        store.store(
            b"x",
            name="f.json",
            url="https://example.invalid/f",
            kind=SourceKind.SEC_FILING,
            entity_id="GOOGL",
        )
        entries = store.manifest(SourceKind.SEC_FILING, "GOOGL", None)
        assert [e.relative_path for e in entries] == ["sec_filing/GOOGL/f.json"]

    def test_artifact_becomes_a_citation(self, tmp_path: Path):
        store = RawStore(tmp_path)
        artifact = store.store(
            b"x",
            name="f.json",
            url="https://example.invalid/f",
            kind=SourceKind.SEC_FILING,
            entity_id="GOOGL",
            accession="0001652044-26-000000",
            form="10-Q",
        )
        ref = artifact.to_source_reference(section="Statements of Cash Flows", page=6)
        assert ref.accession == "0001652044-26-000000"
        assert ref.content_sha256 == artifact.sha256
        assert ref.is_verifiable


class TestUserAgent:
    def test_explicit_agent_is_used(self):
        assert resolve_user_agent(AGENT) == AGENT

    def test_environment_agent_is_used(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CAPEX_ATLAS_SEC_USER_AGENT", AGENT)
        assert resolve_user_agent() == AGENT

    def test_missing_agent_explains_why(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CAPEX_ATLAS_SEC_USER_AGENT", raising=False)
        with pytest.raises(MissingUserAgentError, match="will not guess"):
            resolve_user_agent()

    def test_agent_without_contact_is_refused(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CAPEX_ATLAS_SEC_USER_AGENT", raising=False)
        with pytest.raises(MissingUserAgentError):
            resolve_user_agent("capex-atlas")


def test_cik_padding():
    assert cik_to_padded(1652044) == "0001652044"
    assert cik_to_padded("1652044") == "0001652044"


def build_client(tmp_path: Path, handler) -> SecClient:  # type: ignore[no-untyped-def]
    clock = FakeClock()
    return SecClient(
        store=RawStore(tmp_path),
        user_agent=AGENT,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        bucket=TokenBucket(1000.0, monotonic=clock.monotonic, sleep=clock.sleep),
    )


class TestSecClient:
    def test_company_facts_are_fetched_and_stored(self, tmp_path: Path):
        payload = {"cik": 1652044, "facts": {}}
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=payload)

        with build_client(tmp_path, handler) as client:
            artifact, data = client.company_facts(1652044, "GOOGL")

        assert data == payload
        assert "CIK0001652044.json" in str(calls[0].url)
        assert calls[0].headers["User-Agent"] == AGENT
        assert json.loads(client.store.read(artifact)) == payload

    def test_second_call_is_served_from_the_store(self, tmp_path: Path):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"cik": 1})

        with build_client(tmp_path, handler) as client:
            client.company_facts(1, "GOOGL")
            client.company_facts(1, "GOOGL")

        assert len(calls) == 1

    def test_retries_then_succeeds(self, tmp_path: Path):
        statuses = iter([503, 429, 200])

        def handler(request: httpx.Request) -> httpx.Response:
            status = next(statuses)
            return httpx.Response(status, json={"ok": True} if status == 200 else {})

        with build_client(tmp_path, handler) as client:
            _, data = client.submissions(1, "GOOGL")
        assert data == {"ok": True}

    def test_client_errors_are_not_retried(self, tmp_path: Path):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(404)

        with build_client(tmp_path, handler) as client, pytest.raises(SecRequestError, match="404"):
            client.submissions(1, "GOOGL")
        assert len(calls) == 1

    def test_persistent_failure_gives_up(self, tmp_path: Path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        with build_client(tmp_path, handler) as client, pytest.raises(SecRequestError, match="503"):
            client.submissions(1, "GOOGL")

    def test_ticker_lookup(self, tmp_path: Path):
        index = {"0": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."}}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=index)

        with build_client(tmp_path, handler) as client:
            assert client.cik_for_ticker("googl") == 1652044
            with pytest.raises(UnknownTickerError):
                client.cik_for_ticker("NOSUCH")


class TestCacheFreshness:
    """The first download was served forever.

    No age check, no conditional request, no way to ask for a new copy, and the
    recorded retrieval timestamp was written and never read. A data directory
    became a permanent snapshot the moment it was first used.
    """

    @staticmethod
    def changing_transport(payloads: list[dict[str, object]]) -> httpx.MockTransport:
        """Serves a different body on each call, so staleness is observable."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payloads[min(len(payloads) - 1, handler.calls)])

        handler.calls = 0  # type: ignore[attr-defined]

        def counting(request: httpx.Request) -> httpx.Response:
            response = handler(request)
            handler.calls += 1  # type: ignore[attr-defined]
            return response

        return httpx.MockTransport(counting)

    def client(self, tmp_path: Path, transport: httpx.MockTransport, **policy: object) -> SecClient:
        return SecClient(
            store=RawStore(tmp_path),
            user_agent="tests (tests@example.invalid)",
            client=httpx.Client(transport=transport),
            **policy,  # type: ignore[arg-type]
        )

    def test_a_cached_copy_is_served_without_asking_sec_again(self, tmp_path: Path):
        transport = self.changing_transport([{"version": 1}, {"version": 2}])
        first = self.client(tmp_path, transport).company_facts(1652044, "GOOGL")[1]
        second = self.client(tmp_path, transport).company_facts(1652044, "GOOGL")[1]
        assert first == second == {"version": 1}

    def test_refresh_fetches_a_new_copy(self, tmp_path: Path):
        transport = self.changing_transport([{"version": 1}, {"version": 2}])
        self.client(tmp_path, transport).company_facts(1652044, "GOOGL")
        _, payload = self.client(tmp_path, transport, refresh=True).company_facts(1652044, "GOOGL")
        assert payload == {"version": 2}

    def test_the_new_copy_lands_beside_the_old_one(self, tmp_path: Path):
        transport = self.changing_transport([{"version": 1}, {"version": 2}])
        self.client(tmp_path, transport).company_facts(1652044, "GOOGL")
        self.client(tmp_path, transport, refresh=True).company_facts(1652044, "GOOGL")
        stored = sorted(p.name for p in tmp_path.rglob("companyfacts*.json"))
        assert len(stored) == 2, stored
        # Both keep their own hash and timestamp; neither overwrote the other.
        artifacts = RawStore(tmp_path).manifest(SourceKind.SEC_FILING, "GOOGL", None)
        assert len({a.sha256 for a in artifacts}) == 2

    def test_an_expired_copy_is_refetched(self, tmp_path: Path):
        transport = self.changing_transport([{"version": 1}, {"version": 2}])
        self.client(tmp_path, transport).company_facts(1652044, "GOOGL")
        fresh = self.client(tmp_path, transport, max_age=timedelta(seconds=0))
        assert fresh.company_facts(1652044, "GOOGL")[1] == {"version": 2}

    def test_a_copy_within_max_age_is_kept(self, tmp_path: Path):
        transport = self.changing_transport([{"version": 1}, {"version": 2}])
        self.client(tmp_path, transport).company_facts(1652044, "GOOGL")
        recent = self.client(tmp_path, transport, max_age=timedelta(days=7))
        assert recent.company_facts(1652044, "GOOGL")[1] == {"version": 1}

    def test_offline_serves_the_cache_and_refuses_to_fetch(self, tmp_path: Path):
        transport = self.changing_transport([{"version": 1}])
        self.client(tmp_path, transport).company_facts(1652044, "GOOGL")
        offline = self.client(tmp_path, transport, offline=True)
        assert offline.company_facts(1652044, "GOOGL")[1] == {"version": 1}

        with pytest.raises(OfflineError, match="offline"):
            self.client(tmp_path / "empty", transport, offline=True).company_facts(1, "MSFT")

    def test_deleting_the_file_but_not_the_manifest_says_so(self, tmp_path: Path):
        transport = self.changing_transport([{"version": 1}])
        self.client(tmp_path, transport).company_facts(1652044, "GOOGL")
        for path in tmp_path.rglob("companyfacts*.json"):
            path.unlink()
        with pytest.raises(MissingArtifactError, match="missing from disk"):
            self.client(tmp_path, transport).company_facts(1652044, "GOOGL")
