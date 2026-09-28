import { useState } from 'react';

interface SpoilerBlurProps {
  // Spoiler mode is on AND this content looks like it reveals a result.
  active: boolean;
  children: React.ReactNode;
}

/**
 * Blurs an answer that looks like it reveals a match result while spoiler
 * mode is on, with tap-to-reveal (mirrors the `blur-sm` convention already
 * used for scores in LiveGames/GameSidebar.tsx). The backend prompt is asked
 * not to reveal current-season results at all when spoiler mode is on; this
 * is the client-side backstop for anything that slips through, and for the
 * user tapping a spoiler-y question before rereading their own toggle.
 */
const SpoilerBlur: React.FC<SpoilerBlurProps> = ({ active, children }) => {
  const [revealed, setRevealed] = useState(false);
  if (!active || revealed) return <>{children}</>;

  return (
    <div className="relative">
      <div className="blur-md select-none pointer-events-none" aria-hidden="true">
        {children}
      </div>
      <button
        onClick={() => setRevealed(true)}
        className="absolute inset-0 flex items-center justify-center rounded-lg
                   bg-white/40 hover:bg-white/50 transition-colors
                   text-sm font-semibold text-ink focus-visible:ring-2 focus-visible:ring-sherrin
                   focus-visible:outline-none"
      >
        <span className="px-4 py-2 rounded-full bg-white shadow-card border border-warm-200">
          Spoiler mode is on — tap to reveal
        </span>
      </button>
    </div>
  );
};

export default SpoilerBlur;
