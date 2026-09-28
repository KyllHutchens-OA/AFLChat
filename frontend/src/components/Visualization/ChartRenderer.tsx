import React, { useEffect, useState } from 'react';
import {
  ResponsiveContainer,
  LineChart, Line,
  AreaChart, Area,
  BarChart, Bar,
  ScatterChart, Scatter,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ReferenceDot, ReferenceLine, Label,
  ComposedChart,
} from 'recharts';
import { chartSpecSchema, ChartSpec, SeriesItem, DEFAULT_COLORS } from '../../types/chartSpec';
import { CLUBS } from '../../constants/clubs';
import DataTable from './DataTable';

interface ChartRendererProps {
  spec: any;
  // Embedded inside a ResponseCard, which is already a card — no nested card chrome.
  bare?: boolean;
}

// ── Warm tooltip styling ────────────────────────────────────────

const tooltipStyle = {
  backgroundColor: 'rgba(255, 253, 249, 0.96)',
  border: '1px solid #E8DDD3',
  borderRadius: '12px',
  padding: '8px 12px',
  boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
  fontSize: '13px',
  color: '#3D2E1F',
};

// ── Shared axis tick formatter ──────────────────────────────────

const integerFormatter = (value: any) => {
  const num = Number(value);
  if (!isNaN(num) && Number.isInteger(num)) return String(num);
  return String(value);
};

// ── Club colours (2A `highlight`: the AFL team's full name, matching
// teams.name — e.g. "Geelong", "Brisbane Lions" — not an abbreviation). ────
// When any series names a club, series without one are muted so the
// highlighted subject(s) stand out — e.g. Daicos (Collingwood) vs Bontempelli
// (Western Bulldogs) in real club colours, or one club highlighted in an
// otherwise grey ranking.

const CLUB_BY_NAME: Record<string, (typeof CLUBS)[number]> = Object.fromEntries(
  CLUBS.map((c) => [c.name.toLowerCase(), c]),
);
const MUTED_SERIES_COLOR = '#C3AC87'; // warm-300 — recedes behind club colours

function resolveSeriesColors(series: SeriesItem[], palette: string[]): string[] {
  const anyHighlight = series.some((s) => s.highlight);
  return series.map((s, i) => {
    const club = s.highlight ? CLUB_BY_NAME[s.highlight.toLowerCase()] : undefined;
    if (club) return club.primaryColor;
    if (anyHighlight) return MUTED_SERIES_COLOR; // has a highlight elsewhere, this one isn't the subject
    return s.color || palette[i % palette.length];
  });
}

// A groupedBar with any negative value is 2A's diverging_bar (wins positive,
// losses negative) — it needs a visible y=0 baseline, since grouped bars
// straddling zero otherwise look like they're floating.
function hasNegativeValues(spec: ChartSpec): boolean {
  return spec.series.some((s) => spec.data.some((row) => Number(row[s.key]) < 0));
}

// ── Responsive height: shorter on phones so a two-bar chart isn't a tall sliver ──

function useChartHeight(): number {
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < 640,
  );
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 639px)');
    const onChange = () => setNarrow(mq.matches);
    onChange();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return narrow ? 260 : 400;
}

// ── A short text summary for screen readers (charts have no text alternative
// otherwise — the table behind "Show the numbers" covers the rest) ──────────

function chartSummary(s: ChartSpec): string {
  const kind = s.orientation === 'horizontal' ? 'horizontal bar' : s.chartType;
  const seriesNames = s.series.map((x) => x.name || x.key).filter(Boolean).join(', ');
  const title = s.title ? `${s.title}. ` : '';
  return `${title}${kind} chart, ${s.data.length} data point${s.data.length === 1 ? '' : 's'}${seriesNames ? `, series: ${seriesNames}` : ''}.`;
}

// ── Main Component ──────────────────────────────────────────────

const ChartRenderer: React.FC<ChartRendererProps> = ({ spec, bare = true }) => {
  const height = useChartHeight();
  if (!spec) return null;

  const result = chartSpecSchema.safeParse(spec);

  if (!result.success) {
    // Spec doesn't match the shape we know how to chart (missing chartType,
    // empty/malformed data, etc). Fall back to a table if there's usable data
    // to show, otherwise render nothing — never crash on a bad spec.
    const rawData = Array.isArray(spec?.data) ? spec.data : null;
    if (rawData && rawData.length > 0) {
      return <DataTable data={rawData} title={typeof spec?.title === 'string' ? spec.title : undefined} bare={bare} />;
    }
    return null;
  }

  const s = result.data;

  // Empty dataset: nothing sensible to chart. This is also reachable directly
  // since the schema enforces data.min(1), but keep an explicit guard so the
  // intent is obvious and this stays safe if the schema ever relaxes that rule.
  if (!s.data.length) return null;

  // `table` isn't a Recharts chart at all — render the plain table directly
  // rather than routing it through ResponsiveContainer/renderChart.
  if (s.chartType === 'table') {
    return <DataTable data={s.data} title={s.title} bare={bare} />;
  }

  const colors = resolveSeriesColors(s.series, s.colors && s.colors.length ? s.colors : DEFAULT_COLORS);

  return (
    <div className={bare ? 'w-full tabular-nums' : 'w-full card p-6 my-4 tabular-nums'}>
      {s.title && (
        <h3 className="text-base font-semibold text-[#3D2E1F] mb-3 text-center">
          {s.title}
        </h3>
      )}
      {/* role="img" + aria-label: Recharts' SVG internals are not meaningful to
          screen readers on their own. */}
      <div role="img" aria-label={chartSummary(s)}>
        <ResponsiveContainer width="100%" height={height}>
          {renderChart(s, colors)}
        </ResponsiveContainer>
      </div>
    </div>
  );
};

// ── Chart Router ────────────────────────────────────────────────

function renderChart(spec: ChartSpec, colors: string[]): React.ReactElement {
  switch (spec.chartType) {
    case 'line':
      return renderLineChart(spec, colors);
    case 'bar':
      // Horizontal bars share the `bar` chartType — orientation is the hint.
      return spec.orientation === 'horizontal'
        ? renderHorizontalBarChart(spec, colors)
        : renderBarChart(spec, colors);
    case 'groupedBar':
      return renderGroupedBarChart(spec, colors); // stacked vs grouped: per-series stackId
    case 'scatter':
      return renderScatterChart(spec, colors);
    case 'pie':
      return renderPieChart(spec, colors);
    case 'area':
      return renderAreaChart(spec, colors);
    case 'table':
      // Handled earlier in ChartRenderer (rendered directly, no ResponsiveContainer).
      // Unreachable in practice; kept for exhaustiveness.
      return renderBarChart(spec, colors);
    default:
      return renderBarChart(spec, colors);
  }
}

// ── Shared helpers ──────────────────────────────────────────────

function renderAnnotations(spec: ChartSpec) {
  if (!spec.annotations?.length) return null;
  return spec.annotations.map((ann, i) => (
    <ReferenceDot
      key={i}
      x={ann.x}
      y={ann.y}
      r={5}
      fill={ann.color || DEFAULT_COLORS[0]}
      stroke="#fff"
      strokeWidth={2}
    >
      <Label
        value={ann.label}
        position="top"
        offset={10}
        style={{ fontSize: 11, fill: ann.color || DEFAULT_COLORS[0], fontWeight: 600 }}
      />
    </ReferenceDot>
  ));
}

function xAxisProps(spec: ChartSpec): Record<string, any> {
  const props: Record<string, any> = {
    dataKey: 'x',
    tick: { fontSize: 12, fill: '#8C7B6B' },
    tickLine: false,
    axisLine: { stroke: '#E8DDD3' },
  };
  if (spec.xAxis.label) {
    props.label = { value: spec.xAxis.label, position: 'insideBottom', offset: -5, style: { fontSize: 13, fill: '#6B5B4E', fontWeight: 500 } };
  }
  if (spec.xAxis.tickAngle) {
    props.angle = spec.xAxis.tickAngle;
    props.textAnchor = 'end';
    props.height = 80;
  }
  if (spec.xAxis.integerOnly) {
    props.tickFormatter = integerFormatter;
  }
  return props;
}

function yAxisProps(spec: ChartSpec): Record<string, any> {
  const props: Record<string, any> = {
    tick: { fontSize: 12, fill: '#8C7B6B' },
    tickLine: false,
    axisLine: { stroke: '#E8DDD3' },
  };
  if (spec.yAxis.label) {
    props.label = { value: spec.yAxis.label, angle: -90, position: 'insideLeft', offset: 10, style: { fontSize: 13, fill: '#6B5B4E', fontWeight: 500, textAnchor: 'middle' } };
  }
  if (spec.yAxis.domain) {
    props.domain = spec.yAxis.domain;
  }
  if (spec.yAxis.integerOnly) {
    props.tickFormatter = integerFormatter;
    props.allowDecimals = false;
  }
  return props;
}

// ── Line Chart ──────────────────────────────────────────────────

function renderLineChart(spec: ChartSpec, colors: string[]): React.ReactElement {
  // Use ComposedChart if any series is dashed (moving avg)
  const hasDashed = spec.series.some(s => s.dashed);
  const ChartComponent = hasDashed ? ComposedChart : LineChart;
  // "linear" for discrete per-season/round buckets (2A) — smoothing implies
  // values between seasons that don't exist. Defaults to the old "monotone".
  const curveType = spec.curve || 'monotone';

  return (
    <ChartComponent data={spec.data} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#F0EBE4" />
      <XAxis {...xAxisProps(spec)} />
      <YAxis {...yAxisProps(spec)} />
      <Tooltip contentStyle={tooltipStyle} />
      {spec.legend && <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />}
      {spec.series.map((s, i) => {
        // `colors[i]` is already highlight-resolved (resolveSeriesColors), and
        // falls back to s.color internally -- don't re-prioritize s.color here
        // or every series just gets its backend default and highlight never shows.
        const color = colors[i % colors.length];
        return (
          <Line
            key={s.key || s.name || i}
            type={curveType}
            dataKey={s.key || ''}
            name={s.name}
            stroke={color}
            strokeWidth={s.dashed ? 2 : 3}
            strokeDasharray={s.dashed ? '6 3' : undefined}
            dot={s.dashed ? false : { r: 4, fill: color, strokeWidth: 2, stroke: '#fff' }}
            activeDot={{ r: 6 }}
            animationDuration={800}
          />
        );
      })}
      {renderAnnotations(spec)}
    </ChartComponent>
  );
}

// ── Bar Chart ───────────────────────────────────────────────────

function renderBarChart(spec: ChartSpec, colors: string[]): React.ReactElement {
  return (
    <BarChart data={spec.data} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#F0EBE4" />
      <XAxis {...xAxisProps(spec)} />
      <YAxis {...yAxisProps(spec)} />
      <Tooltip contentStyle={tooltipStyle} />
      {spec.legend && <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />}
      {spec.series.map((s, i) => (
        <Bar
          key={s.key || s.name || i}
          dataKey={s.key || ''}
          name={s.name}
          fill={colors[i % colors.length]}
          radius={[4, 4, 0, 0]}
          animationDuration={600}
        />
      ))}
      {renderAnnotations(spec)}
    </BarChart>
  );
}

// ── Horizontal Bar Chart ────────────────────────────────────────

function renderHorizontalBarChart(spec: ChartSpec, colors: string[]): React.ReactElement {
  return (
    <BarChart data={spec.data} layout="vertical" margin={{ top: 20, right: 30, left: 80, bottom: 20 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#F0EBE4" />
      <XAxis type="number" tick={{ fontSize: 12, fill: '#8C7B6B' }} tickLine={false} axisLine={{ stroke: '#E8DDD3' }} />
      <YAxis
        type="category"
        dataKey="x"
        tick={{ fontSize: 12, fill: '#8C7B6B' }}
        tickLine={false}
        axisLine={{ stroke: '#E8DDD3' }}
        width={70}
      />
      <Tooltip contentStyle={tooltipStyle} />
      {spec.series.map((s, i) => (
        <Bar
          key={s.key || s.name || i}
          dataKey={s.key || ''}
          name={s.name}
          fill={colors[i % colors.length]}
          radius={[0, 4, 4, 0]}
          animationDuration={600}
        />
      ))}
    </BarChart>
  );
}

// ── Grouped / Stacked Bar Chart ─────────────────────────────────

function renderGroupedBarChart(spec: ChartSpec, colors: string[]): React.ReactElement {
  // Diverging bars (2A's diverging_bar: wins positive, losses negative)
  // straddle zero — a reference line makes that baseline visible instead of
  // the bars looking like they're floating.
  const diverging = hasNegativeValues(spec);
  return (
    <BarChart data={spec.data} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#F0EBE4" />
      <XAxis {...xAxisProps(spec)} />
      <YAxis {...yAxisProps(spec)} />
      <Tooltip contentStyle={tooltipStyle} />
      {spec.legend && <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />}
      {diverging && <ReferenceLine y={0} stroke="#8C7B6B" strokeWidth={1.5} />}
      {spec.series.map((s, i) => (
        <Bar
          key={s.key || s.name || i}
          dataKey={s.key || ''}
          name={s.name}
          fill={colors[i % colors.length]}
          stackId={s.stackId}
          radius={s.stackId ? undefined : [4, 4, 0, 0]}
          animationDuration={600}
        />
      ))}
    </BarChart>
  );
}

// ── Scatter Chart ───────────────────────────────────────────────

function renderScatterChart(spec: ChartSpec, colors: string[]): React.ReactElement {
  if (spec.series.length > 1) {
    // Grouped scatter — split data by group field
    return (
      <ScatterChart margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#F0EBE4" />
        <XAxis type="number" dataKey="x" name={spec.xAxis.label || 'X'} tick={{ fontSize: 12, fill: '#8C7B6B' }} />
        <YAxis type="number" dataKey="y" name={spec.yAxis.label || 'Y'} tick={{ fontSize: 12, fill: '#8C7B6B' }} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />
        {spec.series.map((s, i) => (
          <Scatter
            key={s.key || s.name || i}
            name={s.name}
            data={spec.data.filter((d: any) => d.group === s.key)}
            fill={colors[i % colors.length]}
            animationDuration={600}
          />
        ))}
      </ScatterChart>
    );
  }

  return (
    <ScatterChart margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#F0EBE4" />
      <XAxis type="number" dataKey="x" name={spec.xAxis.label || 'X'} tick={{ fontSize: 12, fill: '#8C7B6B' }} />
      <YAxis type="number" dataKey="y" name={spec.yAxis.label || 'Y'} tick={{ fontSize: 12, fill: '#8C7B6B' }} />
      <Tooltip contentStyle={tooltipStyle} />
      <Scatter
        name={spec.series[0]?.name || 'Data'}
        data={spec.data}
        fill={colors[0]}
        animationDuration={600}
      />
      {renderAnnotations(spec)}
    </ScatterChart>
  );
}

// ── Pie Chart ───────────────────────────────────────────────────

function renderPieChart(spec: ChartSpec, colors: string[]): React.ReactElement {
  // Slice-level text labels overlap once there are more than a handful of
  // slices — the backend sets showSliceLabels: false once it's grouped the
  // tail into "Other" (>5 slices), and legend + tooltip carry the info instead.
  const showLabels = spec.showSliceLabels !== false;

  return (
    <PieChart>
      <Pie
        data={spec.data}
        dataKey="value"
        nameKey="name"
        cx="50%"
        cy="50%"
        outerRadius={140}
        innerRadius={60}
        paddingAngle={2}
        label={showLabels ? (props: any) => `${props.name ?? ''} ${((props.percent ?? 0) * 100).toFixed(0)}%` : false}
        labelLine={showLabels ? { stroke: '#8C7B6B' } : false}
        animationDuration={800}
      >
        {spec.data.map((_: any, i: number) => (
          <Cell key={i} fill={colors[i % colors.length]} />
        ))}
      </Pie>
      <Tooltip contentStyle={tooltipStyle} />
      {spec.legend && <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />}
    </PieChart>
  );
}

// ── Area Chart ──────────────────────────────────────────────────

function renderAreaChart(spec: ChartSpec, colors: string[]): React.ReactElement {
  return (
    <AreaChart data={spec.data} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#F0EBE4" />
      <XAxis {...xAxisProps(spec)} />
      <YAxis {...yAxisProps(spec)} />
      <Tooltip contentStyle={tooltipStyle} />
      {spec.legend && <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />}
      {spec.series.map((s, i) => {
        const color = colors[i % colors.length];
        return (
          <Area
            key={s.key || s.name || i}
            type="monotone"
            dataKey={s.key || ''}
            name={s.name}
            stroke={color}
            fill={color}
            fillOpacity={0.25}
            strokeWidth={2}
            stackId={s.stackId}
            animationDuration={800}
          />
        );
      })}
      {renderAnnotations(spec)}
    </AreaChart>
  );
}

export default ChartRenderer;
