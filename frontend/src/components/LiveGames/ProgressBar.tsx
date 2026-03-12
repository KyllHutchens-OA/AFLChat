import React from 'react';

interface ProgressBarProps {
  completePercent: number;
}

const ProgressBar: React.FC<ProgressBarProps> = ({ completePercent }) => {
  return (
    <div className="w-full">
      {/* Progress bar container */}
      <div className="w-full h-2 bg-apple-gray-200 rounded-full overflow-hidden">
        {/* Progress fill */}
        <div
          className="h-full bg-apple-blue-500 rounded-full transition-all duration-500 ease-apple"
          style={{ width: `${Math.min(100, Math.max(0, completePercent))}%` }}
        />
      </div>

      {/* Percentage label */}
      <p className="text-xs text-apple-gray-500 text-center mt-2">
        {Math.round(completePercent)}% complete
      </p>
    </div>
  );
};

export default ProgressBar;
