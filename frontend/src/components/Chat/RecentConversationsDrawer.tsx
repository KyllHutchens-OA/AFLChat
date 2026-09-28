import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { RecentConversation } from '../../utils/recentConversations';

interface RecentConversationsDrawerProps {
  conversations: RecentConversation[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onClose: () => void;
}

const formatDate = (iso: string): string => {
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  } catch {
    return '';
  }
};

const RecentConversationsDrawer: React.FC<RecentConversationsDrawerProps> = ({
  conversations, currentId, onSelect, onClose,
}) => {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="recent-conversations-title"
        className="relative w-full sm:max-w-sm max-h-[75vh] bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl border border-warm-200/50 overflow-hidden flex flex-col"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-warm-100 flex-shrink-0">
          <h2 id="recent-conversations-title" className="text-base font-semibold text-ink">Recent chats</h2>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-warm-400 hover:text-warm-600 hover:bg-warm-100 transition-colors focus-visible:ring-2 focus-visible:ring-sherrin/50 focus-visible:outline-none"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="overflow-y-auto">
          {conversations.length === 0 ? (
            <p className="px-5 py-6 text-sm text-warm-500 text-center">No previous chats on this device yet.</p>
          ) : (
            <ul>
              {conversations.map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => onSelect(c.id)}
                    className={`w-full text-left px-5 py-3 border-b border-warm-100/60 hover:bg-warm-50 transition-colors
                                focus-visible:ring-2 focus-visible:ring-sherrin/50 focus-visible:outline-none
                                ${c.id === currentId ? 'bg-warm-50' : ''}`}
                  >
                    <p className="text-sm text-ink truncate">{c.firstQuestion || 'New conversation'}</p>
                    <p className="text-xs text-warm-400 mt-0.5">{formatDate(c.date)}</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
};

export default RecentConversationsDrawer;
