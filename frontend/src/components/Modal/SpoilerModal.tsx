import { useSpoilerContext } from '../../contexts/SpoilerContext';

const SpoilerModal = () => {
  const { hasSeenModal, setHasSeenModal, setSpoilerModeEnabled } = useSpoilerContext();

  if (hasSeenModal) return null;

  const handleChoice = (enableSpoilerMode: boolean) => {
    setSpoilerModeEnabled(enableSpoilerMode);
    setHasSeenModal(true);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-apple-gray-900/95 backdrop-blur-xl max-w-md w-full rounded-apple-xl p-8 shadow-apple-xl border border-white/10">
        {/* Icon */}
        <div className="text-center mb-6">
          <div className="w-16 h-16 mx-auto bg-apple-blue-500 rounded-full flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          </div>
          <h2 className="text-2xl font-semibold text-white mb-2">
            Spoiler Preferences
          </h2>
          <p className="text-apple-gray-300">
            Would you like to hide live scores and results?
            You can change this anytime using the eye icon in the navigation.
          </p>
        </div>

        {/* Buttons */}
        <div className="space-y-3">
          <button
            onClick={() => handleChoice(true)}
            className="w-full py-3 px-6 bg-apple-blue-500 text-white rounded-apple font-medium
                       hover:bg-apple-blue-600 active:scale-[0.98] transition-all duration-200"
          >
            Hide Scores (No Spoilers)
          </button>
          <button
            onClick={() => handleChoice(false)}
            className="w-full py-3 px-6 bg-white/10 text-white border border-white/20 rounded-apple font-medium
                       hover:bg-white/20 active:scale-[0.98] transition-all duration-200"
          >
            Show Scores (See Everything)
          </button>
        </div>

        <p className="text-center text-xs text-apple-gray-500 mt-6">
          You can toggle this anytime via the eye icon in the top navigation
        </p>
      </div>
    </div>
  );
};

export default SpoilerModal;
