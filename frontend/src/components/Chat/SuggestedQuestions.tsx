import { useEffect, useState } from 'react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5001';

interface SuggestedQuestionsProps {
  onSelect: (question: string) => void;
}

interface SeasonMeta {
  current_season: number;
  latest_completed_season: number;
  in_season: boolean;
}

// Client-side guess until /api/meta/season answers: AFL runs roughly Mar-Sep.
const fallbackSeasonMeta = (now: Date = new Date()): SeasonMeta => {
  const year = now.getFullYear();
  const month = now.getMonth(); // 0 = Jan
  if (month >= 2 && month <= 8) {
    return { current_season: year, latest_completed_season: year - 1, in_season: true };
  }
  const completed = month < 2 ? year - 1 : year;
  return { current_season: completed, latest_completed_season: completed, in_season: false };
};

// Stats/records only: no "who won" chips, so they never spoil a result.
const buildStarterQuestions = (meta: SeasonMeta): string[] => {
  const season = meta.in_season ? meta.current_season : meta.latest_completed_season;
  const soFar = meta.in_season ? ' so far' : '';
  return [
    `Top 10 goal kickers in ${season}${soFar}`,
    `Most disposals in a single game in ${season}`,
    `Average tackles per game by team in ${season}`,
    'Top goal kickers of all time',
  ];
};

const SuggestedQuestions: React.FC<SuggestedQuestionsProps> = ({ onSelect }) => {
  const [meta, setMeta] = useState<SeasonMeta>(() => fallbackSeasonMeta());

  useEffect(() => {
    let cancelled = false;
    fetch(`${BACKEND_URL}/api/meta/season`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: SeasonMeta | null) => {
        if (!cancelled && data && typeof data.current_season === 'number') setMeta(data);
      })
      .catch(() => {
        // Keep the client-side fallback
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const questions = buildStarterQuestions(meta);

  return (
    <div className="flex flex-wrap gap-2 justify-center">
      {questions.map((q) => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          className="px-4 py-2 text-sm rounded-full border border-warm-200 text-warm-700
                     hover:bg-sherrin hover:text-white hover:border-sherrin
                     transition-all duration-200"
        >
          {q}
        </button>
      ))}
    </div>
  );
};

export default SuggestedQuestions;
