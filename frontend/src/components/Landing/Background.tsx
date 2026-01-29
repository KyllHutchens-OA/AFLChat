import React from 'react';

export const Background: React.FC = () => {
  return (
    <svg
      className="absolute inset-0 w-full h-full"
      viewBox="0 0 800 400"
      preserveAspectRatio="xMidYMax slice"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Wall */}
      <rect x="0" y="0" width="800" height="320" fill="#E8E4DF" />

      {/* Wall trim */}
      <rect x="0" y="300" width="800" height="20" fill="#D4CFC9" />

      {/* Floor - Wood pattern */}
      <rect x="0" y="320" width="800" height="80" fill="#8B7355" />
      {/* Floor boards */}
      <line x1="0" y1="340" x2="800" y2="340" stroke="#7A6548" strokeWidth="1" />
      <line x1="0" y1="360" x2="800" y2="360" stroke="#7A6548" strokeWidth="1" />
      <line x1="0" y1="380" x2="800" y2="380" stroke="#7A6548" strokeWidth="1" />
      {/* Vertical board lines */}
      <line x1="100" y1="320" x2="100" y2="400" stroke="#7A6548" strokeWidth="0.5" />
      <line x1="200" y1="320" x2="200" y2="400" stroke="#7A6548" strokeWidth="0.5" />
      <line x1="300" y1="320" x2="300" y2="400" stroke="#7A6548" strokeWidth="0.5" />
      <line x1="400" y1="320" x2="400" y2="400" stroke="#7A6548" strokeWidth="0.5" />
      <line x1="500" y1="320" x2="500" y2="400" stroke="#7A6548" strokeWidth="0.5" />
      <line x1="600" y1="320" x2="600" y2="400" stroke="#7A6548" strokeWidth="0.5" />
      <line x1="700" y1="320" x2="700" y2="400" stroke="#7A6548" strokeWidth="0.5" />

      {/* Bookshelf - Left side */}
      <g>
        {/* Shelf frame */}
        <rect x="30" y="100" width="120" height="220" fill="#5D4037" rx="2" />
        <rect x="35" y="105" width="110" height="210" fill="#4E342E" rx="2" />

        {/* Shelf dividers */}
        <rect x="35" y="155" width="110" height="6" fill="#5D4037" />
        <rect x="35" y="210" width="110" height="6" fill="#5D4037" />
        <rect x="35" y="265" width="110" height="6" fill="#5D4037" />

        {/* Books - Top shelf */}
        <rect x="40" y="110" width="12" height="42" fill="#EF4444" rx="1" />
        <rect x="54" y="115" width="10" height="37" fill="#3B82F6" rx="1" />
        <rect x="66" y="108" width="14" height="44" fill="#10B981" rx="1" />
        <rect x="82" y="112" width="8" height="40" fill="#F59E0B" rx="1" />
        <rect x="92" y="118" width="12" height="34" fill="#8B5CF6" rx="1" />
        <rect x="106" y="110" width="10" height="42" fill="#EC4899" rx="1" />
        <rect x="118" y="114" width="14" height="38" fill="#06B6D4" rx="1" />

        {/* Books - Second shelf */}
        <rect x="42" y="164" width="15" height="42" fill="#6366F1" rx="1" />
        <rect x="59" y="168" width="10" height="38" fill="#F97316" rx="1" />
        <rect x="71" y="162" width="12" height="44" fill="#14B8A6" rx="1" />
        <rect x="85" y="166" width="18" height="40" fill="#DC2626" rx="1" />
        <rect x="105" y="170" width="8" height="36" fill="#2563EB" rx="1" />
        <rect x="115" y="163" width="16" height="43" fill="#7C3AED" rx="1" />

        {/* Books - Third shelf */}
        <rect x="38" y="220" width="14" height="42" fill="#059669" rx="1" />
        <rect x="54" y="224" width="12" height="38" fill="#DB2777" rx="1" />
        <rect x="68" y="218" width="10" height="44" fill="#0891B2" rx="1" />
        <rect x="80" y="222" width="16" height="40" fill="#CA8A04" rx="1" />
        <rect x="98" y="226" width="8" height="36" fill="#9333EA" rx="1" />
        <rect x="108" y="219" width="14" height="43" fill="#E11D48" rx="1" />
        <rect x="124" y="223" width="10" height="39" fill="#0D9488" rx="1" />

        {/* Small plant on shelf */}
        <ellipse cx="135" y="107" rx="8" ry="6" fill="#166534" />
        <rect x="131" y="107" width="8" height="8" fill="#92400E" rx="1" />
      </g>

      {/* Desk - Right side */}
      <g>
        {/* Desk top */}
        <rect x="550" y="230" width="200" height="12" fill="#78350F" rx="2" />
        <rect x="550" y="236" width="200" height="4" fill="#92400E" />

        {/* Desk front panel */}
        <rect x="560" y="242" width="180" height="70" fill="#92400E" rx="2" />

        {/* Desk legs */}
        <rect x="560" y="312" width="8" height="8" fill="#78350F" />
        <rect x="732" y="312" width="8" height="8" fill="#78350F" />

        {/* Desk drawer handles */}
        <rect x="620" y="265" width="20" height="4" fill="#B45309" rx="1" />
        <rect x="620" y="290" width="20" height="4" fill="#B45309" rx="1" />

        {/* Monitor */}
        <rect x="620" y="170" width="80" height="55" fill="#1F2937" rx="3" />
        <rect x="624" y="174" width="72" height="47" fill="#60A5FA" rx="2" />
        <rect x="656" y="225" width="8" height="8" fill="#374151" />
        <rect x="640" y="230" width="40" height="4" fill="#374151" rx="1" />

        {/* Keyboard */}
        <rect x="610" y="210" width="50" height="18" fill="#374151" rx="2" />
        <rect x="612" y="212" width="46" height="14" fill="#4B5563" rx="1" />

        {/* Coffee mug */}
        <ellipse cx="580" cy="225" rx="10" ry="4" fill="#FEF3C7" />
        <rect x="570" y="210" width="20" height="16" fill="#FEF3C7" rx="2" />
        <ellipse cx="580" cy="210" rx="10" ry="4" fill="#92400E" />
        <path d="M590 214 Q596 218, 590 222" fill="none" stroke="#FEF3C7" strokeWidth="3" />
      </g>

      {/* Window - Center back */}
      <g>
        <rect x="320" y="60" width="160" height="180" fill="#87CEEB" rx="4" />
        <rect x="320" y="60" width="160" height="180" fill="none" stroke="#D4CFC9" strokeWidth="8" rx="4" />
        {/* Window panes */}
        <line x1="400" y1="60" x2="400" y2="240" stroke="#D4CFC9" strokeWidth="4" />
        <line x1="320" y1="150" x2="480" y2="150" stroke="#D4CFC9" strokeWidth="4" />
        {/* Clouds */}
        <ellipse cx="360" cy="100" rx="20" ry="12" fill="white" opacity="0.8" />
        <ellipse cx="375" cy="95" rx="15" ry="10" fill="white" opacity="0.8" />
        <ellipse cx="430" cy="120" rx="18" ry="10" fill="white" opacity="0.8" />
        <ellipse cx="445" cy="115" rx="12" ry="8" fill="white" opacity="0.8" />
      </g>

      {/* Small plant on floor */}
      <g>
        <rect x="180" y="280" width="30" height="40" fill="#92400E" rx="3" />
        <ellipse cx="195" cy="275" rx="25" ry="20" fill="#166534" />
        <ellipse cx="185" cy="265" rx="12" ry="15" fill="#15803D" />
        <ellipse cx="205" cy="268" rx="10" ry="12" fill="#15803D" />
      </g>
    </svg>
  );
};
