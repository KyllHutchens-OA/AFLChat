import { useEffect, useState } from 'react';
import scoreboardAnswers from '../../data/landingScoreboard.json';
import MiniQuarterChart from './MiniQuarterChart';
import { contrastText } from '../../utils/color';

interface TeamScore {
  abbr: string;
  score: string;
  total: number;
  quarters: number[];
  primary: string;
  secondary: string;
}

interface ScoreboardAnswer {
  id: string;
  question: string;
  summary: string;
  season: number;
  round: string;
  home: TeamScore;
  away: TeamScore;
}

const ANSWERS = scoreboardAnswers as ScoreboardAnswer[];
const CYCLE_MS = 6000;

// One flip-digit tile. Re-keying it on value change replays the flip.
const FlipDigit = ({ char, animKey }: { char: string; animKey: string }) => (
  <span
    key={animKey}
    className="inline-flex items-center justify-center w-[0.62em] h-[1.1em] bg-ink text-nightgame font-display
               rounded-[3px] mx-[1px] animate-flip-down"
    style={{ animationDuration: '400ms' }}
  >
    {char}
  </span>
);

const ScoreRow = ({ team }: { team: TeamScore }) => (
  <div className="flex items-center gap-3">
    <span
      className="w-9 text-center text-xs font-display tracking-wide rounded-sm py-1"
      style={{ backgroundColor: team.primary, color: contrastText(team.primary) }}
    >
      {team.abbr}
    </span>
    <div className="flex text-2xl sm:text-3xl leading-none">
      {team.score.split('').map((c, i) => (
        <FlipDigit key={i} animKey={`${team.abbr}-${team.score}-${i}`} char={c} />
      ))}
    </div>
  </div>
);

const Scoreboard = () => {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setIndex((i) => (i + 1) % ANSWERS.length), CYCLE_MS);
    return () => clearInterval(t);
  }, [paused]);

  const answer = ANSWERS[index];

  return (
    <div
      className="bg-ink text-white rounded-xl shadow-card-lg p-5 sm:p-6 paper-grain-dark w-full max-w-md"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-nightgame">
          Verified answer &middot; {answer.season} {answer.round}
        </span>
        <div className="flex gap-1">
          {ANSWERS.map((a, i) => (
            <button
              key={a.id}
              aria-label={`Show answer ${i + 1}`}
              onClick={() => setIndex(i)}
              className={`w-1.5 h-1.5 rounded-full transition-colors ${i === index ? 'bg-nightgame' : 'bg-white/25'}`}
            />
          ))}
        </div>
      </div>

      <p className="text-sm text-white/70 mb-4">&ldquo;{answer.question}&rdquo;</p>

      <div className="space-y-2 mb-4">
        <ScoreRow team={answer.home} />
        <ScoreRow team={answer.away} />
      </div>

      <p className="text-sm text-white/85 mb-4 leading-snug">{answer.summary}</p>

      <div className="flex justify-center border-t border-white/10 pt-3">
        <MiniQuarterChart home={answer.home} away={answer.away} />
      </div>
    </div>
  );
};

export default Scoreboard;
