import { useState } from 'react';
import trace from '../../data/landingTrace.json';

interface Step {
  id: string;
  label: string;
  sub: string;
  detail: string;
}

const STEPS: Step[] = [
  { id: 'question', label: 'Question', sub: 'The kick-in', detail: `"${trace.question}"` },
  { id: 'resolve', label: 'Resolve entities', sub: 'A handball', detail: trace.resolveEntities },
  { id: 'tools', label: 'Tools', sub: 'Playing on', detail: trace.tool },
  { id: 'sql', label: 'SQL', sub: 'Through the corridor', detail: trace.sql },
  { id: 'chart', label: 'Chart', sub: 'Lining up', detail: trace.chart },
  { id: 'answer', label: 'Answer', sub: 'Goal umpire’s flags', detail: trace.answer },
];

const STATS = [
  { value: '7,090', label: 'matches, 1990–2026' },
  { value: '310,423', label: 'player-game rows' },
  { value: '118 / 122', label: 'ground-truth eval cases' },
  { value: '~2.6s', label: 'median answer time' },
  { value: '< $0.001', label: 'cost per answer' },
];

const HowItThinks = () => {
  const [active, setActive] = useState<string>('question');
  const activeStep = STEPS.find((s) => s.id === active) ?? STEPS[0];

  return (
    <section id="how-it-thinks" className="bg-ink text-white py-14 sm:py-20 paper-grain-dark">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 lg:px-10">
        <h2 className="font-display text-3xl mb-2">How it thinks.</h2>
        <p className="text-white/60 mb-10 max-w-2xl">
          Each answer goes through the same steps. The question is matched to real teams and players,
          a tool or SQL query gets the data, and the SQL and chart are checked before you see them.
          Hover a step to see the real output from a stored answer.
        </p>

        <div className="flex flex-wrap gap-2 sm:gap-0 sm:flex items-stretch mb-6 border-b border-white/10 pb-6">
          {STEPS.map((step, i) => (
            <div key={step.id} className="flex items-center">
              <button
                onMouseEnter={() => setActive(step.id)}
                onFocus={() => setActive(step.id)}
                onClick={() => setActive(step.id)}
                className={`text-left px-3 py-2 rounded-lg transition-colors ${
                  active === step.id ? 'bg-sherrin' : 'hover:bg-white/10'
                }`}
              >
                <div className="text-sm font-semibold">{step.label}</div>
                <div className="text-[11px] text-white/50">{step.sub}</div>
              </button>
              {i < STEPS.length - 1 && (
                <svg className="w-5 h-5 text-white/25 mx-1 hidden sm:block" fill="none" viewBox="0 0 24 24">
                  <path stroke="currentColor" strokeWidth={2} strokeLinecap="round" d="M9 5l7 7-7 7" />
                </svg>
              )}
            </div>
          ))}
        </div>

        <pre className="bg-black/30 rounded-lg p-4 text-xs sm:text-sm text-nightgame overflow-x-auto whitespace-pre-wrap mb-12 min-h-[4rem] font-mono">
          {activeStep.detail}
        </pre>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-6">
          {STATS.map((s) => (
            <div key={s.label}>
              <div className="font-display text-3xl sm:text-4xl text-nightgame tabular-nums">{s.value}</div>
              <div className="text-xs text-white/60 mt-1">{s.label}</div>
            </div>
          ))}
        </div>

        <a
          href="https://github.com/KyllHutchens-OA/AFLChat"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 mt-8 text-sm text-white/70 hover:text-white transition-colors"
        >
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 .3a12 12 0 00-3.8 23.4c.6.1.8-.3.8-.6v-2.2c-3.3.7-4-1.6-4-1.6-.6-1.4-1.4-1.8-1.4-1.8-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1.1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.4-1.4-5.4-6a4.6 4.6 0 011.2-3.2 4.3 4.3 0 01.1-3.2s1-.3 3.3 1.2a11.5 11.5 0 016 0c2.3-1.5 3.3-1.2 3.3-1.2a4.3 4.3 0 01.1 3.2 4.6 4.6 0 011.2 3.2c0 4.6-2.8 5.7-5.5 6 .5.4.9 1.1.9 2.3v3.3c0 .3.2.7.8.6A12 12 0 0012 .3z" />
          </svg>
          View the source on GitHub
        </a>
      </div>
    </section>
  );
};

export default HowItThinks;
