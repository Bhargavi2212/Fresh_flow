import { useMemo } from 'react';

/**
 * Expandable order detail: raw message, line items with confidence colors,
 * inventory status, substitutions, agent trace summary.
 */
export default function OrderDetail({ order, itemCount, totalAmount }) {
  const items = order?.items ?? [];
  const trace = order?.agent_trace ?? {};
  const rawMessage = order?.raw_message ?? '';

  const confidenceClass = (c) => {
    if (c == null) return 'text-gray-500';
    const v = Number(c);
    if (v >= 0.9) return 'text-green-700';
    if (v >= 0.7) return 'text-amber-700';
    return 'text-red-700';
  };

  return (
    <div className="mt-2 text-left space-y-2 text-sm border-t border-gray-200 pt-2">
      {rawMessage && (
        <div>
          <span className="font-medium text-gray-600">Raw message:</span>
          <p className="mt-0.5 text-gray-700 bg-gray-50 p-2 rounded break-words">{rawMessage}</p>
        </div>
      )}
      {items.length > 0 && (
        <div>
          <span className="font-medium text-gray-600">Line items:</span>
          <ul className="mt-1 space-y-1">
            {items.map((it, i) => (
              <li key={i} className="flex flex-wrap gap-x-2 gap-y-0.5">
                <span className="font-mono">{it.sku_id}</span>
                <span>×{Number(it.quantity)}</span>
                {it.match_confidence != null && (
                  <span className={confidenceClass(it.match_confidence)}>
                    {(Number(it.match_confidence) * 100).toFixed(0)}%
                  </span>
                )}
                {it.status && <span className="text-gray-500">({it.status})</span>}
                {it.substituted_from && (
                  <span className="text-amber-600">subst. from {it.substituted_from}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {Object.keys(trace).length > 0 && (
        <div>
          <span className="font-medium text-gray-600">Agent trace:</span>
          <pre className="mt-0.5 text-xs bg-gray-50 p-2 rounded overflow-auto max-h-32">
            {JSON.stringify(trace, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
