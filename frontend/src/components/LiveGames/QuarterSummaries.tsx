import React from 'react';

interface QuarterSummariesProps {
  quarterSummaries: Record<string, string>;
}

const QuarterSummaries: React.FC<QuarterSummariesProps> = ({ quarterSummaries }) => {
  const quarters = Object.keys(quarterSummaries)
    .map(Number)
    .filter(q => q >= 1 && q <= 4)
    .sort((a, b) => a - b);

  if (quarters.length === 0) {
    return null;
  }

  return (
    <div className="glass rounded-apple-xl p-6 shadow-apple-lg">
      <h3 className="text-xl font-semibold text-apple-gray-900 mb-4">
        Quarter Summaries
      </h3>
      <div className="space-y-3">
        {quarters.map((quarter) => (
          <div
            key={quarter}
            className="bg-apple-gray-50 rounded-apple p-4"
          >
            <div className="flex items-center gap-2 mb-1.5">
              <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-apple-blue-500 text-white text-xs font-bold">
                Q{quarter}
              </span>
              <span className="text-sm font-semibold text-apple-gray-700">
                Quarter {quarter}
              </span>
            </div>
            <p className="text-sm text-apple-gray-700 leading-relaxed pl-9">
              {quarterSummaries[String(quarter)]}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default QuarterSummaries;
