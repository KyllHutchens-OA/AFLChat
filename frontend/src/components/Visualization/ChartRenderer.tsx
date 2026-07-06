import React from 'react';
import {
  ResponsiveContainer,
  LineChart, Line,
  BarChart, Bar,
  ScatterChart, Scatter,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ReferenceDot, Label,
  ErrorBar,
  ComposedChart,
} from 'recharts';
import { chartSpecSchema, ChartSpec, DEFAULT_COLORS } from '../../types/chartSpec';
import DataTable from './DataTable';

interface ChartRendererProps {
  spec: any;
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

// ── Main Component ──────────────────────────────────────────────

const ChartRenderer: React.FC<ChartRendererProps> = ({ spec }) => {
  if (!spec) return null;

  const result = chartSpecSchema.safeParse(spec);

  if (!result.success) {
    // Spec doesn't match the shape we know how to chart (missing chartType,
    // empty/malformed data, etc). Fall back to a table if there's usable data
    // to show, otherwise render nothing — never crash on a bad spec.
    const rawData = Array.isArray(spec?.data) ? spec.data : null;
    if (rawData && rawData.length > 0) {
      return <DataTable data={rawData} title={typeof spec?.title === 'string' ? spec.title : undefined} />;
    }
    return null;
  }

  const s = result.data;

  // Empty dataset: nothing sensible to chart. This is also reachable directly
  // since the schema enforces data.min(1), but keep an explicit guard so the
  // intent is obvious and this stays safe if the schema ever relaxes that rule.
  if (!s.data.length) return null;

  if (!s.chartType) {
    return <DataTable data={s.data} title={s.title} />;
  }

  const colors = s.colors && s.colors.length ? s.colors : DEFAULT_COLORS;

  return (
    <div className="w-full card-apple p-6 my-4">
      {s.title && (
        <h3 className="text-base font-semibold text-[#3D2E1F] mb-4 text-center">
          {s.title}
        </h3>
      )}
      <ResponsiveContainer width="100%" height={400}>
        {renderChart(s, colors)}
      </ResponsiveContainer>
    </div>
  );
};

// ── Chart Router ────────────────────────────────────────────────

function renderChart(spec: ChartSpec, colors: string[]): React.ReactElement {
  switch (spec.chartType) {
    case 'line':
      return renderLineChart(spec, colors);
    case 'bar':
      return renderBarChart(spec, colors);
    case 'horizontal_bar':
      return renderHorizontalBarChart(spec, colors);
    case 'grouped_bar':
    case 'groupedBar':
      return renderGroupedBarChart(spec, colors);
    case 'stacked_bar':
      return renderGroupedBarChart(spec, colors); // same component, series have stackId
    case 'scatter':
      return renderScatterChart(spec, colors);
    case 'pie':
      return renderPieChart(spec, colors);
    case 'box':
      return renderBoxChart(spec, colors);
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

  return (
    <ChartComponent data={spec.data} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#F0EBE4" />
      <XAxis {...xAxisProps(spec)} />
      <YAxis {...yAxisProps(spec)} />
      <Tooltip contentStyle={tooltipStyle} />
      {spec.legend && <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />}
      {spec.series.map((s, i) => {
        const color = s.color || colors[i % colors.length];
        return (
          <Line
            key={s.key || s.name || i}
            type="monotone"
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
          fill={s.color || colors[i % colors.length]}
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
          fill={s.color || colors[i % colors.length]}
          radius={[0, 4, 4, 0]}
          animationDuration={600}
        />
      ))}
    </BarChart>
  );
}

// ── Grouped / Stacked Bar Chart ─────────────────────────────────

function renderGroupedBarChart(spec: ChartSpec, colors: string[]): React.ReactElement {
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
          fill={s.color || colors[i % colors.length]}
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
            fill={s.color || colors[i % colors.length]}
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
        label={(props: any) => `${props.name ?? ''} ${((props.percent ?? 0) * 100).toFixed(0)}%`}
        labelLine={{ stroke: '#8C7B6B' }}
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

// ── Box Chart (rendered as bar with error bars for IQR) ─────────

function renderBoxChart(spec: ChartSpec, colors: string[]): React.ReactElement {
  // Data has: x, median, q1, q3, min, max
  // We show median as bar height, with error bars from q1 to q3
  const processedData = spec.data.map((d: any) => ({
    ...d,
    errorLow: d.median - d.q1,
    errorHigh: d.q3 - d.median,
  }));

  return (
    <BarChart data={processedData} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#F0EBE4" />
      <XAxis dataKey="x" tick={{ fontSize: 12, fill: '#8C7B6B' }} tickLine={false} axisLine={{ stroke: '#E8DDD3' }} />
      <YAxis tick={{ fontSize: 12, fill: '#8C7B6B' }} tickLine={false} axisLine={{ stroke: '#E8DDD3' }} />
      <Tooltip
        contentStyle={tooltipStyle}
        formatter={(_: any, __: any, props: any) => {
          const d = props.payload;
          return [`Median: ${d.median}, Q1: ${d.q1}, Q3: ${d.q3}, Min: ${d.min}, Max: ${d.max}`, ''];
        }}
      />
      <Bar dataKey="median" fill={colors[0]} radius={[4, 4, 0, 0]} animationDuration={600}>
        <ErrorBar dataKey="errorHigh" direction="y" width={8} stroke={colors[1] || colors[0]} />
      </Bar>
    </BarChart>
  );
}

export default ChartRenderer;
