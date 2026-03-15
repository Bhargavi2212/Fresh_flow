import { useState } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001';

export default function QuickReorder({ recentOrders, onReorder, onPrefill, disabled, apiUrl }) {
  const [loading, setLoading] = useState(false);
  const baseUrl = apiUrl || API_URL;
  const lastOrder = recentOrders?.[0];

  const handleTheUsual = () => {
    onReorder('the usual please');
  };

  const handleReorderLast = async () => {
    if (!lastOrder?.order_id || disabled) return;
    setLoading(true);
    try {
      const res = await fetch(`${baseUrl}/api/orders/${lastOrder.order_id}`);
      if (!res.ok) return;
      const data = await res.json();
      const raw = data?.data?.raw_message ?? data?.raw_message ?? '';
      if (onPrefill && typeof onPrefill === 'function') {
        onPrefill(raw);
      } else {
        onReorder(raw || lastOrder.raw_message || '');
      }
    } catch (err) {
      if (lastOrder.raw_message) onReorder(lastOrder.raw_message);
    } finally {
      setLoading(false);
    }
  };

  const dateStr = lastOrder?.created_at
    ? new Date(lastOrder.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    : '';
  const totalStr = lastOrder?.total_amount != null ? `$${Number(lastOrder.total_amount).toFixed(0)}` : '';

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Quick Reorder</h3>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleTheUsual}
          disabled={disabled || loading}
          className="rounded-lg bg-teal-600 px-3 py-2 text-sm font-medium text-white hover:bg-teal-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          📋 The Usual
        </button>
        <button
          type="button"
          onClick={handleReorderLast}
          disabled={disabled || loading || !lastOrder}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:bg-gray-100 disabled:cursor-not-allowed"
        >
          {loading ? '...' : '🔄 Reorder Last'}
        </button>
      </div>
      {lastOrder && (
        <p className="mt-2 text-sm text-gray-500">
          Last order ({dateStr}): {totalStr}
          {lastOrder.raw_message && (
            <span className="block truncate mt-0.5">{(lastOrder.raw_message || '').slice(0, 60)}…</span>
          )}
        </p>
      )}
    </div>
  );
}
