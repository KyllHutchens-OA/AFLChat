import React from 'react';

export type AnimationState = 'idle' | 'walking' | 'jumping';
export type Direction = 'left' | 'right';

interface CharacterProps {
  x: number; // percentage 0-100
  direction: Direction;
  animationState: AnimationState;
  className?: string;
  speechBubble?: string | null;
}

export const Character: React.FC<CharacterProps> = ({
  x,
  direction,
  animationState,
  className = '',
  speechBubble = null,
}) => {
  const isWalking = animationState === 'walking';
  const isJumping = animationState === 'jumping';
  const isIdle = animationState === 'idle';

  return (
    <div
      className={`absolute bottom-0 transition-transform ${className}`}
      style={{
        left: `${x}%`,
        transform: `translateX(-50%)`,
      }}
    >
      {/* Speech bubble */}
      {speechBubble && (
        <div
          className="absolute -top-40 left-1/2 -translate-x-1/2 w-64 animate-fade-in"
          style={{ transform: 'translateX(-50%)' }}
        >
          <div className="relative bg-white rounded-2xl px-4 py-3 shadow-lg border-2 border-gray-200">
            <p className="text-gray-800 text-center text-sm font-medium">{speechBubble}</p>
            {/* Speech bubble tail */}
            <div className="absolute -bottom-3 left-1/2 -translate-x-1/2">
              <div className="w-0 h-0 border-l-8 border-r-8 border-t-12 border-l-transparent border-r-transparent border-t-white"></div>
            </div>
            <div className="absolute -bottom-[14px] left-1/2 -translate-x-1/2">
              <div className="w-0 h-0 border-l-8 border-r-8 border-t-12 border-l-transparent border-r-transparent border-t-gray-200"></div>
            </div>
          </div>
        </div>
      )}
      <div
        className={`${isJumping ? 'animate-jump' : ''} ${isIdle ? 'animate-idle-bounce' : ''}`}
        style={{ transform: direction === 'left' ? 'scaleX(-1)' : '' }}
      >
        <svg
          width="240"
          height="420"
          viewBox="0 0 80 140"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="drop-shadow-lg"
        >
          {/* Hair (back layer - fuller) */}
          <ellipse
            cx="40"
            cy="18"
            rx="24"
            ry="20"
            fill="#5D4037"
          />

          {/* Head */}
          <ellipse
            cx="40"
            cy="28"
            rx="18"
            ry="20"
            fill="#FDBF6F"
          />

          {/* Hair (front - fuller swooped style) */}
          <path
            d="M18 24 C16 10, 40 2, 55 8 C62 12, 64 20, 62 26 C60 18, 50 8, 40 6 C28 6, 18 14, 18 24"
            fill="#5D4037"
          />
          {/* Hair volume left side */}
          <ellipse
            cx="28"
            cy="14"
            rx="12"
            ry="8"
            fill="#5D4037"
          />
          {/* Hair volume right side */}
          <ellipse
            cx="48"
            cy="12"
            rx="10"
            ry="7"
            fill="#5D4037"
          />
          {/* Hair top volume */}
          <ellipse
            cx="38"
            cy="8"
            rx="14"
            ry="6"
            fill="#5D4037"
          />

          {/* Glasses */}
          <rect
            x="26"
            y="24"
            width="12"
            height="10"
            rx="2"
            fill="none"
            stroke="#1F2937"
            strokeWidth="2"
          />
          <rect
            x="42"
            y="24"
            width="12"
            height="10"
            rx="2"
            fill="none"
            stroke="#1F2937"
            strokeWidth="2"
          />
          {/* Glasses bridge */}
          <line
            x1="38"
            y1="28"
            x2="42"
            y2="28"
            stroke="#1F2937"
            strokeWidth="2"
          />
          {/* Glasses arms */}
          <line
            x1="26"
            y1="28"
            x2="22"
            y2="26"
            stroke="#1F2937"
            strokeWidth="2"
          />
          <line
            x1="54"
            y1="28"
            x2="58"
            y2="26"
            stroke="#1F2937"
            strokeWidth="2"
          />

          {/* Eyes */}
          <circle cx="32" cy="29" r="2" fill="#1F2937" />
          <circle cx="48" cy="29" r="2" fill="#1F2937" />

          {/* Smile */}
          <path
            d="M35 38 Q40 42, 45 38"
            fill="none"
            stroke="#1F2937"
            strokeWidth="2"
            strokeLinecap="round"
          />

          {/* Neck */}
          <rect x="35" y="46" width="10" height="6" fill="#FDBF6F" />

          {/* Body - White Dress Shirt */}
          <rect
            x="24"
            y="50"
            width="32"
            height="40"
            rx="4"
            fill="#F8FAFC"
            stroke="#E2E8F0"
            strokeWidth="1"
          />

          {/* Shirt collar */}
          <path
            d="M32 50 L40 58 L48 50"
            fill="#F8FAFC"
            stroke="#E2E8F0"
            strokeWidth="1"
          />

          {/* Shirt buttons */}
          <circle cx="40" cy="62" r="2" fill="#CBD5E1" />
          <circle cx="40" cy="72" r="2" fill="#CBD5E1" />
          <circle cx="40" cy="82" r="2" fill="#CBD5E1" />

          {/* Left Arm */}
          <g className={isWalking ? 'animate-arm-swing-left origin-top' : ''}>
            <rect
              x="12"
              y="52"
              width="14"
              height="32"
              rx="6"
              fill="#F8FAFC"
              stroke="#E2E8F0"
              strokeWidth="1"
            />
            {/* Hand */}
            <ellipse cx="19" cy="86" rx="6" ry="5" fill="#FDBF6F" />
          </g>

          {/* Right Arm */}
          <g className={isWalking ? 'animate-arm-swing-right origin-top' : ''}>
            <rect
              x="54"
              y="52"
              width="14"
              height="32"
              rx="6"
              fill="#F8FAFC"
              stroke="#E2E8F0"
              strokeWidth="1"
            />
            {/* Hand */}
            <ellipse cx="61" cy="86" rx="6" ry="5" fill="#FDBF6F" />
          </g>

          {/* Pants - Black */}
          <rect
            x="24"
            y="88"
            width="32"
            height="8"
            fill="#1F2937"
          />

          {/* Left Leg */}
          <g className={isWalking ? 'animate-leg-step-left origin-top' : ''}>
            <rect
              x="24"
              y="94"
              width="14"
              height="36"
              rx="4"
              fill="#1F2937"
            />
            {/* Shoe */}
            <ellipse cx="31" cy="132" rx="8" ry="4" fill="#374151" />
          </g>

          {/* Right Leg */}
          <g className={isWalking ? 'animate-leg-step-right origin-top' : ''}>
            <rect
              x="42"
              y="94"
              width="14"
              height="36"
              rx="4"
              fill="#1F2937"
            />
            {/* Shoe */}
            <ellipse cx="49" cy="132" rx="8" ry="4" fill="#374151" />
          </g>
        </svg>
      </div>
    </div>
  );
};
