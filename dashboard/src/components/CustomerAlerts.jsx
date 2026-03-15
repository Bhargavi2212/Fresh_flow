import { useState, useMemo } from 'react';

const ALERT_ICONS = {
  churn_risk: '⚠️',
  upsell: '↑',
  anomaly: '!',
  growth_signal: '★',
  milestone: '★',
};

/**
 * Recent alerts: customer name, alert type icon, description, severity badge.
 * High severity: red left border. PATCH to acknowledge. REST + customer_alert WebSocket.
 */
export default function CustomerAlerts({ alerts, wsEvents, apiUrl, onAck }) {
  const [acking, setAcking] = useState(new Set());

  const displayList = useMemo(() => {
    const byId = new Map();
    alerts.forEach((a) => byId.set(a.id, { ...a, fromWs: false }));
    wsEvents.forEach((ev) => {
      if (ev.alert_id) {
        byId.set(ev.alert_id, {
          id: ev.alert_id,
          customer_name: ev.customer_name,
          alert_type: ev.alert_type,
          description: ev.description,
          severity: ev.severity,
          acknowledged: false,
          created_at: ev.timestamp,
          fromWs: true,
        });
      }
    });
    return Array.from(byId.values()).sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
      return tb - ta;
    });
  }, [alerts, wsEvents]);

  const handleAck = (id) => {
    if (acking.has(id)) return;
    setAcking((s) => new Set(s).add(id));
    fetch(`${apiUrl}/api/customer-alerts/${id}`, { method: 'PATCH' })
      .then(() => onAck?.(id))
      .catch(() => {})
      .finally(() => setAcking((s) => { const n = new Set(s); n.delete(id); return n; }));
  };

  return (
    <section className="bg-white rounded-lg border border-gray-200 p-4">
      <h2 className="text-lg font-semibold mb-3">Customer Intelligence</h2>
      {displayList.length === 0 ? (
        <p className="text-gray-500 text-sm">No alerts yet.</p>
      ) : (
        <ul className="space-y-2">
          {displayList.map((a) => (
            <li
              key={a.id}
              className={`border rounded-lg p-3 ${
                a.severity === 'high' && !a.acknowledged ? 'border-l-4 border-l-red-500' : 'border-gray-200'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <span className="font-medium">{a.customer_name ?? 'Customer'}</span>
                  <span className="ml-2 text-gray-500" title={a.alert_type}>
                    {ALERT_ICONS[a.alert_type] ?? '•'}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-gray-100 ml-2">{a.alert_type}</span>
                  {a.severity && (
                    <span
                      className={`text-xs px-2 py-0.5 rounded ml-1 ${
                        a.severity === 'high' ? 'bg-red-100 text-red-800' : 'bg-gray-100'
                      }`}
                    >
                      {a.severity}
                    </span>
                  )}
                  {a.description && <p className="text-sm text-gray-600 mt-1">{a.description}</p>}
                  {a.created_at && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      {new Date(a.created_at).toLocaleString()}
                    </p>
                  )}
                </div>
                {!a.acknowledged && (
                  <button
                    type="button"
                    disabled={acking.has(a.id)}
                    onClick={() => handleAck(a.id)}
                    className="shrink-0 text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
                  >
                    {acking.has(a.id) ? '…' : 'Ack'}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
