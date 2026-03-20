import { useState, useEffect, useCallback } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || '';

type TimeRange = 24 | 168 | 720;

interface TrafficPoint {
  time: string;
  views: number;
  unique_visitors: number;
}

interface TrafficData {
  total_views: number;
  unique_visitors: number;
  unique_ips: number;
  views_by_page: { page: string; views: number }[];
  time_series: TrafficPoint[];
}

interface UsageData {
  total_requests: number;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  by_model: {
    model: string;
    requests: number;
    cost: number;
    input_tokens: number;
    output_tokens: number;
  }[];
  time_series: { time: string; requests: number; cost: number; tokens: number }[];
  limits: {
    daily_budget_usd: number;
    today_spent_usd: number;
    remaining_usd: number;
    per_visitor_limit: number;
  };
}

interface ConversationMessage {
  role: string;
  content: string;
  timestamp: string;
}

interface ConversationData {
  id: string;
  id_short: string;
  chat_type: string;
  messages: ConversationMessage[];
  message_count: number;
  updated_at: string | null;
}

interface ConversationsResponse {
  conversations: ConversationData[];
  total_conversations: number;
  message_counts_by_type: Record<string, number>;
}

interface ReportData {
  id: number;
  conversation_id: string | null;
  message_text: string | null;
  what_happened: string;
  what_expected: string | null;
  page_url: string | null;
  created_at: string;
  conversation_messages: ConversationMessage[];
}

const RANGE_LABELS: Record<TimeRange, string> = {
  24: 'Today',
  168: '7 days',
  720: '30 days',
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('en-AU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

// Simple bar chart using divs
function MiniBarChart<T extends { time: string }>({
  data,
  valueKey,
  height = 80,
  color = '#3b82f6',
}: {
  data: T[];
  valueKey: keyof T;
  height?: number;
  color?: string;
}) {
  if (!data.length) return <div className="text-apple-gray-400 text-sm py-4">No data</div>;

  const values = data.map((d) => (d[valueKey] as number) || 0);
  const max = Math.max(...values, 1);

  return (
    <div className="flex items-end gap-px" style={{ height }}>
      {data.map((d, i) => {
        const val = values[i];
        const h = (val / max) * height;
        const label = data.length <= 24 ? formatTime(d.time) : formatDate(d.time);
        return (
          <div
            key={i}
            className="flex-1 min-w-0 group relative"
            style={{ height }}
          >
            <div
              className="absolute bottom-0 w-full rounded-t transition-all"
              style={{ height: Math.max(h, 1), backgroundColor: color, opacity: 0.8 }}
            />
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block
                            bg-apple-gray-900 text-white text-xs px-2 py-1 rounded whitespace-nowrap z-10">
              {label}: {val}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white/60 backdrop-blur rounded-xl p-4 border border-apple-gray-200/50">
      <div className="text-2xl font-semibold text-apple-gray-900">{value}</div>
      <div className="text-xs text-apple-gray-500 mt-1">{label}</div>
      {sub && <div className="text-xs text-apple-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

const ANALYTICS_PASSWORD = 'NotAnotherCommentator!';

const Analytics = () => {
  const [authed, setAuthed] = useState(() => sessionStorage.getItem('analytics_authed') === '1');
  const [passwordInput, setPasswordInput] = useState('');
  const [passwordError, setPasswordError] = useState(false);
  const [hours, setHours] = useState<TimeRange>(24);
  const [traffic, setTraffic] = useState<TrafficData | null>(null);
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [convos, setConvos] = useState<ConversationsResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'traffic' | 'usage' | 'logs' | 'reports'>('traffic');
  const [expandedConvo, setExpandedConvo] = useState<string | null>(null);
  const [chatFilter, setChatFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [reports, setReports] = useState<ReportData[]>([]);
  const [expandedReport, setExpandedReport] = useState<number | null>(null);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (passwordInput === ANALYTICS_PASSWORD) {
      sessionStorage.setItem('analytics_authed', '1');
      setAuthed(true);
      setPasswordError(false);
    } else {
      setPasswordError(true);
    }
  };

  if (!authed) {
    return (
      <div className="max-w-sm mx-auto px-4 py-32">
        <form onSubmit={handleLogin} className="bg-white/60 backdrop-blur rounded-xl p-6 border border-apple-gray-200/50">
          <h1 className="text-xl font-semibold text-apple-gray-900 mb-4">Analytics</h1>
          <input
            type="password"
            value={passwordInput}
            onChange={(e) => { setPasswordInput(e.target.value); setPasswordError(false); }}
            placeholder="Password"
            autoFocus
            className={`w-full px-3 py-2 rounded-lg border text-sm bg-white
              ${passwordError ? 'border-red-400' : 'border-apple-gray-200'}
              focus:outline-none focus:ring-2 focus:ring-apple-blue-500/30 focus:border-apple-blue-500`}
          />
          {passwordError && (
            <p className="text-xs text-red-500 mt-1.5">Incorrect password</p>
          )}
          <button
            type="submit"
            className="w-full mt-3 px-4 py-2 text-sm font-medium text-white bg-apple-blue-500 rounded-lg
                       hover:bg-apple-blue-600 transition-colors"
          >
            Enter
          </button>
        </form>
      </div>
    );
  }

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [trafficRes, usageRes, convosRes, reportsRes] = await Promise.all([
        fetch(`${API_BASE}/api/analytics/traffic?hours=${hours}`),
        fetch(`${API_BASE}/api/analytics/api-usage?hours=${hours}`),
        fetch(`${API_BASE}/api/analytics/conversations?hours=${hours}`),
        fetch(`${API_BASE}/api/analytics/reports`),
      ]);

      if (trafficRes.ok) setTraffic(await trafficRes.json());
      if (usageRes.ok) setUsage(await usageRes.json());
      if (convosRes.ok) setConvos(await convosRes.json());
      if (reportsRes.ok) {
        const data = await reportsRes.json();
        setReports(data.reports || []);
      }
    } catch (e) {
      console.error('Failed to fetch analytics:', e);
    }
    setLoading(false);
  }, [hours]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filteredConvos = convos?.conversations.filter(
    (c) => chatFilter === 'all' || c.chat_type === chatFilter
  );

  const handleDownload = () => {
    window.open(`${API_BASE}/api/analytics/conversations/download?hours=${hours}`, '_blank');
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-semibold text-apple-gray-900">Analytics</h1>
        <div className="flex gap-1 bg-apple-gray-100 rounded-lg p-0.5">
          {([24, 168, 720] as TimeRange[]).map((h) => (
            <button
              key={h}
              onClick={() => setHours(h)}
              className={`px-3 py-1.5 text-sm rounded-md transition-all ${
                hours === h
                  ? 'bg-white text-apple-gray-900 shadow-sm font-medium'
                  : 'text-apple-gray-500 hover:text-apple-gray-700'
              }`}
            >
              {RANGE_LABELS[h]}
            </button>
          ))}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-apple-gray-200">
        {(['traffic', 'usage', 'logs', 'reports'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-all -mb-px ${
              activeTab === tab
                ? 'border-apple-blue-500 text-apple-blue-500'
                : 'border-transparent text-apple-gray-500 hover:text-apple-gray-700'
            }`}
          >
            {tab === 'traffic' ? 'Traffic'
              : tab === 'usage' ? 'API Usage'
              : tab === 'logs' ? 'Conversation Logs'
              : (
                <span className="flex items-center gap-1.5">
                  Reports
                  {reports.length > 0 && (
                    <span className="inline-flex items-center justify-center w-4 h-4 text-xs rounded-full bg-red-100 text-red-600 font-semibold">
                      {reports.length}
                    </span>
                  )}
                </span>
              )}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-16 text-apple-gray-400">Loading...</div>
      ) : (
        <>
          {/* Traffic Tab */}
          {activeTab === 'traffic' && traffic && (
            <div className="space-y-6">
              <div className="grid grid-cols-3 gap-3">
                <StatCard label="Page Views" value={traffic.total_views} />
                <StatCard label="Unique Visitors" value={traffic.unique_visitors} />
                <StatCard label="Unique IPs" value={traffic.unique_ips} />
              </div>

              <div className="bg-white/60 backdrop-blur rounded-xl p-5 border border-apple-gray-200/50">
                <h3 className="text-sm font-medium text-apple-gray-700 mb-3">
                  Views per hour
                </h3>
                <MiniBarChart data={traffic.time_series} valueKey="views" height={100} />
              </div>

              {traffic.views_by_page.length > 0 && (
                <div className="bg-white/60 backdrop-blur rounded-xl p-5 border border-apple-gray-200/50">
                  <h3 className="text-sm font-medium text-apple-gray-700 mb-3">Pages</h3>
                  <div className="space-y-2">
                    {traffic.views_by_page.map((p) => (
                      <div key={p.page} className="flex justify-between text-sm">
                        <span className="text-apple-gray-700 truncate">{p.page}</span>
                        <span className="text-apple-gray-500 ml-4 tabular-nums">{p.views}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* API Usage Tab */}
          {activeTab === 'usage' && usage && (
            <div className="space-y-6">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard label="Requests" value={usage.total_requests} />
                <StatCard
                  label="Cost"
                  value={`$${usage.total_cost_usd.toFixed(4)}`}
                />
                <StatCard
                  label="Input Tokens"
                  value={usage.total_input_tokens.toLocaleString()}
                />
                <StatCard
                  label="Output Tokens"
                  value={usage.total_output_tokens.toLocaleString()}
                />
              </div>

              {/* Budget bar */}
              <div className="bg-white/60 backdrop-blur rounded-xl p-5 border border-apple-gray-200/50">
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-apple-gray-700 font-medium">Daily Budget</span>
                  <span className="text-apple-gray-500">
                    ${usage.limits.today_spent_usd.toFixed(4)} / ${usage.limits.daily_budget_usd.toFixed(2)}
                  </span>
                </div>
                <div className="h-2 bg-apple-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, (usage.limits.today_spent_usd / usage.limits.daily_budget_usd) * 100)}%`,
                      backgroundColor:
                        usage.limits.today_spent_usd / usage.limits.daily_budget_usd > 0.8
                          ? '#ef4444'
                          : usage.limits.today_spent_usd / usage.limits.daily_budget_usd > 0.5
                          ? '#f59e0b'
                          : '#22c55e',
                    }}
                  />
                </div>
                <div className="text-xs text-apple-gray-400 mt-1">
                  ${usage.limits.remaining_usd.toFixed(4)} remaining &middot;{' '}
                  {usage.limits.per_visitor_limit} requests/visitor/day
                </div>
              </div>

              {/* Cost time series */}
              {usage.time_series.length > 0 && (
                <div className="bg-white/60 backdrop-blur rounded-xl p-5 border border-apple-gray-200/50">
                  <h3 className="text-sm font-medium text-apple-gray-700 mb-3">
                    Requests per hour
                  </h3>
                  <MiniBarChart
                    data={usage.time_series}
                    valueKey="requests"
                    height={80}
                    color="#8b5cf6"
                  />
                </div>
              )}

              {/* By model */}
              {usage.by_model.length > 0 && (
                <div className="bg-white/60 backdrop-blur rounded-xl p-5 border border-apple-gray-200/50">
                  <h3 className="text-sm font-medium text-apple-gray-700 mb-3">By Model</h3>
                  <div className="space-y-2">
                    {usage.by_model.map((m) => (
                      <div key={m.model} className="flex justify-between text-sm">
                        <span className="text-apple-gray-700 font-mono text-xs">{m.model}</span>
                        <span className="text-apple-gray-500 tabular-nums">
                          {m.requests} req &middot; ${m.cost.toFixed(4)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Reports Tab */}
          {activeTab === 'reports' && (
            <div className="space-y-4">
              <div className="text-xs text-apple-gray-400">{reports.length} report{reports.length !== 1 ? 's' : ''}</div>

              {reports.length === 0 && (
                <div className="text-center py-12 text-apple-gray-400 text-sm">No reports yet</div>
              )}

              <div className="space-y-2">
                {reports.map((report) => (
                  <div
                    key={report.id}
                    className="bg-white/60 backdrop-blur rounded-xl border border-apple-gray-200/50 overflow-hidden"
                  >
                    <button
                      onClick={() => setExpandedReport(expandedReport === report.id ? null : report.id)}
                      className="w-full flex items-start justify-between px-4 py-3 text-left hover:bg-apple-gray-50/50 transition-colors"
                    >
                      <div className="flex-1 min-w-0 pr-4">
                        <p className="text-sm text-apple-gray-800 truncate">{report.what_happened}</p>
                        {report.message_text && (
                          <p className="text-xs text-apple-gray-400 truncate mt-0.5 italic">
                            Re: "{report.message_text.slice(0, 80)}{report.message_text.length > 80 ? '…' : ''}"
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <span className="text-xs text-apple-gray-400">
                          {report.created_at ? formatTimestamp(report.created_at) : ''}
                        </span>
                        <svg
                          className={`w-4 h-4 text-apple-gray-400 transition-transform ${expandedReport === report.id ? 'rotate-180' : ''}`}
                          fill="none" stroke="currentColor" viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                    </button>

                    {expandedReport === report.id && (
                      <div className="border-t border-apple-gray-200/50 px-4 py-4 space-y-4">
                        {/* Report fields */}
                        <div className="space-y-3">
                          <div>
                            <p className="text-xs font-medium text-apple-gray-500 uppercase mb-1">What went wrong</p>
                            <p className="text-sm text-apple-gray-800 whitespace-pre-wrap">{report.what_happened}</p>
                          </div>
                          {report.what_expected && (
                            <div>
                              <p className="text-xs font-medium text-apple-gray-500 uppercase mb-1">What was expected</p>
                              <p className="text-sm text-apple-gray-800 whitespace-pre-wrap">{report.what_expected}</p>
                            </div>
                          )}
                          {report.message_text && (
                            <div>
                              <p className="text-xs font-medium text-apple-gray-500 uppercase mb-1">AI message</p>
                              <p className="text-sm text-apple-gray-600 bg-apple-gray-50 rounded-lg px-3 py-2 whitespace-pre-wrap">{report.message_text}</p>
                            </div>
                          )}
                          {report.conversation_id && (
                            <p className="text-xs text-apple-gray-400 font-mono">conv: {report.conversation_id}</p>
                          )}
                        </div>

                        {/* Conversation log */}
                        {report.conversation_messages.length > 0 && (
                          <div>
                            <p className="text-xs font-medium text-apple-gray-500 uppercase mb-2">Conversation log</p>
                            <div className="space-y-2 max-h-80 overflow-y-auto">
                              {report.conversation_messages.map((msg, i) => (
                                <div
                                  key={i}
                                  className={`text-sm px-3 py-2 rounded-lg ${
                                    msg.role === 'user'
                                      ? 'bg-apple-blue-50 text-apple-gray-800'
                                      : 'bg-apple-gray-50 text-apple-gray-700'
                                  }`}
                                >
                                  <div className="flex justify-between items-center mb-1">
                                    <span className="text-xs font-medium text-apple-gray-500 uppercase">{msg.role}</span>
                                    <span className="text-xs text-apple-gray-400">
                                      {msg.timestamp ? formatTimestamp(msg.timestamp) : ''}
                                    </span>
                                  </div>
                                  <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Conversations Tab */}
          {activeTab === 'logs' && convos && (
            <div className="space-y-4">
              {/* Filter + download bar */}
              <div className="flex items-center justify-between">
                <div className="flex gap-1 bg-apple-gray-100 rounded-lg p-0.5">
                  {['all', 'afl', 'aflagent'].map((f) => (
                    <button
                      key={f}
                      onClick={() => setChatFilter(f)}
                      className={`px-3 py-1 text-xs rounded-md transition-all ${
                        chatFilter === f
                          ? 'bg-white text-apple-gray-900 shadow-sm font-medium'
                          : 'text-apple-gray-500 hover:text-apple-gray-700'
                      }`}
                    >
                      {f === 'all' ? 'All' : f === 'aflagent' ? 'Agent' : f.charAt(0).toUpperCase() + f.slice(1)}
                    </button>
                  ))}
                </div>
                <button
                  onClick={handleDownload}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-apple-gray-600 hover:text-apple-gray-900
                             bg-white border border-apple-gray-200 rounded-lg hover:shadow-sm transition-all"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download
                </button>
              </div>

              <div className="text-xs text-apple-gray-400">
                {filteredConvos?.length || 0} conversations &middot;{' '}
                {Object.entries(convos.message_counts_by_type)
                  .map(([k, v]) => `${k}: ${v} msgs`)
                  .join(' · ')}
              </div>

              {/* Conversation list */}
              <div className="space-y-2">
                {filteredConvos?.length === 0 && (
                  <div className="text-center py-12 text-apple-gray-400 text-sm">
                    No conversations in this period
                  </div>
                )}
                {filteredConvos?.map((conv) => (
                  <div
                    key={conv.id}
                    className="bg-white/60 backdrop-blur rounded-xl border border-apple-gray-200/50 overflow-hidden"
                  >
                    <button
                      onClick={() =>
                        setExpandedConvo(expandedConvo === conv.id ? null : conv.id)
                      }
                      className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-apple-gray-50/50 transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span
                          className={`inline-block px-2 py-0.5 text-xs rounded-full font-medium ${
                            conv.chat_type === 'aflagent'
                              ? 'bg-purple-100 text-purple-700'
                              : conv.chat_type === 'resume'
                              ? 'bg-amber-100 text-amber-700'
                              : 'bg-blue-100 text-blue-700'
                          }`}
                        >
                          {conv.chat_type === 'aflagent' ? 'agent' : conv.chat_type}
                        </span>
                        <span className="text-sm text-apple-gray-700 truncate">
                          {conv.messages[0]?.content.slice(0, 80) || 'Empty'}
                          {(conv.messages[0]?.content.length || 0) > 80 ? '...' : ''}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 ml-4 shrink-0">
                        <span className="text-xs text-apple-gray-400 tabular-nums">
                          {conv.message_count} msgs
                        </span>
                        <span className="text-xs text-apple-gray-400">
                          {conv.updated_at ? formatTimestamp(conv.updated_at) : ''}
                        </span>
                        <svg
                          className={`w-4 h-4 text-apple-gray-400 transition-transform ${
                            expandedConvo === conv.id ? 'rotate-180' : ''
                          }`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                    </button>

                    {expandedConvo === conv.id && (
                      <div className="border-t border-apple-gray-200/50 px-4 py-3 space-y-2 max-h-96 overflow-y-auto">
                        <div className="text-xs text-apple-gray-400 mb-2 font-mono">{conv.id}</div>
                        {conv.messages.map((msg, i) => (
                          <div
                            key={i}
                            className={`text-sm px-3 py-2 rounded-lg ${
                              msg.role === 'user'
                                ? 'bg-apple-blue-50 text-apple-gray-800'
                                : 'bg-apple-gray-50 text-apple-gray-700'
                            }`}
                          >
                            <div className="flex justify-between items-center mb-1">
                              <span className="text-xs font-medium text-apple-gray-500 uppercase">
                                {msg.role}
                              </span>
                              <span className="text-xs text-apple-gray-400">
                                {msg.timestamp ? formatTimestamp(msg.timestamp) : ''}
                              </span>
                            </div>
                            <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default Analytics;
