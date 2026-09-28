import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import SqlHighlight from './SqlHighlight';

// Shape of the `trace` WS event / persisted message metadata
// (backend/app/agent/v3/trace.py::build_trace_payload).
interface TraceEntity {
  query: string;
  kind: 'player' | 'team';
  name: string;
  id: number;
}
interface TraceToolCall {
  name: string;
  args: Record<string, unknown>;
  sql: string[];
  row_count: number | null;
  latency_s: number;
  error: string | null;
}
export interface Trace {
  model: string;
  entities: TraceEntity[];
  tool_calls: TraceToolCall[];
  sql: string[];
  row_count: number | null;
  retries: number;
  tokens: Record<string, number>;
  cost_usd: number;
  latency_s: number;
  ttft_s: number | null;
  data_as_of: string;
  error: string | null;
}

interface WorkingDrawerProps {
  trace: Trace;
  onClose: () => void;
}

const formatArgs = (args: Record<string, unknown>): string => {
  const entries = Object.entries(args).filter(([, v]) => v !== null && v !== undefined && v !== '');
  if (!entries.length) return '(no arguments)';
  return entries.map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : String(v)}`).join('  ·  ');
};

const WorkingDrawer: React.FC<WorkingDrawerProps> = ({ trace, onClose }) => {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [copiedAll, setCopiedAll] = useState(false);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const totalTokens = (trace.tokens?.input_tokens || 0) + (trace.tokens?.output_tokens || 0);
  const allSql = trace.tool_calls.flatMap((c) => c.sql).join('\n\n');

  const copyAllSql = async () => {
    try {
      await navigator.clipboard.writeText(allSql);
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 1500);
    } catch {
      // clipboard unavailable — no-op
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="working-drawer-title"
        className="relative w-full sm:max-w-lg max-h-[85vh] bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl border border-warm-200/50 overflow-hidden flex flex-col animate-fade-in"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-warm-100 flex-shrink-0">
          <div>
            <h2 id="working-drawer-title" className="text-base font-semibold text-ink">Show your working</h2>
            <p className="text-xs text-warm-400 mt-0.5">How the agent got this answer</p>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-warm-400 hover:text-warm-600 hover:bg-warm-100 transition-colors focus-visible:ring-2 focus-visible:ring-sherrin/50 focus-visible:outline-none"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="overflow-y-auto px-5 py-4 space-y-5 text-sm">
          {/* Summary stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Latency" value={`${trace.latency_s.toFixed(1)}s`} />
            <Stat label="Tokens" value={totalTokens.toLocaleString()} />
            <Stat label="Cost" value={`$${trace.cost_usd.toFixed(4)}`} />
            <Stat label="Retries" value={String(trace.retries)} />
          </div>

          {trace.data_as_of && (
            <p className="text-xs text-warm-500">Data as of {trace.data_as_of} &middot; model {trace.model}</p>
          )}

          {/* Matched entities */}
          {trace.entities.length > 0 && (
            <section>
              <h3 className="section-label mb-2">Matched entities</h3>
              <ul className="flex flex-wrap gap-1.5">
                {trace.entities.map((e, i) => (
                  <li
                    key={i}
                    className="px-2.5 py-1 rounded-full bg-warm-100 text-warm-700 text-xs"
                    title={`from "${e.query}"`}
                  >
                    {e.name} <span className="text-warm-400">({e.kind})</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Tool calls */}
          <section>
            <h3 className="section-label mb-2">Tool calls ({trace.tool_calls.length})</h3>
            <ol className="space-y-3">
              {trace.tool_calls.map((c, i) => (
                <li key={i} className="border border-warm-100 rounded-lg p-3">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="font-mono text-xs font-semibold text-ink">{c.name}</span>
                    <span className="text-xs text-warm-400 tabular-nums">{c.latency_s.toFixed(2)}s</span>
                  </div>
                  <p className="text-xs text-warm-600 mb-1.5">{formatArgs(c.args)}</p>
                  {c.error ? (
                    <p className="text-xs text-sherrin-600">Error: {c.error}</p>
                  ) : (
                    <p className="text-xs text-warm-500 tabular-nums">
                      {c.row_count === null ? 'no result' : `${c.row_count} row${c.row_count === 1 ? '' : 's'}`}
                    </p>
                  )}
                  {c.sql.map((q, j) => <SqlHighlight key={j} sql={q} />)}
                </li>
              ))}
            </ol>
          </section>

          {trace.sql.length > 0 && (
            <button
              onClick={copyAllSql}
              className="text-xs text-sherrin-600 hover:text-sherrin-700 font-medium"
            >
              {copiedAll ? 'Copied!' : 'Copy all SQL'}
            </button>
          )}

          {trace.error && (
            <p className="text-xs text-sherrin-600">Turn error: {trace.error}</p>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
};

const Stat: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="bg-warm-50 rounded-lg px-3 py-2">
    <div className="text-xs text-warm-500">{label}</div>
    <div className="text-sm font-semibold text-ink tabular-nums">{value}</div>
  </div>
);

export default WorkingDrawer;
