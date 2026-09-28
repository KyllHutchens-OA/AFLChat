// Tiny regex-based SQL highlighter — avoids pulling in prism-react-renderer
// (or similar) for one code block per drawer. Good enough for the read-only
// SELECT statements the agent emits, not a general-purpose SQL parser.
const KEYWORDS = new Set([
  'select', 'from', 'where', 'and', 'or', 'not', 'in', 'as', 'join', 'left', 'right',
  'inner', 'outer', 'on', 'group', 'by', 'order', 'having', 'limit', 'offset', 'desc',
  'asc', 'distinct', 'case', 'when', 'then', 'else', 'end', 'is', 'null', 'between',
  'like', 'ilike', 'union', 'all', 'with', 'over', 'partition', 'count', 'sum', 'avg',
  'min', 'max', 'coalesce', 'cast', 'round', 'extract',
]);

// Token types get their own colour so the query is scannable at a glance:
// keywords (statement shape), strings/numbers (literal filters), comments.
const TOKEN_RE = /(--[^\n]*)|('(?:[^']|'')*')|(\b\d+\.?\d*\b)|([a-zA-Z_][a-zA-Z0-9_]*)|(\s+)|([^\sa-zA-Z0-9_]+)/g;

// Colours chosen for contrast against the dark (#16130F) code block background.
function classify(token: string, isWord: boolean): string {
  if (token.startsWith('--')) return 'text-warm-300 italic';
  if (token.startsWith("'")) return 'text-[#7FDCC4]'; // string literal
  if (isWord && KEYWORDS.has(token.toLowerCase())) return 'text-[#F2B705] font-semibold'; // night-game yellow
  if (/^\d+\.?\d*$/.test(token)) return 'text-[#EB98A5]';
  return 'text-[#F6F1E7]';
}

interface SqlHighlightProps {
  sql: string;
}

const SqlHighlight: React.FC<SqlHighlightProps> = ({ sql }) => {
  const tokens: { text: string; cls: string }[] = [];
  let m: RegExpExecArray | null;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(sql))) {
    const token = m[0];
    const isWord = /^[a-zA-Z_]/.test(token);
    tokens.push({ text: token, cls: classify(token, isWord) });
  }

  return (
    <pre className="text-xs bg-[#16130F] text-[#F6F1E7] rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-words">
      <code>
        {tokens.map((t, i) => (
          <span key={i} className={t.cls || undefined}>
            {t.text}
          </span>
        ))}
      </code>
    </pre>
  );
};

export default SqlHighlight;
