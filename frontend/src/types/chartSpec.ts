import { z } from 'zod';

/**
 * Frontend mirror of the ChartSpecV1 wire contract
 * (backend/app/visualization/spec.py::ChartSpecV1).
 *
 * As of Milestone 4 the backend validates every chart spec it emits against
 * that pydantic model before sending it over the `visualization` WebSocket
 * event — invalid specs are never sent (logged + dropped server-side). This
 * schema is now the strict mirror: `chartType` is a closed enum, `series`
 * requires at least one entry, and `version` must be the literal "1".
 *
 * `recharts_builder.py` maps its richer internal chart-type vocabulary onto
 * this contract before validating:
 *   - `horizontal_bar` -> chartType `bar` + `orientation: "horizontal"`
 *   - `grouped_bar` / `stacked_bar` -> chartType `groupedBar` (stacking is
 *     signaled per-series via `series[].stackId`, not a top-level flag)
 *   - `comparison` / `box` -> chartType `groupedBar`
 *
 * Always validate with `chartSpecSchema.safeParse(...)` — never `.parse(...)`,
 * and treat a failed parse as "fall back to a table (or nothing)", not a
 * crash. A failed parse is still expected for chart specs restored from
 * conversation history that were saved before Milestone 4 (old snake_case
 * chartTypes, no `version` field) — DataTable is the correct fallback there.
 */

// Canonical chart types the backend ChartSpecV1 contract emits (or reserves
// for future chart-selection work: `area` and `table` currently have no
// producing code path but ChartRenderer implements both).
export const FUTURE_CHART_TYPES = [
  'line',
  'bar',
  'groupedBar',
  'pie',
  'scatter',
  'area',
  'table',
] as const;

// AFL warm palette — mirrors backend/app/visualization/recharts_builder.py::AFL_COLORS.
// Used whenever a spec omits `colors` (or sends an empty array) so charts never
// silently render in black.
export const DEFAULT_COLORS = [
  '#C2581C',
  '#2D7A6F',
  '#D4794D',
  '#246359',
  '#8C7B6B',
  '#A30046',
  '#D4001A',
  '#002B5C',
];

const axisConfigSchema = z
  .object({
    label: z.string().optional(),
    tickAngle: z.number().optional(),
    domain: z.tuple([z.number(), z.number()]).optional(),
    integerOnly: z.boolean().optional(),
  })
  .passthrough();

const seriesItemSchema = z
  .object({
    key: z.string(),
    name: z.string().optional(),
    color: z.string().optional(),
    dashed: z.boolean().optional(),
    stackId: z.string().optional(),
    // AFL team to colour this series by (team itself, or a player's most
    // frequent club) — not read by ChartRenderer yet, kept for a future pass.
    highlight: z.string().optional(),
  })
  .passthrough();

const annotationSchema = z
  .object({
    x: z.union([z.string(), z.number()]),
    y: z.number(),
    label: z.string().optional().default(''),
    color: z.string().optional(),
  })
  .passthrough();

// Strict chartType enum — matches backend ChartSpecV1.ChartTypeV1 exactly.
export const chartTypeSchema = z.enum(FUTURE_CHART_TYPES);

export const chartSpecSchema = z
  .object({
    version: z.literal('1'),
    chartType: chartTypeSchema,
    title: z.string().optional().default(''),
    // A row is a flexible record: {name/x, value/metric, ...}. Empty data is
    // rejected here on purpose — ChartRenderer treats the resulting parse
    // failure as its "no chart, no crash" empty-data guard.
    data: z.array(z.record(z.string(), z.unknown())).min(1),
    series: z.array(seriesItemSchema).min(1),
    xAxis: axisConfigSchema.optional().default({}),
    yAxis: axisConfigSchema.optional().default({}),
    colors: z.array(z.string()).optional(),
    annotations: z.array(annotationSchema).optional(),
    legend: z.boolean().optional(),
    // Bar-only: "horizontal" renders bars laid out horizontally (long
    // category names) via the same `bar` chartType.
    orientation: z.enum(['horizontal', 'vertical']).optional(),
    // Pie-only: false when the backend grouped >5 slices into "Other" — the
    // frontend suppresses on-slice text labels in favor of legend + tooltip.
    showSliceLabels: z.boolean().optional(),
    // Line-only: "linear" for discrete per-season/round data (smoothing implies
    // values between seasons that don't exist). Not read by ChartRenderer yet —
    // a data-contract stepping stone for a later chart-styling pass.
    curve: z.enum(['linear', 'monotone']).optional(),
  })
  .passthrough();

export type ChartSpec = z.infer<typeof chartSpecSchema>;
export type SeriesItem = z.infer<typeof seriesItemSchema>;
export type AxisConfig = z.infer<typeof axisConfigSchema>;
export type Annotation = z.infer<typeof annotationSchema>;
