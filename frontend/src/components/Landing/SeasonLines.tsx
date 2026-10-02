// Two-series per-season line chart, plain inline SVG for the landing page's
// light cards. Draws one gridline and one year label per season.
interface Series {
  name: string;
  values: number[];
  color: string;
}

interface SeasonLinesProps {
  seasons: number[];
  a: Series;
  b: Series;
  width?: number;
  height?: number;
}

const PAD_X = 10;
const PAD_TOP = 8;
const PAD_BOTTOM = 18;

const SeasonLines: React.FC<SeasonLinesProps> = ({ seasons, a, b, width = 240, height = 96 }) => {
  const max = Math.max(...a.values, ...b.values) * 1.08;
  const plotH = height - PAD_TOP - PAD_BOTTOM;
  const stepX = (width - PAD_X * 2) / (seasons.length - 1);
  const x = (i: number) => PAD_X + i * stepX;
  const y = (v: number) => PAD_TOP + plotH - (v / max) * plotH;
  const points = (values: number[]) => values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');

  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        role="img"
        aria-label={`${a.name} and ${b.name} by season, ${seasons[0]} to ${seasons[seasons.length - 1]}`}
        className="overflow-visible"
      >
        {seasons.map((s, i) => (
          <g key={s}>
            <line x1={x(i)} y1={PAD_TOP} x2={x(i)} y2={PAD_TOP + plotH} stroke="#C3AC87" strokeOpacity={0.35} strokeDasharray="2,3" />
            <text x={x(i)} y={height - 4} textAnchor="middle" fontSize={9} fill="#8A7A62">
              {String(s).slice(2)}
            </text>
          </g>
        ))}
        {[a, b].map((s) => (
          <g key={s.name}>
            <polyline points={points(s.values)} fill="none" stroke={s.color} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
            {s.values.map((v, i) => (
              <circle key={i} cx={x(i)} cy={y(v)} r={2.5} fill={s.color} />
            ))}
          </g>
        ))}
      </svg>
      <div className="flex gap-4 mt-1 text-xs text-warm-700">
        {[a, b].map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5">
            <span className="w-3 h-0.5 rounded" style={{ backgroundColor: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
};

export default SeasonLines;
