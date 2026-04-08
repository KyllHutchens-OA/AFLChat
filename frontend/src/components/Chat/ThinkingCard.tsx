interface ThinkingCardProps {
  step: string;
}

const STEPS = [
  { key: 'understand', label: 'Understanding your question' },
  { key: 'sql', label: 'Building query' },
  { key: 'execute', label: 'Fetching data' },
  { key: 'visuali', label: 'Creating visualization' },
  { key: 'respond', label: 'Composing response' },
];

const ThinkingCard: React.FC<ThinkingCardProps> = ({ step }) => {
  const stepLower = step.toLowerCase();
  const activeIdx = STEPS.findIndex(s => stepLower.includes(s.key));

  return (
    <div className="card-apple p-5 animate-fade-in">
      <div className="space-y-3">
        {STEPS.map((s, i) => {
          const isActive = i === activeIdx;
          const isDone = i < activeIdx;
          const isPending = i > activeIdx;

          return (
            <div key={s.key} className="flex items-center gap-3">
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                isActive ? 'bg-afl-accent animate-pulse' :
                isDone ? 'bg-afl-accent' :
                'bg-afl-warm-200'
              }`} />
              <span className={`text-sm ${
                isActive ? 'text-afl-warm-900 font-medium' :
                isDone ? 'text-afl-warm-500' :
                'text-afl-warm-300'
              }`}>
                {s.label}
              </span>
              {isActive && (
                <div className="flex-1 h-1 bg-afl-warm-100 rounded-full overflow-hidden">
                  <div className="h-full bg-afl-accent rounded-full animate-pulse" style={{ width: '60%' }} />
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
