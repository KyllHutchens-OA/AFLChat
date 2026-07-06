import { z } from 'zod';

/**
 * Frontend mirror of the chart spec contract.
 *
 * The Milestone-4 backend work will introduce a versioned pydantic contract with a
 * canonical, strictly-typed `chartType` enum. This schema is written to be that
 * contract's frontend counterpart, but it deliberately stays LOOSER than the ideal
 * shape in a couple of places, because the CURRENT backend
 * (`backend/app/visualization/recharts_builder.py`) already ships payloads that
 * would fail a strict version:
 *
 *  - `chartType` includes snake_case values not in the future enum
 *    (`horizontal_bar`, `stacked_bar`, `grouped_bar`, `box`), and uses
 *    `grouped_bar`/`stacked_bar` where the future contract will use `groupedBar`.
 *    We validate it as a non-empty string rather than a strict enum so today's
 *    payloads (and near-future ones) both parse. `ChartRenderer`'s own switch
 *    statement is what actually routes/falls back on unrecognized values.
 *  - `series` can legitimately be an EMPTY array today (pie charts and the
 *    backend's error-fallback payload both send `series: []`), so it is NOT
 *    enforced as min-1 even though the future contract calls for that. Treat the
 *    `FUTURE_CHART_TYPES`/min-1 intent below as documentation for Milestone 4,
 *    not as an active runtime constraint.
 *
 * Always validate with `chartSpecSchema.safeParse(...)` — never `.parse(...)` —
 * and treat a failed parse as "fall back to a table (or nothing)", not a crash.
 */

// Canonical chart types the Milestone-4 backend contract is expected to emit.
// Not enforced by chartTypeSchema (see note above) — kept here for Milestone-4
// alignment / documentation purposes.
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
    key: z.string().optional(),
    name: z.string().optional(),
    color: z.string().optional(),
    dashed: z.boolean().optional(),
    stackId: z.string().optional(),
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

export const chartSpecSchema = z
  .object({
    // Future contract field; the current backend never sends this.
    version: z.literal('1').optional(),
    chartType: z.string().min(1),
    title: z.string().optional().default(''),
    // A row is a flexible record: {name/x, value/metric, ...}. Empty data is
    // rejected here on purpose — ChartRenderer treats the resulting parse
    // failure as its "no chart, no crash" empty-data guard.
    data: z.array(z.record(z.string(), z.unknown())).min(1),
    series: z.array(seriesItemSchema).optional().default([]),
    xAxis: axisConfigSchema.optional().default({}),
    yAxis: axisConfigSchema.optional().default({}),
    colors: z.array(z.string()).optional(),
    annotations: z.array(annotationSchema).optional(),
    legend: z.boolean().optional(),
  })
  .passthrough();

export type ChartSpec = z.infer<typeof chartSpecSchema>;
export type SeriesItem = z.infer<typeof seriesItemSchema>;
export type AxisConfig = z.infer<typeof axisConfigSchema>;
export type Annotation = z.infer<typeof annotationSchema>;
