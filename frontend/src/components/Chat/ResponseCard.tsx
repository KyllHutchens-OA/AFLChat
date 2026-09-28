import { useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ChartRenderer from '../Visualization/ChartRenderer';
import DataTable from '../Visualization/DataTable';
import ChartErrorBoundary from '../Common/ChartErrorBoundary';
import FeedbackButton from './FeedbackButton';
import SpoilerBlur from './SpoilerBlur';
import WorkingDrawer, { type Trace } from './WorkingDrawer';
import { looksLikeResult } from '../../utils/spoilerHeuristics';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';

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
  trace?: Trace;
  conversationId?: string | null;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// 'YYYY-MM-DD' -> '26 Sep 2026' (string parsing, so no timezone shift).
const formatDataAsOf = (iso: string): string | null => {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d || m > 12) return null;
  return `${d} ${MONTHS[m - 1]} ${y}`;
};

const ResponseCard: React.FC<ResponseCardProps> = ({ text, visualization, isError, dataAsOf, trace, conversationId }) => {
  const [showNumbers, setShowNumbers] = useState(false);
  const [showWorking, setShowWorking] = useState(false);
  const { hideScores } = useSpoilerMode();
  const asOf = dataAsOf ? formatDataAsOf(dataAsOf) : null;
  const tableData = Array.isArray(visualization?.data) ? visualization.data : null;
  const blurred = hideScores && looksLikeResult(text);

  if (isError) {
    return (
      <div className="card border-l-4 border-l-sherrin-400 p-5">
        <div className="flex items-center gap-2 mb-2 text-sherrin-600">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-sm font-medium">BALL! We got caught holding it.</span>
        </div>
        <div className="chat-markdown text-warm-700">
          <SafeMarkdown text={text} />
        </div>
      </div>
    );
  }

  return (
    <div className="card p-5 animate-fade-in">
      {/* Headline sentence (streamed text) leads — the chart is the hero below it. */}
      <SpoilerBlur active={blurred}>
        <div className="chat-markdown text-warm-900">
          <SafeMarkdown text={text} />
        </div>

        {visualization && (
          <div className="mt-4">
            <ChartErrorBoundary data={tableData} title={visualization?.title}>
              <ChartRenderer spec={visualization} />
            </ChartErrorBoundary>
          </div>
        )}

        {/* The numbers behind the chart, collapsed by default — no nested card,
            no duplicated table pushing the chart below the fold. */}
        {tableData && tableData.length > 0 && (
          <div className="mt-3">
            <button
              onClick={() => setShowNumbers((v) => !v)}
              aria-expanded={showNumbers}
              className="text-xs font-medium text-warm-600 hover:text-ink transition-colors
                         focus-visible:ring-2 focus-visible:ring-sherrin/50 focus-visible:outline-none rounded"
            >
              {showNumbers ? 'Hide the numbers' : 'Show the numbers'} ({tableData.length} row{tableData.length === 1 ? '' : 's'})
            </button>
            {showNumbers && (
              <div className="mt-2">
                <DataTable data={tableData} />
              </div>
            )}
          </div>
        )}
      </SpoilerBlur>

      <div className="flex items-center justify-between mt-3">
        <div className="flex items-center gap-3">
          {asOf && <p className="text-xs text-warm-600">Data as of {asOf}</p>}
          {trace && (
            <button
              onClick={() => setShowWorking(true)}
              className="text-xs font-medium text-warm-500 hover:text-ink underline decoration-warm-300
                         underline-offset-2 transition-colors focus-visible:ring-2 focus-visible:ring-sherrin/50
                         focus-visible:outline-none rounded"
            >
              Show your working
            </button>
          )}
        </div>
        <FeedbackButton compact conversationId={conversationId ?? null} messageText={text} />
      </div>

      {showWorking && trace && <WorkingDrawer trace={trace} onClose={() => setShowWorking(false)} />}
    </div>
  );
};

export default ResponseCard;
