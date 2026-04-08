interface ThinkingCardProps {
  step: string;
}

const STEPS = [
  { keys: ['understand', 'received', 'question', 'complexity', 'analyz', 'plan'], label: 'Understanding' },
  { keys: ['sql', 'query', 'generat', 'building', 'execut', 'fetch', 'database', 'search', 'found', 'result', 'statistic', 'enrich', 'odds', 'news', 'predict', 'tipping'], label: 'Crunching the numbers' },
  { keys: ['visuali', 'chart', 'creat', 'respond', 'writ', 'response', 'complete'], label: 'Putting it together' },
];

const ThinkingCard: React.FC<ThinkingCardProps> = ({ step }) => {
  const stepLower = step.toLowerCase();
  const activeIdx = STEPS.findIndex(s => s.keys.some(k => stepLower.includes(k)));

  return (
    <div className="card-apple p-5 animate-fade-in">
      <div className="space-y-4">
        {STEPS.map((s, i) => {
          const isActive = i === activeIdx;
          const isDone = i < activeIdx;

          return (
            <div key={s.label} className="flex items-center gap-3">
              <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                isActive ? 'bg-afl-accent animate-pulse' :
                isDone ? 'bg-afl-accent' :
                'bg-afl-warm-200'
              }`} />

              <span className={`text-sm flex-shrink-0 w-40 ${
                isActive ? 'text-afl-warm-900 font-medium' :
                isDone ? 'text-afl-warm-500' :
                'text-afl-warm-300'
              }`}>
                {s.label}
              </span>

              {isActive && (
                <div className="flex-1 h-8 relative overflow-hidden">
                  {/* Football — positioned absolutely, animated with left % */}
                  <div className="football-dribble absolute bottom-0 h-5 w-5">
                    <svg className="w-5 h-5 text-afl-accent" viewBox="0 0 24 24" fill="currentColor">
                      <ellipse cx="12" cy="12" rx="10" ry="7" transform="rotate(-30 12 12)" />
                      <line x1="5" y1="8" x2="19" y2="16" stroke="white" strokeWidth="0.8" />
                      <line x1="8" y1="5.5" x2="10" y2="17" stroke="white" strokeWidth="0.6" />
                      <line x1="14" y1="7" x2="16" y2="18.5" stroke="white" strokeWidth="0.6" />
                    </svg>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ThinkingCard;
