// Single-series sparkline, plain inline SVG (no chart library on the landing
// page's first paint).
interface SparklineProps {
  values: number[];
  color: string;
  width?: number;
  height?: number;
}

const Sparkline: React.FC<SparklineProps> = ({ values, color, width = 200, height = 56 }) => {
  const max = Math.max(...values) * 1.1;
  const min = Math.min(0, ...values);
  const range = max - min || 1;
  const stepX = width / (values.length - 1);
  const points = values
    .map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label="Career trend">
      <polyline points={points} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

export default Sparkline;
