import { useEffect, useRef, useCallback } from 'react';

interface UseGameLoopOptions {
  onTick: (deltaTime: number) => void;
  isRunning: boolean;
}

export function useGameLoop({ onTick, isRunning }: UseGameLoopOptions) {
  const requestRef = useRef<number>();
  const previousTimeRef = useRef<number>();
  const onTickRef = useRef(onTick);

  // Keep onTick ref updated to avoid stale closures
  useEffect(() => {
    onTickRef.current = onTick;
  }, [onTick]);

  const animate = useCallback((time: number) => {
    if (previousTimeRef.current !== undefined) {
      const deltaTime = time - previousTimeRef.current;
      onTickRef.current(deltaTime);
    }
    previousTimeRef.current = time;
    requestRef.current = requestAnimationFrame(animate);
  }, []);

  useEffect(() => {
    if (isRunning) {
      previousTimeRef.current = undefined;
      requestRef.current = requestAnimationFrame(animate);
    } else {
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current);
      }
    }

    return () => {
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current);
      }
    };
  }, [isRunning, animate]);
}
