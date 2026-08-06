"""The metadata-only policy, which is the part of tracing that can do harm."""

from __future__ import annotations

from decimal import Decimal

import pytest

from capex_atlas.obs import AttributePolicyError, content_digest, sanitize, span, tracing


class TestContentCannotReachASpan:
    def test_plain_metadata_passes(self):
        clean = sanitize(
            {
                "capex_atlas.company.ticker": "GOOGL",
                "capex_atlas.fiscal.period": "2025FY",
                "capex_atlas.fact.count": 943,
                "capex_atlas.validation.passed": True,
            }
        )
        assert clean["capex_atlas.company.ticker"] == "GOOGL"
        assert clean["capex_atlas.fact.count"] == 943

    @pytest.mark.parametrize(
        "key",
        [
            "capex_atlas.claim.quote",
            "capex_atlas.model.prompt",
            "capex_atlas.document.text",
            "capex_atlas.filing.content",
            "capex_atlas.agent.reasoning",
            "capex_atlas.transcript.passage",
        ],
    )
    def test_content_bearing_keys_are_refused(self, key: str):
        with pytest.raises(AttributePolicyError, match="carries content"):
            sanitize({key: "anything"})

    def test_a_hash_of_a_passage_is_allowed(self):
        # Identifying a passage without reproducing it is the supported route.
        clean = sanitize({"capex_atlas.claim.quote_sha256": content_digest("a long passage")})
        assert len(next(iter(clean.values()))) == 16

    def test_a_long_string_is_refused_rather_than_truncated(self):
        # A truncated prompt is still a prompt.
        with pytest.raises(AttributePolicyError, match="probably document text"):
            sanitize({"capex_atlas.note": "x" * 500})

    def test_attributes_outside_the_namespace_are_refused(self):
        with pytest.raises(AttributePolicyError, match="must start with"):
            sanitize({"company.ticker": "GOOGL"})

    def test_decimals_are_refused_with_a_reason(self):
        with pytest.raises(AttributePolicyError, match="calculation graph"):
            sanitize({"capex_atlas.metric.result": Decimal("1.5")})

    def test_structures_are_refused(self):
        with pytest.raises(AttributePolicyError, match="scalars only"):
            sanitize({"capex_atlas.facts": [1, 2, 3]})

    def test_the_policy_runs_even_without_opentelemetry(self):
        # Otherwise a violation would only surface in production, where the
        # exporter is real and someone else is reading it.
        with (
            pytest.raises(AttributePolicyError),
            span("capex_atlas.metric.calculate", **{"capex_atlas.doc.text": "y" * 400}),
        ):
            pass


class TestSpansAreSafeWithoutTheSdk:
    def test_a_span_works_when_tracing_is_unavailable(self):
        with span("capex_atlas.metric.calculate", **{"capex_atlas.metric.name": "roic"}) as active:
            assert active is None or hasattr(active, "set_attribute")

    def test_configure_reports_whether_tracing_is_live(self):
        assert tracing.configure() is tracing.available()

    def test_trace_id_is_absent_without_a_provider(self):
        if not tracing.available():
            assert tracing.current_trace_id() is None

    def test_annotate_on_a_noop_span_is_harmless(self):
        tracing.annotate(None, {"capex_atlas.company.ticker": "GOOGL"})

    def test_annotate_still_enforces_the_policy_when_the_span_is_real(self):
        class Recorder:
            def __init__(self) -> None:
                self.seen: dict[str, object] = {}

            def set_attribute(self, key: str, value: object) -> None:
                self.seen[key] = value

        recorder = Recorder()
        tracing.annotate(recorder, {"capex_atlas.company.ticker": "GOOGL"})
        assert recorder.seen == {"capex_atlas.company.ticker": "GOOGL"}
        with pytest.raises(AttributePolicyError):
            tracing.annotate(recorder, {"capex_atlas.filing.text": "z" * 400})


def test_the_span_taxonomy_is_namespaced():
    assert all(name.startswith("capex_atlas.") for name in tracing.SPAN_NAMES)
