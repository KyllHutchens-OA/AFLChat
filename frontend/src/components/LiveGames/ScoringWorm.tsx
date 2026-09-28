import React, { useId, useMemo } from 'react';
import type { GameEvent, QuarterScores } from '../../contexts/LiveDataContext';

interface ScoringWormProps {
  events: GameEvent[];
  quarterScores?: QuarterScores;
  homeAbbr: string;
  awayAbbr: string;
  homeColor?: string;
  awayColor?: string;
}

interface WormPoint {
  x: number; // 0-1 normalized
  margin: number; // home - away
  quarter: number;
}

const WIDTH = 640;
const HEIGHT = 180;
const PAD_X = 8;
const PAD_Y = 16;

// Builds worm points from scoring events when available, falling back to the
// four quarter checkpoints (always present) when event-level detail wasn't
// captured for this game (e.g. older finals).
const buildPoints = (events: GameEvent[], quarterScores?: QuarterScores): WormPoint[] => {
  const scoring = (events || [])
    .filter(e => e.event_type === 'goal' || e.event_type === 'behind')
    .slice()
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  if (scoring.length > 0) {
    const byQuarter = new Map<number, GameEvent[]>();
    scoring.forEach(e => {
      const q = e.quarter || 1;
      if (!byQuarter.has(q)) byQuarter.set(q, []);
      byQuarter.get(q)!.push(e);
    });
    const points: WormPoint[] = [{ x: 0, margin: 0, quarter: 0 }];
    for (let q = 1; q <= 4; q++) {
      const qEvents = byQuarter.get(q) || [];
      qEvents.forEach((e, i) => {
        const x = (q - 1) / 4 + ((i + 1) / (qEvents.length + 1)) * (1 / 4);
        points.push({ x, margin: e.home_score_after - e.away_score_after, quarter: q });
      });
    }
    return points;
  }

  // Coarse fallback: just the 4 quarter-end margins
  if (quarterScores) {
    const points: WormPoint[] = [{ x: 0, margin: 0, quarter: 0 }];
    for (let q = 1; q <= 4; q++) {
      const home = quarterScores.home[q - 1];
      const away = quarterScores.away[q - 1];
      if (home == null || away == null) continue;
      points.push({ x: q / 4, margin: home - away, quarter: q });
    }
    return points;
  }

  return [];
};

const ScoringWorm: React.FC<ScoringWormProps> = ({
  events, quarterScores, homeAbbr, awayAbbr, homeColor = '#CC2936', awayColor = '#4A4A4A',
}) => {
  const clipId = useId();
  const points = useMemo(() => buildPoints(events, quarterScores), [events, quarterScores]);

  if (points.length < 2) {
    return null;
  }

  const maxMargin = Math.max(8, ...points.map(p => Math.abs(p.margin)));
  const innerW = WIDTH - PAD_X * 2;
  const innerH = HEIGHT - PAD_Y * 2;
  const centerY = PAD_Y + innerH / 2;

  const toXY = (p: WormPoint) => ({
    x: PAD_X + p.x * innerW,
    y: centerY - (p.margin / maxMargin) * (innerH / 2),
  });

  const coords = points.map(toXY);
  const linePath = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
  const areaPath = `${linePath} L ${coords[coords.length - 1].x.toFixed(1)},${centerY} L ${coords[0].x.toFixed(1)},${centerY} Z`;

  return (
    <div>
      <div className="flex items-center justify-between text-xs font-medium text-afl-warm-500 mb-1">
        <span>{homeAbbr} lead</span>
        <span>Scoring worm</span>
        <span>{awayAbbr} lead</span>
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full h-auto" role="img" aria-label={`Margin over time, ${homeAbbr} versus ${awayAbbr}`}>
        <defs>
          <clipPath id={`${clipId}-above`}>
            <rect x={0} y={0} width={WIDTH} height={centerY} />
          </clipPath>
          <clipPath id={`${clipId}-below`}>
            <rect x={0} y={centerY} width={WIDTH} height={HEIGHT - centerY} />
          </clipPath>
        </defs>

        {/* Quarter gridlines */}
        {[0.25, 0.5, 0.75].map(f => (
          <line
            key={f}
            x1={PAD_X + f * innerW} x2={PAD_X + f * innerW}
            y1={PAD_Y} y2={HEIGHT - PAD_Y}
            stroke="#E0D5C8" strokeDasharray="3 3"
          />
        ))}

        {/* Zero line (margin flips) */}
        <line x1={PAD_X} x2={WIDTH - PAD_X} y1={centerY} y2={centerY} stroke="#C8B9A8" strokeWidth={1} />

        {/* Diverging fill: home colour above zero, away colour below */}
        <path d={areaPath} fill={homeColor} opacity={0.18} clipPath={`url(#${clipId}-above)`} />
        <path d={areaPath} fill={awayColor} opacity={0.18} clipPath={`url(#${clipId}-below)`} />

        {/* The worm itself */}
        <path d={linePath} fill="none" stroke="#16130F" strokeWidth={2} strokeLinejoin="round" />
      </svg>
    </div>
  );
};

export default ScoringWorm;
