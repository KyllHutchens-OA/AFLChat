import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface SpoilerContextType {
  spoilerModeEnabled: boolean;
  setSpoilerModeEnabled: React.Dispatch<React.SetStateAction<boolean>>;
  hasSeenModal: boolean;
  setHasSeenModal: (seen: boolean) => void;
}

const SpoilerContext = createContext<SpoilerContextType | undefined>(undefined);

const STORAGE_KEYS = {
  SPOILER_MODE: 'afl-nac-spoiler-mode',
  HAS_SEEN_MODAL: 'footy-nac-welcome-v2',
};

export const SpoilerProvider = ({ children }: { children: ReactNode }) => {
  // Initialize from localStorage (default: spoiler mode OFF = show stats)
  const [spoilerModeEnabled, setSpoilerModeEnabled] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEYS.SPOILER_MODE);
    return stored === 'true';
  });

  const [hasSeenModal, setHasSeenModal] = useState(() => {
    return localStorage.getItem(STORAGE_KEYS.HAS_SEEN_MODAL) === 'true';
  });

  // Persist to localStorage on change
  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.SPOILER_MODE, String(spoilerModeEnabled));
  }, [spoilerModeEnabled]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.HAS_SEEN_MODAL, String(hasSeenModal));
  }, [hasSeenModal]);

  return (
    <SpoilerContext.Provider value={{
      spoilerModeEnabled,
      setSpoilerModeEnabled,
      hasSeenModal,
      setHasSeenModal,
    }}>
      {children}
    </SpoilerContext.Provider>
  );
};

export const useSpoilerContext = () => {
  const context = useContext(SpoilerContext);
  if (!context) {
    throw new Error('useSpoilerContext must be used within SpoilerProvider');
  }
  return context;
};
