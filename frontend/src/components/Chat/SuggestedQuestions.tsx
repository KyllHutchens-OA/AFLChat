interface SuggestedQuestionsProps {
  teamName?: string | null;
  onSelect: (question: string) => void;
}

const GENERIC_QUESTIONS = [
  "Who won the 2025 grand final?",
  "Top goal kickers of all time",
  "Show me the closest games this season",
  "Which team has the longest winning streak?",
];

const TEAM_QUESTIONS: Record<string, string[]> = {
  default: [
    "How did {team} go last season?",
    "Who is {team}'s all-time leading goal kicker?",
    "{team}'s biggest win ever",
    "Show me {team}'s win/loss record by season",
  ],
};

const SuggestedQuestions: React.FC<SuggestedQuestionsProps> = ({ teamName, onSelect }) => {
  const questions = teamName
    ? (TEAM_QUESTIONS.default).map(q => q.replace('{team}', teamName))
    : GENERIC_QUESTIONS;

  return (
    <div className="flex flex-wrap gap-2 justify-center">
      {questions.map((q) => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          className="px-4 py-2 text-sm rounded-full border border-afl-warm-200 text-afl-warm-700
                     hover:bg-afl-accent hover:text-white hover:border-afl-accent
                     transition-all duration-200"
        >
          {q}
        </button>
      ))}
    </div>
  );
};

export default SuggestedQuestions;
