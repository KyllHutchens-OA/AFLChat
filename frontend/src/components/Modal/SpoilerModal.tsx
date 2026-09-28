import { useSpoilerContext } from '../../contexts/SpoilerContext';
import Dialog from './Dialog';

// Spoiler preference prompt, shown once (rendered on /live only).
const SpoilerModal = () => {
  const { hasSeenModal, setHasSeenModal, setSpoilerModeEnabled } = useSpoilerContext();

  if (hasSeenModal) return null;

  const handleSpoilerChoice = (enableSpoilerMode: boolean) => {
    setSpoilerModeEnabled(enableSpoilerMode);
    setHasSeenModal(true);
  };

  return (
    // This is a forced first-time choice, not a dismissible notice, so the
    // backdrop doesn't close it. Escape still works, defaulting to the safe
    // choice (hide scores) rather than leaving the preference unset.
    <Dialog
      onClose={() => handleSpoilerChoice(true)}
      labelId="spoiler-modal-title"
      closeOnBackdrop={false}
      className="bg-ink/95 backdrop-blur-xl max-w-md w-full rounded-xl p-8 shadow-card-xl border border-white/10"
    >
      <div className="text-center mb-6">
        <div className="w-16 h-16 mx-auto bg-sherrin rounded-full flex items-center justify-center mb-4">
          <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
        </div>
        <h2 id="spoiler-modal-title" className="text-2xl font-semibold text-white mb-2">
          Spoiler Preferences
        </h2>
        <p className="text-warm-300 text-sm">
          This app shows live and previously played game scores. Would you like to hide spoilers?
        </p>
      </div>

      <div className="space-y-3">
        <button
          onClick={() => handleSpoilerChoice(true)}
          className="w-full py-3 px-6 bg-white/10 text-white border border-white/20 rounded-md font-medium
                     hover:bg-white/20 active:scale-[0.98] transition-all duration-200"
        >
          Hide Scores (No Spoilers)
        </button>
        <button
          onClick={() => handleSpoilerChoice(false)}
          className="w-full py-3 px-6 bg-sherrin text-white rounded-md font-medium
                     hover:bg-sherrin-600 active:scale-[0.98] transition-all duration-200"
        >
          Show Scores (See Everything)
        </button>
      </div>

      <p className="text-center text-xs text-warm-300 mt-6">
        You can toggle this anytime via the eye icon in the top navigation
      </p>
    </Dialog>
  );
};

export default SpoilerModal;
