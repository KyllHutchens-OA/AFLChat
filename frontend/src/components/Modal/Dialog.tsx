import { ReactNode, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

interface DialogProps {
  onClose: () => void;
  labelId: string;
  children: ReactNode;
  className?: string;
  /** Clicking the backdrop closes the dialog. Off for a forced first-time choice. */
  closeOnBackdrop?: boolean;
}

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

// Shared accessible modal shell: role="dialog", aria-modal, a focus trap and
// Escape to close. Used by every overlay outside the chat page (chat owns
// its own dialogs, if any).
const Dialog: React.FC<DialogProps> = ({ onClose, labelId, children, className = '', closeOnBackdrop = true }) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const focusables = panel?.querySelectorAll<HTMLElement>(FOCUSABLE);
    (focusables?.[0] ?? panel)?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== 'Tab' || !panel) return;
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      previouslyFocused.current?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Portalled to <body>: a `fixed` overlay nested inside an ancestor with a
  // backdrop-filter (the nav's glass blur) would otherwise be positioned
  // relative to that ancestor's box instead of the viewport (backdrop-filter
  // creates a containing block for fixed descendants, same as transform).
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (closeOnBackdrop && e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
        tabIndex={-1}
        className={className}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
};

export default Dialog;
