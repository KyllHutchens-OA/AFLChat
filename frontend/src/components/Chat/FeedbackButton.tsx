import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';

const API_BASE = import.meta.env.VITE_API_URL || '';

interface FeedbackButtonProps {
  conversationId: string | null;
  messageText: string;
}

const FeedbackButton: React.FC<FeedbackButtonProps> = ({ conversationId, messageText }) => {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<'form' | 'submitting' | 'done'>('form');
  const [whatHappened, setWhatHappened] = useState('');
  const [whatExpected, setWhatExpected] = useState('');
  const [error, setError] = useState('');

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') handleClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open]);

  const handleClose = () => {
    setOpen(false);
    // Reset form after animation
    setTimeout(() => {
      setState('form');
      setWhatHappened('');
      setWhatExpected('');
      setError('');
    }, 200);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!whatHappened.trim()) {
      setError('Please describe what happened.');
      return;
    }
    setError('');
    setState('submitting');

    try {
      const res = await fetch(`${API_BASE}/api/reports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          message_text: messageText.slice(0, 1000),
          what_happened: whatHappened.trim(),
          what_expected: whatExpected.trim(),
          page_url: window.location.href,
        }),
      });

      if (!res.ok) throw new Error('Server error');
      setState('done');
      setTimeout(handleClose, 2000);
    } catch {
      setError('Something went wrong. Please try again.');
      setState('form');
    }
  };

  const modal = open ? createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) handleClose(); }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />

      {/* Dialog */}
      <div className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl border border-apple-gray-200/50 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-apple-gray-100">
          <div>
            <h2 className="text-base font-semibold text-apple-gray-900">Report an issue</h2>
            <p className="text-xs text-apple-gray-400 mt-0.5">Help us improve AFL.NAC</p>
          </div>
          <button
            onClick={handleClose}
            className="p-1.5 rounded-lg text-apple-gray-400 hover:text-apple-gray-600 hover:bg-apple-gray-100 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {state === 'done' ? (
          <div className="px-5 py-10 text-center">
            <div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-3">
              <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-sm font-medium text-apple-gray-900">Thanks for your report!</p>
            <p className="text-xs text-apple-gray-400 mt-1">We'll look into it.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="px-5 py-5 space-y-4">
            <div>
              <label className="block text-xs font-medium text-apple-gray-600 mb-1.5">
                What went wrong? <span className="text-red-400">*</span>
              </label>
              <textarea
                value={whatHappened}
                onChange={(e) => setWhatHappened(e.target.value)}
                placeholder="Describe the problem with this response..."
                rows={3}
                maxLength={2000}
                disabled={state === 'submitting'}
                autoFocus
                className="w-full text-sm px-3 py-2 rounded-xl border border-apple-gray-200 bg-apple-gray-50
                           focus:outline-none focus:ring-2 focus:ring-apple-blue-500/30 focus:border-apple-blue-500
                           focus:bg-white resize-none disabled:opacity-60 transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-apple-gray-600 mb-1.5">
                What did you expect instead? <span className="text-apple-gray-400">(optional)</span>
              </label>
              <textarea
                value={whatExpected}
                onChange={(e) => setWhatExpected(e.target.value)}
                placeholder="The correct answer or behaviour..."
                rows={2}
                maxLength={2000}
                disabled={state === 'submitting'}
                className="w-full text-sm px-3 py-2 rounded-xl border border-apple-gray-200 bg-apple-gray-50
                           focus:outline-none focus:ring-2 focus:ring-apple-blue-500/30 focus:border-apple-blue-500
                           focus:bg-white resize-none disabled:opacity-60 transition-colors"
              />
            </div>

            {error && <p className="text-xs text-red-500">{error}</p>}

            <div className="flex gap-2 pt-1">
              <button
                type="submit"
                disabled={state === 'submitting'}
                className="flex-1 py-2 text-sm font-medium text-white bg-apple-blue-500 rounded-xl
                           hover:bg-apple-blue-600 disabled:opacity-60 transition-colors"
              >
                {state === 'submitting' ? 'Sending…' : 'Send report'}
              </button>
              <button
                type="button"
                onClick={handleClose}
                disabled={state === 'submitting'}
                className="px-4 py-2 text-sm text-apple-gray-500 hover:text-apple-gray-700 hover:bg-apple-gray-100
                           rounded-xl transition-colors disabled:opacity-60"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>,
    document.body
  ) : null;

  return (
    <>
      <div className="mt-3 text-center">
        <p className="text-xs text-apple-gray-500 mb-1">
          AFL.NAC is still learning. If this response seems off, wrong, or just plain weird, let us know and we'll work to fix it!
        </p>
        <button
          onClick={() => setOpen(true)}
          className="text-xs text-apple-blue-500 hover:text-apple-blue-600 inline-flex items-center gap-1 transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
          </svg>
          Report an issue
        </button>
      </div>

      {modal}
    </>
  );
};

export default FeedbackButton;
