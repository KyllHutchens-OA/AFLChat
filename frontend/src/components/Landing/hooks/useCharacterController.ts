import { useEffect, useState, useCallback, useRef } from 'react';

type ArrowKey = 'ArrowLeft' | 'ArrowRight';

interface UseCharacterControllerOptions {
  disabled?: boolean;
  onJump?: () => void;
}

export function useCharacterController({ disabled = false, onJump }: UseCharacterControllerOptions = {}) {
  const [keysPressed, setKeysPressed] = useState<Set<ArrowKey>>(new Set());
  const onJumpRef = useRef(onJump);

  // Keep onJump ref updated
  useEffect(() => {
    onJumpRef.current = onJump;
  }, [onJump]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (disabled) return;

    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      setKeysPressed(prev => {
        const next = new Set(prev);
        next.add(e.key as ArrowKey);
        return next;
      });
    }

    if (e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      onJumpRef.current?.();
    }
  }, [disabled]);

  const handleKeyUp = useCallback((e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      setKeysPressed(prev => {
        const next = new Set(prev);
        next.delete(e.key as ArrowKey);
        return next;
      });
    }
  }, []);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [handleKeyDown, handleKeyUp]);

  // Clear keys when disabled changes to true
  useEffect(() => {
    if (disabled) {
      setKeysPressed(new Set());
    }
  }, [disabled]);

  return { keysPressed };
}
