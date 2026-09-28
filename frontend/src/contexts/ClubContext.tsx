import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { CLUBS, Club } from '../constants/clubs';

interface ClubContextType {
  club: Club | null;
  setClub: (abbreviation: string | null) => void;
}

const ClubContext = createContext<ClubContextType | undefined>(undefined);

const STORAGE_KEY = 'footy-nac-club';

// Sherrin red / ink — the app's default accent when no club is chosen.
const DEFAULT_PRIMARY = '#C8102E';
const DEFAULT_SECONDARY = '#16130F';

function applyClubVars(club: Club | null) {
  const root = document.documentElement;
  root.style.setProperty('--club-primary', club?.primaryColor ?? DEFAULT_PRIMARY);
  root.style.setProperty('--club-secondary', club?.secondaryColor ?? DEFAULT_SECONDARY);
}

export const ClubProvider = ({ children }: { children: ReactNode }) => {
  const [club, setClubState] = useState<Club | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return CLUBS.find((c) => c.abbreviation === stored) ?? null;
  });

  useEffect(() => {
    applyClubVars(club);
  }, [club]);

  const setClub = (abbreviation: string | null) => {
    const next = abbreviation ? CLUBS.find((c) => c.abbreviation === abbreviation) ?? null : null;
    setClubState(next);
    if (next) {
      localStorage.setItem(STORAGE_KEY, next.abbreviation);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  return (
    <ClubContext.Provider value={{ club, setClub }}>
      {children}
    </ClubContext.Provider>
  );
};

export const useClub = () => {
  const context = useContext(ClubContext);
  if (!context) {
    throw new Error('useClub must be used within ClubProvider');
  }
  return context;
};
