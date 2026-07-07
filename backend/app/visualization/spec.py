"""
AFL Analytics Agent - Chart Spec Contract (v1)

Pydantic model for the wire format emitted by ``RechartsBuilder`` to the
frontend over the ``visualization`` WebSocket event. This is the backend
half of the contract mirrored in ``frontend/src/types/chartSpec.ts`` (zod).

Canonical `chartType` values (camelCase): line, bar, groupedBar, pie,
scatter, area, table.

The chart-selection/preprocessing pipeline (chart_selector.py,
data_preprocessor.py, layout_config.py) still uses its own richer internal
vocabulary (`horizontal_bar`, `stacked_bar`, `grouped_bar`, `box`,
`comparison`, `trend`, ...) end-to-end — that vocabulary is NOT part of this
contract. `RechartsBuilder` is the single seam that translates internal
chart types into this contract before anything is validated or sent over
the wire:

  - `horizontal_bar` -> chartType `bar` + `orientation: "horizontal"`
  - `grouped_bar` / `stacked_bar` -> chartType `groupedBar` (stacking is
    signaled per-series via `SeriesItem.stackId`, not a top-level flag)
  - `comparison` -> chartType `groupedBar`
  - `box` -> chartType `groupedBar` (median + range, see recharts_builder)
  - `trend` -> chartType `line`

Use `ChartSpecV1.model_validate(raw_dict)` and catch `pydantic.ValidationError`
around it; on failure, log loudly and emit nothing (never send a spec that
doesn't conform to this contract).
"""
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

# Canonical wire-format chart types. Keep in sync with
# frontend/src/types/chartSpec.ts::FUTURE_CHART_TYPES.
ChartTypeV1 = Literal["line", "bar", "groupedBar", "pie", "scatter", "area", "table"]


class AxisConfig(BaseModel):
    """Axis configuration. Mirrors chartSpec.ts::axisConfigSchema."""

    model_config = ConfigDict(extra="allow")

    label: Optional[str] = None
    tickAngle: Optional[float] = None
    domain: Optional[List[float]] = None
    integerOnly: Optional[bool] = None


class SeriesItem(BaseModel):
    """A single plotted series. Mirrors chartSpec.ts::seriesItemSchema."""

    model_config = ConfigDict(extra="allow")

    key: str
    name: Optional[str] = None
    color: Optional[str] = None
    dashed: Optional[bool] = None
    # Presence of stackId is how a "stacked" groupedBar is signaled to the
    # frontend (ChartRenderer's renderGroupedBarChart reads it per-series).
    stackId: Optional[str] = None


class Annotation(BaseModel):
    """A single reference-point annotation. Mirrors chartSpec.ts::annotationSchema."""

    model_config = ConfigDict(extra="allow")

    x: Union[str, float]
    y: float
    label: str = ""
    color: Optional[str] = None


class ChartSpecV1(BaseModel):
    """
    Versioned chart spec contract emitted by RechartsBuilder.

    Required: version, chartType, data (>=1 row), series (>=1 entry).
    `extra="forbid"` at this level so an accidental new top-level key
    (e.g. a stray "error" field from an old fallback path) fails validation
    loudly instead of silently reaching the frontend.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    chartType: ChartTypeV1
    title: str = ""
    data: List[Dict[str, Any]] = Field(min_length=1)
    series: List[SeriesItem] = Field(min_length=1)
    xAxis: AxisConfig = Field(default_factory=AxisConfig)
    yAxis: AxisConfig = Field(default_factory=AxisConfig)
    colors: Optional[List[str]] = None
    annotations: Optional[List[Annotation]] = None
    legend: Optional[bool] = None

    # ── Optional extras (documented deviations from the plan's minimal
    # field list, needed to keep existing ChartRenderer behavior working) ──

    # Set to "horizontal" for a horizontal bar chart (chartType stays "bar").
    orientation: Optional[Literal["horizontal", "vertical"]] = None
    # Pie-only: when the backend grouped long tails into "Other" (>5 slices),
    # slice-level text labels are suppressed in favor of legend + tooltip to
    # avoid label overlap. Defaults to showing labels when omitted.
    showSliceLabels: Optional[bool] = None
