import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useClub } from '../../contexts/ClubContext';
import LogoMark from '../Layout/LogoMark';
import Scoreboard from './Scoreboard';

const PLACEHOLDER_QUESTIONS = [
  'Who kicked the most goals in a losing Grand Final?',
  'Buddy vs Lockett, goals per game',
  'Closest finish at the Gabba since 2000',
  'Daicos vs Bontempelli, disposals by season',
];

const BASE_CHIPS = [
  'Most disposals in a single game since 1990',
  "Show me Geelong's win/loss record since 2015",
  'Top 10 goal kickers in 2025',
];

const Hero = () => {
  const navigate = useNavigate();
  const { club } = useClub();
  const [input, setInput] = useState('');
  const [placeholderIndex, setPlaceholderIndex] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setPlaceholderIndex((i) => (i + 1) % PLACEHOLDER_QUESTIONS.length), 3200);
    return () => clearInterval(t);
  }, []);

  const chips = club
    ? [`How has ${club.name} gone this season?`, ...BASE_CHIPS.slice(0, 2)]
    : BASE_CHIPS;

  const goAsk = (q: string) => {
    if (!q.trim()) return;
    navigate(`/ask?q=${encodeURIComponent(q.trim())}`);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    goAsk(input);
  };

  return (
    <section className="relative overflow-hidden bg-paper paper-grain">
      {/* decorative 50m arc line-work */}
      <svg className="absolute -top-24 -right-40 w-[560px] h-[560px] text-warm-300/40 pointer-events-none" viewBox="0 0 200 200" aria-hidden="true">
        <circle cx="100" cy="100" r="95" fill="none" stroke="currentColor" strokeWidth="1" />
        <circle cx="100" cy="100" r="60" fill="none" stroke="currentColor" strokeWidth="1" />
      </svg>

      <div className="relative max-w-7xl mx-auto px-4 sm:px-8 lg:px-10 pt-10 pb-16 sm:pt-16 sm:pb-24 grid lg:grid-cols-2 gap-10 items-center">
        <div>
          <div className="flex items-center gap-3 mb-5">
            <LogoMark className="w-10 h-10" animate />
            <span className="text-xs font-semibold uppercase tracking-[0.25em] text-warm-600">
              Not Another Commentator
            </span>
          </div>

          <h1 className="font-display text-5xl sm:text-6xl leading-[0.95] text-ink mb-4">
            NEED TO SETTLE<br />A DEBATE?
          </h1>
          <p className="text-lg text-warm-700 mb-8 max-w-md">
            Ask about any AFL match or player since 1990 and get the answer with a chart.
          </p>

          <form onSubmit={handleSubmit} className="mb-4">
            <div className="flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={PLACEHOLDER_QUESTIONS[placeholderIndex]}
                aria-label="Ask a footy question"
                className="input-field flex-1 text-base py-3.5"
              />
              <button
                type="submit"
                className="shrink-0 px-6 py-2.5 rounded-lg font-semibold text-white shadow-card
                           bg-[var(--club-primary)] hover:brightness-90 active:scale-95
                           transition-all duration-200"
              >
                Ask
              </button>
            </div>
          </form>

          <div className="flex flex-wrap gap-2">
            {chips.map((q) => (
              <button
                key={q}
                onClick={() => goAsk(q)}
                className="text-sm px-3 py-1.5 rounded-full bg-white border border-warm-300 text-warm-700
                           hover:border-[var(--club-primary)] hover:text-[var(--club-primary)] transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        <div className="flex justify-center lg:justify-end">
          <Scoreboard />
        </div>
      </div>

      <div className="boundary-line" />
    </section>
  );
};

export default Hero;
