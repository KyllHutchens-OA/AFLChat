import React from 'react';

interface SelectionBubbleProps {
  label: string;
  position: 'left' | 'right';
  onClick: () => void;
  isActive: boolean;
  icon: 'resume' | 'afl';
}

export const SelectionBubble: React.FC<SelectionBubbleProps> = ({
  label,
  position,
  onClick,
  isActive,
  icon,
}) => {
  return (
    <button
      onClick={onClick}
      className={`
        absolute top-8 animate-float
        px-10 py-6 rounded-3xl
        bg-white/90 backdrop-blur-sm
        border-3 border-transparent
        shadow-xl
        transition-all duration-300
        hover:scale-110 hover:shadow-2xl
        focus:outline-none focus:ring-4 focus:ring-blue-300
        cursor-pointer
        ${position === 'left' ? 'left-[12%]' : 'right-[12%]'}
        ${isActive ? 'border-yellow-400 shadow-yellow-400/50' : 'hover:border-blue-400'}
      `}
      style={{
        animationDelay: position === 'left' ? '0s' : '0.5s',
      }}
    >
      <div className="flex flex-col items-center gap-3">
        {icon === 'resume' ? (
          <svg
            className="w-14 h-14 text-blue-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        ) : (
          <svg
            className="w-14 h-14 text-emerald-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
        )}
        <span className="text-2xl font-semibold text-gray-800">{label}</span>
      </div>
    </button>
  );
};
