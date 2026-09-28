import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ChartRenderer from '../Visualization/ChartRenderer';
import ChartErrorBoundary from '../Common/ChartErrorBoundary';

// LLM output is untrusted: no images (exfiltration beacons), links open isolated.
const DISALLOWED_ELEMENTS = ['img'];
const MARKDOWN_COMPONENTS: Components = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer nofollow" />,
};

const SafeMarkdown: React.FC<{ text: string }> = ({ text }) => (
  <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    disallowedElements={DISALLOWED_ELEMENTS}
    components={MARKDOWN_COMPONENTS}
  >
    {text}
  </ReactMarkdown>
);

interface ResponseCardProps {
  text: string;
  visualization?: any;
  isError?: boolean;
  dataAsOf?: string;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// 'YYYY-MM-DD' -> '26 Sep 2026' (string parsing, so no timezone shift).
const formatDataAsOf = (iso: string): string | null => {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d || m > 12) return null;
  return `${d} ${MONTHS[m - 1]} ${y}`;
};

const ResponseCard: React.FC<ResponseCardProps> = ({ text, visualization, isError, dataAsOf }) => {
  const asOf = dataAsOf ? formatDataAsOf(dataAsOf) : null;
  if (isError) {
    return (
      <div className="card-apple border-l-4 border-l-red-400 p-5">
        <div className="flex items-center gap-2 mb-2 text-red-600">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-sm font-medium">Something went wrong</span>
        </div>
        <div className="chat-markdown text-afl-warm-700">
          <SafeMarkdown text={text} />
        </div>
      </div>
    );
  }

  return (
    <div className="card-apple p-5 animate-fade-in">
      <div className="chat-markdown text-afl-warm-900">
        <SafeMarkdown text={text} />
      </div>
      {visualization && (
        <>
          <div className="border-t border-afl-warm-100 my-4" />
          <ChartErrorBoundary
            data={Array.isArray(visualization?.data) ? visualization.data : null}
            title={visualization?.title}
          >
            <ChartRenderer spec={visualization} />
          </ChartErrorBoundary>
        </>
      )}
      {asOf && <p className="mt-3 text-xs text-afl-warm-600">Data as of {asOf}</p>}
    </div>
  );
};

export default ResponseCard;
