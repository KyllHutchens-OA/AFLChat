import { useEffect, useRef } from 'react';

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onFocus?: () => void;
  disabled?: boolean;
}

const MAX_HEIGHT_PX = 160; // ~6 lines before it scrolls internally

/** Multiline, auto-growing chat input. Enter sends, Shift+Enter inserts a newline. */
const ChatInput: React.FC<ChatInputProps> = ({ value, onChange, onSubmit, onFocus, disabled }) => {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !disabled) onSubmit();
    }
  };

  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={handleKeyDown}
      onFocus={onFocus}
      placeholder="Ask about AFL statistics..."
      aria-label="Ask about AFL statistics"
      disabled={disabled}
      rows={1}
      className="w-full px-4 py-3 rounded-xl border border-warm-200 bg-white resize-none
                 focus:outline-none focus:ring-2 focus:ring-sherrin/30 focus:border-sherrin
                 text-sm disabled:bg-warm-50 disabled:cursor-not-allowed
                 placeholder:text-warm-400 transition-all leading-normal"
      style={{ maxHeight: MAX_HEIGHT_PX }}
    />
  );
};

export default ChatInput;
