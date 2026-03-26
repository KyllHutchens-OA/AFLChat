import { useState } from 'react';
import { useSpoilerContext } from '../../contexts/SpoilerContext';

const SpoilerModal = () => {
  const { hasSeenModal, setHasSeenModal, setSpoilerModeEnabled } = useSpoilerContext();
  const [step, setStep] = useState<'welcome' | 'spoiler'>('welcome');

  if (hasSeenModal) return null;

  const handleSpoilerChoice = (enableSpoilerMode: boolean) => {
    setSpoilerModeEnabled(enableSpoilerMode);
    setHasSeenModal(true);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      {step === 'welcome' ? (
        /* Step 1: Welcome */
        <div className="bg-apple-gray-900/95 backdrop-blur-xl max-w-md w-full rounded-apple-xl p-8 shadow-apple-xl border border-white/10">
          <div className="text-center mb-6">
            <div className="w-16 h-16 mx-auto bg-apple-blue-500 rounded-full flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h2 className="text-2xl font-semibold text-white mb-3">
              Welcome to Footy-NAC
            </h2>
            <div className="text-left space-y-2 text-sm text-apple-gray-300">
              <div className="flex items-start gap-2">
                <span className="text-apple-blue-400 mt-0.5 flex-shrink-0">&#x2022;</span>
                <span><strong className="text-white">Chat Agent</strong> — Ask any AFL question and get instant stats, charts, and analysis</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-apple-blue-400 mt-0.5 flex-shrink-0">&#x2022;</span>
                <span><strong className="text-white">Live Games</strong> — Follow games in real-time with AI-powered quarter summaries and match previews</span>
              </div>
            </div>
          </div>

          <button
            onClick={() => setStep('spoiler')}
            className="w-full py-3 px-6 bg-apple-blue-500 text-white rounded-apple font-medium
                       hover:bg-apple-blue-600 active:scale-[0.98] transition-all duration-200"
          >
            Get Started
          </button>

          {/* Support footer */}
          <div className="border-t border-white/10 pt-4 mt-6">
            <p className="text-center text-xs text-apple-gray-300 mb-2">
              Consider supporting me to help keep things going.
            </p>
            <div className="text-center">
              <a
                href="https://buymeacoffee.com/footy.nac"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-400 hover:text-amber-300 transition-colors"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20.216 6.415l-.132-.666c-.119-.598-.388-1.163-1.001-1.379-.197-.069-.42-.098-.57-.241-.152-.143-.196-.366-.231-.572-.065-.378-.125-.756-.192-1.133-.057-.325-.102-.69-.25-.987-.195-.4-.597-.634-.996-.788a5.723 5.723 0 00-.626-.194c-1-.263-2.05-.36-3.077-.416a25.834 25.834 0 00-3.7.062c-.915.083-1.88.184-2.75.5-.318.116-.646.256-.888.501-.297.302-.393.77-.177 1.146.154.267.415.456.692.58.36.162.737.284 1.123.366 1.075.238 2.189.331 3.287.37 1.218.05 2.437.01 3.65-.118.299-.033.598-.073.896-.119.352-.054.578-.513.474-.834-.124-.383-.457-.531-.834-.473-.466.074-.96.108-1.382.146-1.177.08-2.358.082-3.536.006a22.228 22.228 0 01-1.157-.107c.067-.222.131-.445.2-.666.093-.292.21-.577.374-.838.197-.312.47-.556.822-.66a5.48 5.48 0 011.233-.166c.678-.032 1.356-.02 2.034.019.712.04 1.422.114 2.126.227.262.042.524.098.784.157.042.012.08.028.12.046.096.044.184.11.216.206l.132.666c.035.175.037.355.018.532l-.353 1.78c-.08.4-.162.8-.233 1.201l-.175.878c-.033.167-.083.333-.127.5a.728.728 0 01-.378.432l-.007.003-.008.004-.011.005h-.003c-.012.006-.024.011-.036.016a.672.672 0 01-.141.047c-.053.012-.107.018-.161.019H14.5c-.093 0-.183-.019-.269-.055a.733.733 0 01-.179-.108l-.002-.001-.001-.001a.64.64 0 01-.063-.062l-.002-.003a.584.584 0 01-.077-.117l-.003-.008a.51.51 0 01-.037-.12l-.002-.01a.443.443 0 01-.012-.134v-.002a.447.447 0 01.02-.134l.003-.01c.008-.038.02-.075.037-.12l.003-.007a.58.58 0 01.077-.118l.002-.002a.62.62 0 01.063-.063l.001-.001a.726.726 0 01.179-.108.73.73 0 01.269-.055h.002l.037-.002a.753.753 0 00.366-.11.732.732 0 00.296-.393c.043-.143.047-.292.025-.439l-.353-1.78a18.89 18.89 0 00-.233-1.2l-.175-.878a4.285 4.285 0 00-.127-.5.73.73 0 00-.378-.432l-.007-.003-.008-.004-.011-.005h-.003a.473.473 0 00-.036-.016.672.672 0 00-.141-.047.723.723 0 00-.161-.019H9.5c-.093 0-.183.019-.269.055a.733.733 0 00-.179.108l-.002.001-.001.001a.64.64 0 00-.063.062l-.002.003a.584.584 0 00-.077.117l-.003.008a.51.51 0 00-.037.12l-.002.01a.443.443 0 00-.012.134v.002c-.002.045.005.09.02.134l.003.01c.008.038.02.075.037.12l.003.007a.58.58 0 00.077.118l.002.002a.62.62 0 00.063.063l.001.001a.726.726 0 00.179.108.73.73 0 00.269.055h.002l.037.002a.753.753 0 01.366.11.732.732 0 01.296.393c.043.143.047.292.025.439L4.02 17.34a1.44 1.44 0 01-1.416 1.16H2.5c-.28 0-.5.22-.5.5s.22.5.5.5h.103a2.44 2.44 0 002.4-1.966l.89-4.49.353-1.78c.035-.175.037-.355.018-.532a1.73 1.73 0 00-.216-.206l-.12-.046c-.26-.06-.522-.115-.784-.157a20.57 20.57 0 00-2.126-.227 25.15 25.15 0 00-2.034-.02c-.429.013-.847.063-1.233.167-.352.104-.625.348-.822.66a3.04 3.04 0 00-.374.838c-.069.221-.133.444-.2.666.385.05.772.087 1.157.107 1.178.076 2.359.074 3.536-.006.422-.038.916-.072 1.382-.146.377-.058.71.09.834.473.104.321-.122.78-.474.834-.298.046-.597.086-.896.119a24.58 24.58 0 01-3.65.118c-1.098-.039-2.212-.132-3.287-.37a5.023 5.023 0 01-1.123-.366 1.386 1.386 0 01-.692-.58c-.216-.376-.12-.844.177-1.146.242-.245.57-.385.888-.501.87-.316 1.835-.417 2.75-.5a25.83 25.83 0 013.7-.062c1.027.056 2.077.153 3.077.416.208.055.42.122.626.194.399.154.801.388.996.788.148.297.193.662.25.987.067.377.127.755.192 1.133.035.206.079.429.231.572.15.143.373.172.57.241.613.216.882.781 1.001 1.379l.132.666z" />
                </svg>
                Buy Me a Coffee
              </a>
            </div>
          </div>
        </div>
      ) : (
        /* Step 2: Spoiler preference */
        <div className="bg-apple-gray-900/95 backdrop-blur-xl max-w-md w-full rounded-apple-xl p-8 shadow-apple-xl border border-white/10">
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
            <p className="text-apple-gray-300 text-sm">
              This app shows live and previously played game scores. Would you like to hide spoilers?
            </p>
          </div>

          <div className="space-y-3">
            <button
              onClick={() => handleSpoilerChoice(true)}
              className="w-full py-3 px-6 bg-white/10 text-white border border-white/20 rounded-apple font-medium
                         hover:bg-white/20 active:scale-[0.98] transition-all duration-200"
            >
              Hide Scores (No Spoilers)
            </button>
            <button
              onClick={() => handleSpoilerChoice(false)}
              className="w-full py-3 px-6 bg-apple-blue-500 text-white rounded-apple font-medium
                         hover:bg-apple-blue-600 active:scale-[0.98] transition-all duration-200"
            >
              Show Scores (See Everything)
            </button>
          </div>

          <p className="text-center text-xs text-apple-gray-500 mt-6">
            You can toggle this anytime via the eye icon in the top navigation
          </p>
        </div>
      )}
    </div>
  );
};

export default SpoilerModal;
