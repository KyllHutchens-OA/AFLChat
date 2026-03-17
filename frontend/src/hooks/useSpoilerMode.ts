import { useSpoilerContext } from '../contexts/SpoilerContext';

export const useSpoilerMode = () => {
  const { spoilerModeEnabled, setSpoilerModeEnabled } = useSpoilerContext();

  return {
    // When true, hide scores/stats
    hideScores: spoilerModeEnabled,
    // Toggle function
    toggleSpoilerMode: () => setSpoilerModeEnabled(!spoilerModeEnabled),
    // Direct setter
    setSpoilerMode: setSpoilerModeEnabled,
  };
};
