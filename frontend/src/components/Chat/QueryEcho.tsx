interface QueryEchoProps {
  text: string;
}

const QueryEcho: React.FC<QueryEchoProps> = ({ text }) => {
  return (
    <div className="flex items-center gap-3 py-2 px-4 text-sm text-afl-warm-500">
      <div className="flex-1 border-t border-afl-warm-200" />
      <span className="whitespace-nowrap font-medium">You asked: "{text}"</span>
      <div className="flex-1 border-t border-afl-warm-200" />
    </div>
  );
};

export default QueryEcho;
