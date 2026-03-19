import { useSpoilerContext } from '../contexts/SpoilerContext';

export const useSpoilerMode = () => {
  const { spoilerModeEnabled, setSpoilerModeEnabled } = useSpoilerContext();

  return {
    // When true, hide scores/stats
    hideScores: spoilerModeEnabled,
    // Toggle function - use functional update to avoid stale closure issues
    toggleSpoilerMode: () => setSpoilerModeEnabled(prev => !prev),
    // Direct setter
    setSpoilerMode: setSpoilerModeEnabled,
  };
};
