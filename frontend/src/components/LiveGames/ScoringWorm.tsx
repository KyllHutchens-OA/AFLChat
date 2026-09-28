import React, { useId, useMemo } from 'react';
import type { GameEvent, QuarterScores } from '../../contexts/LiveDataContext';

interface ScoringWormProps {
  events: GameEvent[];
  quarterScores?: QuarterScores;
  homeAbbr: string;
  awayAbbr: string;
  homeColor?: string;
  awayColor?: string;
  // The scoreboard's final score, e.g. `game.home_score` / `game.away_score`.
  // This is the one field that's always kept in sync at full time (see
  // matches-vs-live_games sync), so it anchors the "final margin" label even
  // when quarter_scores or the event log are stale or incomplete.
  finalHomeScore?: number;
  finalAwayScore?: number;
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
const buildPoints = (
  events: GameEvent[],
  quarterScores?: QuarterScores,
  finalHomeScore?: number,
  finalAwayScore?: number,
): WormPoint[] => {
  const scoring = (events || [])
    .filter(e => e.event_type === 'goal' || e.event_type === 'behind')
    .slice()
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  let points: WormPoint[];

  if (scoring.length > 0) {
    const byQuarter = new Map<number, GameEvent[]>();
    scoring.forEach(e => {
      const q = e.quarter || 1;
      if (!byQuarter.has(q)) byQuarter.set(q, []);
      byQuarter.get(q)!.push(e);
    });
    points = [{ x: 0, margin: 0, quarter: 0 }];
    for (let q = 1; q <= 4; q++) {
      const qEvents = byQuarter.get(q) || [];
      qEvents.forEach((e, i) => {
        const x = (q - 1) / 4 + ((i + 1) / (qEvents.length + 1)) * (1 / 4);
        points.push({ x, margin: e.home_score_after - e.away_score_after, quarter: q });
      });
    }
  } else if (quarterScores) {
    // Coarse fallback: just the 4 quarter-end margins
    points = [{ x: 0, margin: 0, quarter: 0 }];
    for (let q = 1; q <= 4; q++) {
      const home = quarterScores.home[q - 1];
      const away = quarterScores.away[q - 1];
      if (home == null || away == null) continue;
      points.push({ x: q / 4, margin: home - away, quarter: q });
    }
  } else {
    points = [];
  }

  // Neither the event log nor quarter_scores are guaranteed to have caught
  // up with a game's true final score (a late behind that never got a
  // socket event, a stale quarter cache on a replayed game). The top-level
  // score is the one field kept in sync at full time, so when it's given,
  // it always wins for the endpoint — otherwise the "final margin" label
  // could show a wrong score.
  if (finalHomeScore != null && finalAwayScore != null && points.length > 0) {
    const trueFinalMargin = finalHomeScore - finalAwayScore;
    const last = points[points.length - 1];
    if (last.x < 1 || last.margin !== trueFinalMargin) {
      points.push({ x: 1, margin: trueFinalMargin, quarter: 4 });
    }
  }

  return points;
};

const ScoringWorm: React.FC<ScoringWormProps> = ({
  events, quarterScores, homeAbbr, awayAbbr, homeColor = '#C8102E', awayColor = '#544539',
  finalHomeScore, finalAwayScore,
}) => {
  const clipId = useId();
  const points = useMemo(
    () => buildPoints(events, quarterScores, finalHomeScore, finalAwayScore),
    [events, quarterScores, finalHomeScore, finalAwayScore],
  );

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

  const finalMargin = points[points.length - 1].margin;
  const finalPoint = coords[coords.length - 1];
  const marginLabel = finalMargin === 0 ? 'Scores level' : `${finalMargin > 0 ? homeAbbr : awayAbbr} by ${Math.abs(finalMargin)}`;
  // Keep the end label inside the chart when the margin sits near an edge.
  const labelY = Math.min(Math.max(finalPoint.y, PAD_Y + 10), HEIGHT - PAD_Y - 6);

  return (
    <div>
      <p className="section-label mb-1">Scoring worm</p>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full h-auto" role="img" aria-label={`Margin over time, ${homeAbbr} versus ${awayAbbr}. Final: ${marginLabel}.`}>
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
            stroke="#DCCBAE" strokeDasharray="3 3"
          />
        ))}

        {/* Axis labels: the vertical position, not left/right, carries the
            lead — home above the zero line, away below it. */}
        <text x={PAD_X} y={PAD_Y - 4} fontSize={10} fontWeight={600} fill={homeColor}>
          {homeAbbr} lead
        </text>
        <text x={PAD_X} y={HEIGHT - 5} fontSize={10} fontWeight={600} fill={awayColor}>
          {awayAbbr} lead
        </text>

        {/* Zero line (margin flips) */}
        <line x1={PAD_X} x2={WIDTH - PAD_X} y1={centerY} y2={centerY} stroke="#C3AC87" strokeWidth={1} />

        {/* Diverging fill: home colour above zero, away colour below */}
        <path d={areaPath} fill={homeColor} opacity={0.18} clipPath={`url(#${clipId}-above)`} />
        <path d={areaPath} fill={awayColor} opacity={0.18} clipPath={`url(#${clipId}-below)`} />

        {/* The worm itself */}
        <path d={linePath} fill="none" stroke="#16130F" strokeWidth={2} strokeLinejoin="round" />

        {/* Final margin, at the end of the line */}
        <circle cx={finalPoint.x} cy={finalPoint.y} r={3.5} fill="#16130F" />
        <text
          x={finalPoint.x - 8}
          y={labelY}
          textAnchor="end"
          fontSize={11}
          fontWeight={700}
          fill="#16130F"
        >
          {marginLabel}
        </text>
      </svg>
    </div>
  );
};

export default ScoringWorm;
