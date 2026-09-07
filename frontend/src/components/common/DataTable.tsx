import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import { useMemo, useState } from 'react';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  sortValue?: (row: T) => string | number;
  className?: string;
}

interface Props<T> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  rowKey: (row: T) => string;
}

export default function DataTable<T>({ columns, data, onRowClick, emptyMessage, rowKey }: Props<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const sorted = useMemo(() => {
    if (!sortKey) return data;
    const col = columns.find((c) => c.key === sortKey);
    if (!col?.sortValue) return data;
    const sortedData = [...data].sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      if (typeof av === 'number' && typeof bv === 'number') return av - bv;
      return String(av).localeCompare(String(bv));
    });
    return sortDir === 'asc' ? sortedData : sortedData.reverse();
  }, [data, columns, sortKey, sortDir]);

  const toggleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 px-4 py-10 text-center text-sm text-slate-500">
        {emptyMessage ?? 'No records found'}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-700/50">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-700/50 bg-slate-900/80">
            {columns.map((col) => (
              <th key={col.key} className={`whitespace-nowrap px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-400 ${col.className ?? ''}`}>
                {col.sortValue ? (
                  <button
                    onClick={() => toggleSort(col.key)}
                    className="flex items-center gap-1.5 uppercase tracking-wider hover:text-cyan-400"
                  >
                    {col.header}
                    {sortKey === col.key ? (
                      sortDir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
                    ) : (
                      <ArrowUpDown className="h-3 w-3 opacity-40" />
                    )}
                  </button>
                ) : (
                  col.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, idx) => (
            <tr
              key={rowKey(row)}
              onClick={() => onRowClick?.(row)}
              className={`border-b border-slate-800/60 text-slate-300 ${
                idx % 2 === 1 ? 'bg-slate-800/20' : ''
              } ${onRowClick ? 'cursor-pointer hover:bg-cyan-500/5' : 'hover:bg-slate-800/40'}`}
            >
              {columns.map((col) => (
                <td key={col.key} className={`px-4 py-2.5 align-middle ${col.className ?? ''}`}>
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
