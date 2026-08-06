"""The ``@metric`` decorator.

Metrics are declared rather than hand-written so that no result can exist
without a calculation node, and so that evidence status propagates without
anyone having to remember to propagate it.

A metric body is plain arithmetic over ``Decimal``. Everything else -- unwrapping
inputs, checking units and periods, degrading status, building the node,
recording it in the active graph -- happens here, once.
"""

from __future__ import annotations

import decimal
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from capex_atlas.assumptions.models import Assumption
from capex_atlas.provenance.errors import (
    DuplicateMetricError,
    PeriodMismatchError,
    UnitMismatchError,
)
from capex_atlas.provenance.graph import active_graph
from capex_atlas.schemas.calculation import CalculationNode
from capex_atlas.schemas.decimals import calculation_context
from capex_atlas.schemas.evidence import EvidenceStatus
from capex_atlas.schemas.hashing import canonical
from capex_atlas.schemas.period import FiscalPeriod, PeriodKind
from capex_atlas.schemas.values import AnalyticalValue

INHERIT: Final = "<inherit>"
"""Sentinel for ``unit``: take the unit of the first analytical input."""

OUTPUT_PERIOD_KWARG: Final = "_output_period"
"""Reserved call-time kwarg naming the result's period explicitly."""

ComputeFn = Callable[..., Decimal | None]


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    version: str
    formula: str
    unit: str
    label: str
    homogeneous_inputs: bool
    allow_mixed_periods: bool
    allow_missing_inputs: bool


class Metric:
    """A callable that turns ``AnalyticalValue`` inputs into one traced output."""

    def __init__(self, definition: MetricDefinition, compute: ComputeFn) -> None:
        self.definition = definition
        self._compute = compute
        self.__name__ = compute.__name__
        self.__doc__ = compute.__doc__

    def __call__(self, *args: Any, **kwargs: Any) -> AnalyticalValue:
        spec = self.definition
        # Reserved kernel kwarg. Cross-period metrics cannot infer their own
        # output period -- a discrete quarter derived by differencing two
        # year-to-date figures belongs to neither input -- so the caller states it.
        output_period: FiscalPeriod | None = kwargs.pop(OUTPUT_PERIOD_KWARG, None)
        ordered = [*args, *kwargs.values()]
        analytical = [item for item in ordered if isinstance(item, AnalyticalValue)]
        assumptions = [item for item in ordered if isinstance(item, Assumption)]

        self._check_units(analytical)
        # Run the period check for its validation regardless, then let an
        # explicit output period win over the inferred one.
        inferred_period = self._check_periods(analytical)
        period = output_period if output_period is not None else inferred_period

        input_ids = tuple(item.value_id for item in analytical)
        assumption_ids = tuple(item.assumption_id for item in assumptions)
        # Bare literals are not graph inputs, but they do change the result, so
        # they have to participate in the content-addressed id.
        literals = tuple(
            canonical(item)
            for item in ordered
            if not isinstance(item, AnalyticalValue | Assumption)
        )
        period_label = period.label if period is not None else None

        node_id = CalculationNode.derive_id(
            metric_id=spec.metric_id,
            metric_version=spec.version,
            inputs=input_ids + literals,
            assumption_ids=assumption_ids,
            period_label=period_label,
        )

        unit = self._resolve_unit(analytical)
        result, status = self._evaluate(args, kwargs, analytical, assumptions)

        source_ids = tuple(
            dict.fromkeys(source for item in analytical for source in item.source_ids)
        )
        node = CalculationNode(
            node_id=node_id,
            metric_id=spec.metric_id,
            metric_version=spec.version,
            formula=spec.formula,
            inputs=input_ids,
            assumption_ids=assumption_ids,
            source_ids=source_ids,
            result=result,
            unit=unit,
            status=status,
            period_label=period_label,
        )
        graph = active_graph()
        if graph is not None:
            graph.add(node)

        return AnalyticalValue(
            value_id=node_id,
            value=result,
            unit=unit,
            status=status,
            period=period,
            label=spec.label,
            formula_node_id=node_id,
            source_ids=source_ids,
            assumption_ids=assumption_ids,
        )

    def _evaluate(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        analytical: list[AnalyticalValue],
        assumptions: list[Assumption],
    ) -> tuple[Decimal | None, EvidenceStatus]:
        spec = self.definition
        statuses = [item.status for item in analytical] + [item.status for item in assumptions]

        # A bare ``None`` means the caller had no fact for that input at all,
        # which is routine when a filer does not tag a concept. Treat it exactly
        # like a value-less AnalyticalValue rather than letting it reach the
        # metric body and raise.
        missing = any(item.value is None for item in analytical) or any(
            item is None for item in (*args, *kwargs.values())
        )
        if missing and not spec.allow_missing_inputs:
            return None, EvidenceStatus.UNRESOLVED

        try:
            # One precision setting for every metric, so a result never depends
            # on whatever context the caller happened to be in.
            with decimal.localcontext(calculation_context()):
                result = self._compute(*_unwrap_all(args), **_unwrap_map(kwargs))
        except (decimal.DivisionByZero, decimal.InvalidOperation):
            # A zero denominator is a real analytical outcome (no invested
            # capital, no revenue yet) rather than a crash, and it resolves to
            # unknown. Returning zero here would assert something false.
            return None, EvidenceStatus.UNRESOLVED

        if result is None:
            return None, EvidenceStatus.UNRESOLVED
        # A calculation is at best derived, however solid its inputs.
        return result, EvidenceStatus.weakest(EvidenceStatus.DERIVED, *statuses)

    def _resolve_unit(self, analytical: list[AnalyticalValue]) -> str:
        if self.definition.unit != INHERIT:
            return self.definition.unit
        if not analytical:
            raise UnitMismatchError(
                f"{self.definition.metric_id}: unit=INHERIT needs at least one analytical input"
            )
        return analytical[0].unit

    def _check_units(self, analytical: list[AnalyticalValue]) -> None:
        if not self.definition.homogeneous_inputs:
            return
        units = {item.unit for item in analytical}
        if len(units) > 1:
            raise UnitMismatchError(
                f"{self.definition.metric_id} adds its inputs, so they must share a unit; "
                f"got {sorted(units)}"
            )

    def _check_periods(self, analytical: list[AnalyticalValue]) -> FiscalPeriod | None:
        """Validate the input periods and decide which one the result belongs to.

        Mixing a flow with a stock is not an error, it is what a return ratio is:
        NOPAT earned over a year divided by capital measured at a date. So one
        duration period alongside any number of balance-sheet dates is allowed,
        and the result takes the duration period, because that is the span the
        ratio describes.

        Two *different* spans is a different matter and stays an error unless the
        metric declares itself cross-period.
        """
        periods = {item.period for item in analytical if item.period is not None}
        durations = {p for p in periods if p.kind is not PeriodKind.INSTANT}
        instants = periods - durations

        if not self.definition.allow_mixed_periods:
            if len(durations) > 1:
                raise PeriodMismatchError(
                    f"{self.definition.metric_id} received inputs spanning "
                    f"{sorted(p.label for p in durations)}. Set allow_mixed_periods=True only "
                    "if the metric is defined across periods, such as a lagged incremental "
                    "return."
                )
            if not durations and len(instants) > 1:
                raise PeriodMismatchError(
                    f"{self.definition.metric_id} received balance-sheet inputs from "
                    f"{sorted(p.label for p in instants)} with no period to anchor them to."
                )

        if len(durations) == 1:
            return next(iter(durations))
        if not durations and len(instants) == 1:
            return next(iter(instants))
        return None


def _unwrap(item: Any) -> Any:
    if isinstance(item, AnalyticalValue):
        return item.value
    if isinstance(item, Assumption):
        return item.value
    return item


def _unwrap_all(items: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(_unwrap(item) for item in items)


def _unwrap_map(items: dict[str, Any]) -> dict[str, Any]:
    return {key: _unwrap(value) for key, value in items.items()}


_REGISTRY: dict[str, Metric] = {}


def metric(
    *,
    metric_id: str,
    version: str,
    formula: str,
    unit: str,
    label: str | None = None,
    homogeneous_inputs: bool = False,
    allow_mixed_periods: bool = False,
    allow_missing_inputs: bool = False,
) -> Callable[[ComputeFn], Metric]:
    """Declare a traced metric.

    Args:
        metric_id: Stable dotted name, e.g. ``fcf.standardized``.
        version: Bump when the formula changes, so historical bundles keep
            reproducing their original numbers.
        formula: Human-readable formula, shown to readers next to the result.
        unit: Output unit, or :data:`INHERIT` to take it from the first input.
        homogeneous_inputs: Require every analytical input to share a unit.
            Set this on anything additive.
        allow_mixed_periods: Permit inputs from different fiscal periods. Only
            correct for genuinely cross-period metrics such as lagged
            incremental ROIC.
        allow_missing_inputs: Pass ``None`` inputs through to the body instead
            of short-circuiting to unresolved.
    """

    def decorate(compute: ComputeFn) -> Metric:
        if metric_id in _REGISTRY:
            raise DuplicateMetricError(f"metric {metric_id!r} is already registered")
        definition = MetricDefinition(
            metric_id=metric_id,
            version=version,
            formula=formula,
            unit=unit,
            label=label or metric_id,
            homogeneous_inputs=homogeneous_inputs,
            allow_mixed_periods=allow_mixed_periods,
            allow_missing_inputs=allow_missing_inputs,
        )
        wrapped = Metric(definition, compute)
        _REGISTRY[metric_id] = wrapped
        return wrapped

    return decorate


def registered_metrics() -> dict[str, Metric]:
    """Every metric declared so far, keyed by id."""
    return dict(_REGISTRY)
