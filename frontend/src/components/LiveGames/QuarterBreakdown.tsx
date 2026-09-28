import React from 'react';
import type { QuarterBreakdownEntry, QuarterScores } from '../../contexts/LiveDataContext';

interface QuarterBreakdownProps {
  homeAbbr: string;
  awayAbbr: string;
  breakdown?: QuarterBreakdownEntry[] | null;
  quarterScores?: QuarterScores;
}

// Quarter-by-quarter scoreboard, AFL style: cumulative goals.behinds (total)
// at the end of each quarter. Falls back to totals-only when the full
// goals/behinds split isn't available (only set once a game migrates to
// `matches`).
const QuarterBreakdown: React.FC<QuarterBreakdownProps> = ({ homeAbbr, awayAbbr, breakdown, quarterScores }) => {
  const quarters = breakdown && breakdown.length > 0 ? breakdown : null;
  const totalsOnly = !quarters && quarterScores;

  if (!quarters && !totalsOnly) return null;

  const cell = (q: number) => {
    if (quarters) {
      const entry = quarters.find(e => e.quarter === q);
      if (!entry) return { home: '-', away: '-' };
      return {
        home: `${entry.home_goals}.${entry.home_behinds} (${entry.home_total})`,
        away: `${entry.away_goals}.${entry.away_behinds} (${entry.away_total})`,
      };
    }
    const home = quarterScores?.home[q - 1];
    const away = quarterScores?.away[q - 1];
    return { home: home == null ? '-' : `(${home})`, away: away == null ? '-' : `(${away})` };
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-afl-warm-500">
            <th className="text-left font-medium py-1 pr-3"></th>
            {[1, 2, 3, 4].map(q => (
              <th key={q} className="text-right font-medium py-1 px-2 tabular-nums">Q{q}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(['home', 'away'] as const).map(side => (
            <tr key={side} className="border-t border-afl-warm-100">
              <td className="py-2 pr-3 font-semibold text-afl-warm-900">
                {side === 'home' ? homeAbbr : awayAbbr}
              </td>
              {[1, 2, 3, 4].map(q => (
                <td key={q} className="text-right py-2 px-2 tabular-nums text-afl-warm-700">
                  {cell(q)[side]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default QuarterBreakdown;
