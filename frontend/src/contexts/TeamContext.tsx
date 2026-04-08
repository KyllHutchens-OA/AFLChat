import { createContext, useContext, useState, ReactNode } from 'react';

interface TeamContextType {
  team: string | null;
  setTeam: (team: string) => void;
  clearTeam: () => void;
}

const TeamContext = createContext<TeamContextType | undefined>(undefined);

const STORAGE_KEY = 'footy-nac-team';

export const TeamProvider = ({ children }: { children: ReactNode }) => {
  const [team, setTeamState] = useState<string | null>(() => {
    return localStorage.getItem(STORAGE_KEY);
  });

  const setTeam = (teamName: string) => {
    setTeamState(teamName);
    localStorage.setItem(STORAGE_KEY, teamName);
  };

  const clearTeam = () => {
    setTeamState(null);
    localStorage.removeItem(STORAGE_KEY);
  };

  return (
    <TeamContext.Provider value={{ team, setTeam, clearTeam }}>
      {children}
    </TeamContext.Provider>
  );
};

export const useTeam = () => {
  const context = useContext(TeamContext);
  if (!context) {
    throw new Error('useTeam must be used within TeamProvider');
  }
  return context;
};
