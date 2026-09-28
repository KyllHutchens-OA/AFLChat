// Lightweight quarter-by-quarter score chart, drawn as plain inline SVG so
// the landing page never has to load Recharts on first paint. Sits on the
// scoreboard's ink background, so dark club colours (navy, maroon, purple)
// get lightened until they clear a legible contrast ratio.
import { legibleOnDark } from '../../utils/color';

interface TeamLine {
  quarters: number[];
  primary: string;
}

interface MiniQuarterChartProps {
  home: TeamLine;
  away: TeamLine;
  width?: number;
  height?: number;
}

const toPoints = (quarters: number[], max: number, width: number, height: number) => {
  const stepX = width / (quarters.length - 1 + 0.4);
  return quarters
    .map((v, i) => {
      const x = 8 + i * stepX;
      const y = height - 8 - (v / max) * (height - 16);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
};

const MiniQuarterChart: React.FC<MiniQuarterChartProps> = ({ home, away, width = 220, height = 90 }) => {
  const max = Math.max(...home.quarters, ...away.quarters) * 1.08;
  const homePoints = toPoints(home.quarters, max, width, height);
  const awayPoints = toPoints(away.quarters, max, width, height);
  const homeStroke = legibleOnDark(home.primary);
  const awayStroke = legibleOnDark(away.primary);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      role="img"
      aria-label="Cumulative score by quarter for both teams"
      className="overflow-visible"
    >
      {/* quarter gridlines: brighter than the ink background so they read as
          structure, not noise */}
      {[0, 1, 2, 3].map((q) => (
        <line
          key={q}
          x1={8 + q * (width / 3.4)}
          y1={4}
          x2={8 + q * (width / 3.4)}
          y2={height - 6}
          stroke="#FFFFFF"
          strokeOpacity={0.18}
          strokeWidth={1}
          strokeDasharray="2,3"
        />
      ))}
      <polyline points={awayPoints} fill="none" stroke={awayStroke} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
      <polyline points={homePoints} fill="none" stroke={homeStroke} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

export default MiniQuarterChart;
