import { useState, useEffect } from 'react';
import OrderDetail from './OrderDetail.jsx';

/**
 * List of recent orders (newest first). Each row: timestamp, customer, channel icon,
 * status badge. Click expands OrderDetail. Animate new orders from WebSocket.
 */
export default function OrderFeed({ orders, wsOrderEvents, apiUrl, loading }) {
  const [expandedId, setExpandedId] = useState(null);
  const [orderDetails, setOrderDetails] = useState({});

  // Merge REST orders with WS events: show WS "order_received" / "order_confirmed" first, then REST
  const displayOrders = (() => {
    const byId = new Map();
    wsOrderEvents.forEach((ev) => {
      const id = ev.order_id || ev.order_id;
      if (ev.type === 'order_confirmed') {
        byId.set(id, {
          order_id: id,
          customer_id: null,
          customer_name: ev.customer_name,
          channel: ev.channel,
          status: ev.status,
          total_amount: ev.total_amount,
          created_at: ev.timestamp,
          fromWs: true,
          item_count: ev.item_count,
        });
      } else if (ev.type === 'order_received') {
        byId.set(id, {
          order_id: id,
          customer_name: ev.customer_name,
          channel: ev.channel || 'web',
          status: 'pending',
          total_amount: null,
          created_at: ev.timestamp,
          fromWs: true,
        });
      }
    });
    orders.forEach((o) => {
      if (!byId.has(o.order_id)) {
        byId.set(o.order_id, { ...o, fromWs: false });
      }
    });
    return Array.from(byId.values()).sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
      return tb - ta;
    });
  })();

  // Fetch full order detail when expanding
  useEffect(() => {
    if (!expandedId || orderDetails[expandedId]) return;
    let cancelled = false;
    fetch(`${apiUrl}/api/orders/${expandedId}`)
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled && data?.data) setOrderDetails((prev) => ({ ...prev, [expandedId]: data.data }));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [expandedId, apiUrl, orderDetails]);

  if (loading && orders.length === 0) {
    return (
      <section className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="text-lg font-semibold mb-3">Order Feed</h2>
        <p className="text-gray-500 text-sm">Loading…</p>
      </section>
    );
  }

  return (
    <section className="bg-white rounded-lg border border-gray-200 p-4">
      <h2 className="text-lg font-semibold mb-3">Order Feed</h2>
      {displayOrders.length === 0 ? (
        <p className="text-gray-500 text-sm">No orders yet.</p>
      ) : (
        <ul className="space-y-2">
          {displayOrders.map((o) => (
            <li
              key={o.order_id}
              className="border border-gray-200 rounded-lg p-3 hover:bg-gray-50 transition-all"
            >
              <button
                type="button"
                className="w-full text-left flex flex-wrap items-center gap-x-3 gap-y-1"
                onClick={() => setExpandedId(expandedId === o.order_id ? null : o.order_id)}
              >
                <span className="text-xs text-gray-500">
                  {o.created_at ? new Date(o.created_at).toLocaleString() : '—'}
                </span>
                <span className="font-medium">{o.customer_name ?? o.customer_id ?? o.order_id}</span>
                <span className="text-gray-500">
                  {o.channel === 'sms' ? '📱' : '🌐'} {o.channel || 'web'}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded ${
                    o.status === 'confirmed' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'
                  }`}
                >
                  {o.status === 'confirmed' ? 'Confirmed' : o.status === 'needs_review' ? 'Needs Review' : o.status}
                </span>
                <span className="text-gray-500">
                  {o.item_count ?? (o.items?.length) ?? '—'} items
                </span>
                {o.total_amount != null && (
                  <span className="font-mono">${Number(o.total_amount).toFixed(2)}</span>
                )}
                <span className="ml-auto text-gray-400">{expandedId === o.order_id ? '▼' : '▶'}</span>
              </button>
              {expandedId === o.order_id && (
                <OrderDetail
                  order={orderDetails[o.order_id] ?? o}
                  itemCount={o.item_count ?? o.items?.length}
                  totalAmount={o.total_amount}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
