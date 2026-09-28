import React from 'react';

interface DataTableProps {
  data: Record<string, unknown>[] | null | undefined;
  title?: string;
  // Embedded inside another card (e.g. behind "Show the numbers" in
  // ResponseCard) — no card chrome of its own. Defaults to true since that's
  // now the only place this renders from; pass false for a standalone table.
  bare?: boolean;
}

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') return Number.isFinite(value) ? value.toLocaleString() : String(value);
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/**
 * Renders a plain table over `spec.data`. This is the fallback used whenever a
 * chart spec can't be safely rendered as a chart (failed validation, an
 * unrecognized shape, or a runtime error caught by ChartErrorBoundary) but the
 * underlying rows are still usable.
 */
const DataTable: React.FC<DataTableProps> = ({ data, title, bare = true }) => {
  if (!data || data.length === 0) return null;

  const columns = Array.from(
    data.reduce((set, row) => {
      Object.keys(row ?? {}).forEach((k) => set.add(k));
      return set;
    }, new Set<string>()),
  );

  if (columns.length === 0) return null;
  const wide = columns.length > 4;

  const table = (
    <>
      {/* Wide tables scroll horizontally — a visible affordance beats a silent
          cut-off edge, since nothing else here hints the table continues. */}
      <div className="relative">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left tabular-nums">
            <thead>
              <tr className="border-b border-warm-100">
                {columns.map((col) => (
                  <th key={col} className="px-3 py-2 font-semibold text-[#6B5B4E] whitespace-nowrap">
                    {humanizeKey(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr key={i} className="border-b border-warm-100/60 last:border-0">
                  {columns.map((col) => (
                    <td key={col} className="px-3 py-2 text-[#3D2E1F] whitespace-nowrap">
                      {formatCell(row?.[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {wide && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-white to-transparent"
          />
        )}
      </div>
      {wide && <p className="mt-1.5 text-xs text-warm-500">Scroll to see more &rarr;</p>}
    </>
  );

  if (bare) return table;

  return (
    <div className="w-full card p-6 my-4">
      {title && (
        <h3 className="text-base font-semibold text-[#3D2E1F] mb-4 text-center">{title}</h3>
      )}
      {table}
    </div>
  );
};

export default DataTable;
