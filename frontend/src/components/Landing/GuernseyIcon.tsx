// Plain SVG guernsey silhouette in club colours — no logos, stripes/hoops/sash
// patterns only, so this stays clear of club trademarks.
export type GuernseyPattern = 'stripes' | 'hoops' | 'sash' | 'solid' | 'halves';

interface GuernseyIconProps {
  primary: string;
  secondary: string;
  pattern: GuernseyPattern;
  className?: string;
}

// Sleeveless jumper outline (front view), shared by every club.
const JUMPER_PATH =
  'M30 6 C34 2 42 0 50 0 C58 0 66 2 70 6 L88 16 L80 34 L70 28 L70 100 C70 106 65 110 58 110 L42 110 C35 110 30 106 30 100 L30 28 L20 34 L12 16 Z';

const GuernseyIcon: React.FC<GuernseyIconProps> = ({ primary, secondary, pattern, className }) => {
  const clipId = `guernsey-clip-${primary.replace('#', '')}-${secondary.replace('#', '')}-${pattern}`;

  const renderFill = () => {
    switch (pattern) {
      case 'stripes':
        return (
          <g clipPath={`url(#${clipId})`}>
            <rect x="0" y="0" width="100" height="110" fill={primary} />
            {[0, 2, 4, 6].map((i) => (
              <rect key={i} x={14 + i * 11} y="0" width="6" height="110" fill={secondary} />
            ))}
          </g>
        );
      case 'hoops':
        return (
          <g clipPath={`url(#${clipId})`}>
            <rect x="0" y="0" width="100" height="110" fill={secondary} />
            {[0, 1, 2, 3].map((i) => (
              <rect key={i} x="0" y={14 + i * 22} width="100" height="11" fill={primary} />
            ))}
          </g>
        );
      case 'sash':
        return (
          <g clipPath={`url(#${clipId})`}>
            <rect x="0" y="0" width="100" height="110" fill={primary} />
            <g transform="rotate(35 50 55)">
              <rect x="-30" y="42" width="160" height="26" fill={secondary} />
            </g>
          </g>
        );
      case 'halves':
        return (
          <g clipPath={`url(#${clipId})`}>
            <rect x="0" y="0" width="50" height="110" fill={primary} />
            <rect x="50" y="0" width="50" height="110" fill={secondary} />
          </g>
        );
      case 'solid':
      default:
        return (
          <g clipPath={`url(#${clipId})`}>
            <rect x="0" y="0" width="100" height="110" fill={primary} />
            <rect x="30" y="0" width="40" height="10" fill={secondary} />
          </g>
        );
    }
  };

  return (
    <svg viewBox="0 0 100 112" className={className} aria-hidden="true">
      <defs>
        <clipPath id={clipId}>
          <path d={JUMPER_PATH} />
        </clipPath>
      </defs>
      {renderFill()}
      <path d={JUMPER_PATH} fill="none" stroke="#16130F" strokeOpacity="0.25" strokeWidth="1.5" />
    </svg>
  );
};

export default GuernseyIcon;
