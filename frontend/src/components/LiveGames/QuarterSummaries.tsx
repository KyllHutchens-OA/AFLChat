import React, { useState, useEffect } from 'react';

interface QuarterScores {
  home: (number | null)[];
  away: (number | null)[];
}

interface QuarterSummariesProps {
  quarterSummaries: Record<string, string>;
  quarterScores?: QuarterScores;
}

const QuarterSummaries: React.FC<QuarterSummariesProps> = ({ quarterSummaries, quarterScores }) => {
  const quarters = Object.keys(quarterSummaries)
    .map(Number)
    .filter(q => q >= 1 && q <= 4)
    .sort((a, b) => a - b);

  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  // Auto-expand latest quarter, collapse others when new quarter arrives
  useEffect(() => {
    if (quarters.length > 0) {
      const latest = quarters[quarters.length - 1];
      setExpanded(new Set([latest]));
    }
  }, [quarters.length]);

  if (quarters.length === 0) {
    return null;
  }

  const toggleQuarter = (quarter: number) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(quarter)) {
        next.delete(quarter);
      } else {
        next.add(quarter);
      }
      return next;
    });
  };

  const getQuarterScore = (quarter: number): string | null => {
    if (!quarterScores) return null;
    const homeScore = quarterScores.home[quarter - 1];
    const awayScore = quarterScores.away[quarter - 1];
    if (homeScore == null || awayScore == null) return null;
    return `${homeScore}-${awayScore}`;
  };

  return (
    <div className="glass rounded-apple-xl p-6 shadow-apple-lg">
      <h3 className="text-xl font-semibold text-afl-warm-900 mb-4">
        Quarter Summaries
      </h3>
      <div className="space-y-3">
        {quarters.map((quarter) => {
          const isExpanded = expanded.has(quarter);
          const score = getQuarterScore(quarter);

          return (
            <div
              key={quarter}
              className="bg-afl-warm-50 rounded-apple overflow-hidden"
            >
              <button
                onClick={() => toggleQuarter(quarter)}
                className="w-full flex items-center gap-2 p-4 text-left hover:bg-afl-warm-100 transition-colors"
              >
                <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-afl-accent text-white text-xs font-bold flex-shrink-0">
                  Q{quarter}
                </span>
                <span className="text-sm font-semibold text-afl-warm-700">
                  Quarter {quarter}
                </span>
                {score && (
                  <span className="text-sm font-medium text-afl-warm-500 ml-1">
                    ({score})
                  </span>
                )}
                <svg
                  className={`w-4 h-4 text-afl-warm-400 ml-auto transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {isExpanded && (
                <p className="text-sm text-afl-warm-700 leading-relaxed px-4 pb-4 pl-[3.25rem]">
                  {quarterSummaries[String(quarter)]}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default QuarterSummaries;
