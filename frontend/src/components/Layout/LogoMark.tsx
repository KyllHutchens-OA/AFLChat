// Footy-NAC logo mark: a Sherrin in outline with "NAC" set in the ball's
// panel. Used in the nav and reused (bigger, animated) in the landing hero.
interface LogoMarkProps {
  className?: string;
  animate?: boolean;
}

const LogoMark: React.FC<LogoMarkProps> = ({ className = 'w-8 h-8', animate = false }) => (
  <svg
    viewBox="0 0 44 44"
    className={`${className} ${animate ? 'animate-sherrin-spin-in' : ''}`}
    role="img"
    aria-label="Footy-NAC logo"
  >
    <ellipse cx="22" cy="22" rx="20" ry="13" fill="#C8102E" stroke="#16130F" strokeWidth="1.5" />
    {/* seam */}
    <path d="M3 22 Q22 15 41 22" fill="none" stroke="#16130F" strokeWidth="1" opacity="0.3" />
    <path d="M3 22 Q22 29 41 22" fill="none" stroke="#16130F" strokeWidth="1" opacity="0.3" />
    {/* laces */}
    <line x1="19" y1="15.5" x2="25" y2="15.5" stroke="#16130F" strokeWidth="1.2" opacity="0.5" />
    <line x1="19" y1="28.5" x2="25" y2="28.5" stroke="#16130F" strokeWidth="1.2" opacity="0.5" />
    {/* NAC monogram in the panel */}
    <text
      x="22"
      y="24.5"
      textAnchor="middle"
      fontFamily="Anton, sans-serif"
      fontSize="9"
      fill="#F6F1E7"
      letterSpacing="0.5"
    >
      NAC
    </text>
  </svg>
);

export default LogoMark;
