interface ThinkingCardProps {
  // Raw backend label (`data.step`), used only when we don't recognise the tool/step.
  step: string;
  // WS `thinking` event carries the real tool name for a tool call, if any.
  tool?: string;
  // `received` (before any work) | `tool` | `review` (model re-checking a
  // tool result before answering or calling another tool).
  currentStep?: string;
}

// Real pipeline steps, in footy voice — this is the "show real progress"
// fix: previously a fuzzy keyword match on backend strings, now driven by
// the actual tool name the WS `thinking` event carries.
const TOOL_COPY: Record<string, string> = {
  resolve_entities: "Working out who's who...",
  player_stats: 'Checking the stats...',
  leaderboard: 'Checking the stats...',
  team_results: 'Checking the stats...',
  head_to_head: 'Checking the stats...',
  match_lookup: 'Checking the stats...',
  ladder: 'Building the ladder...',
  news: 'Checking the news...',
  run_sql: 'Checking the stats...',
  make_chart: 'Drawing it up...',
};

const STEP_COPY: Record<string, string> = {
  received: 'Having a crack...',
  review: 'Going upstairs to the ARC...',
};

function microcopy(step: string, tool?: string, currentStep?: string): string {
  if (tool && TOOL_COPY[tool]) return TOOL_COPY[tool];
  if (currentStep && STEP_COPY[currentStep]) return STEP_COPY[currentStep];
  return step || 'Thinking...';
}

const ThinkingCard: React.FC<ThinkingCardProps> = ({ step, tool, currentStep }) => {
  const label = microcopy(step, tool, currentStep);

  return (
    <div className="card p-5 animate-fade-in" role="status">
      <div className="flex items-center gap-3">
        <div className="relative h-6 w-6 flex-shrink-0 overflow-hidden">
          <svg
            className="football-dribble absolute bottom-0 h-5 w-5 text-sherrin"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <ellipse cx="12" cy="12" rx="10" ry="7" transform="rotate(-30 12 12)" />
            <line x1="5" y1="8" x2="19" y2="16" stroke="white" strokeWidth="0.8" />
            <line x1="8" y1="5.5" x2="10" y2="17" stroke="white" strokeWidth="0.6" />
            <line x1="14" y1="7" x2="16" y2="18.5" stroke="white" strokeWidth="0.6" />
          </svg>
        </div>
        <span className="text-sm font-medium text-warm-900">{label}</span>
      </div>
    </div>
  );
};

export default ThinkingCard;
