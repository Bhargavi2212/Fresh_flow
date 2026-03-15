import { useState } from 'react';

/**
 * Recent POs: PO number, supplier, item count, total, status badge, timestamp. Expand for line items.
 * Data from REST + purchase_order_created WebSocket.
 */
export default function PurchaseOrders({ purchaseOrders, wsEvents, apiUrl }) {
  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState({});

  const displayList = (() => {
    const byId = new Map();
    purchaseOrders.forEach((po) => byId.set(po.po_id, { ...po, fromWs: false }));
    wsEvents.forEach((ev) => {
      if (ev.po_id) {
        byId.set(ev.po_id, {
          po_id: ev.po_id,
          supplier_name: ev.supplier_name,
          status: 'draft',
          total_amount: ev.total_amount,
          created_at: ev.timestamp,
          items: [],
          fromWs: true,
          item_count: ev.item_count,
        });
      }
    });
    return Array.from(byId.values()).sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
      return tb - ta;
    });
  })();

  const fetchDetail = (poId) => {
    if (detail[poId]) return;
    fetch(`${apiUrl}/api/purchase-orders/${poId}`)
      .then((r) => r.json())
      .then((data) => setDetail((prev) => ({ ...prev, [poId]: data })))
      .catch(() => {});
  };

  return (
    <section className="bg-white rounded-lg border border-gray-200 p-4">
      <h2 className="text-lg font-semibold mb-3">Purchase Orders</h2>
      {displayList.length === 0 ? (
        <p className="text-gray-500 text-sm">No purchase orders yet.</p>
      ) : (
        <ul className="space-y-2">
          {displayList.map((po) => (
            <li key={po.po_id} className="border border-gray-200 rounded-lg p-3">
              <button
                type="button"
                className="w-full text-left flex flex-wrap items-center gap-x-3 gap-y-1"
                onClick={() => {
                  setExpandedId(expandedId === po.po_id ? null : po.po_id);
                  if (expandedId !== po.po_id) fetchDetail(po.po_id);
                }}
              >
                <span className="font-mono font-medium">{po.po_id}</span>
                <span className="text-gray-600">{po.supplier_name ?? po.supplier_id}</span>
                <span className="text-xs px-2 py-0.5 rounded bg-gray-100">{po.status}</span>
                <span className="text-gray-500">
                  {(po.items?.length ?? po.item_count) ?? 0} items
                </span>
                {po.total_amount != null && (
                  <span className="font-mono">${Number(po.total_amount).toFixed(2)}</span>
                )}
                {po.created_at && (
                  <span className="text-xs text-gray-400">
                    {new Date(po.created_at).toLocaleString()}
                  </span>
                )}
                <span className="ml-auto text-gray-400">{expandedId === po.po_id ? '▼' : '▶'}</span>
              </button>
              {expandedId === po.po_id && (
                <div className="mt-2 pt-2 border-t border-gray-100 text-sm space-y-2">
                  {(detail[po.po_id]?.reasoning ?? po.reasoning) && (
                    <p className="text-gray-600 italic">
                      <span className="font-medium text-gray-700">Reasoning: </span>
                      {detail[po.po_id]?.reasoning ?? po.reasoning}
                    </p>
                  )}
                  {(detail[po.po_id]?.items?.length > 0 || po.items?.length > 0) && (
                    <>
                      <span className="font-medium text-gray-600">Line items:</span>
                      <ul className="mt-1 space-y-0.5">
                        {(detail[po.po_id]?.items ?? po.items ?? []).map((it, i) => (
                          <li key={i} className="flex gap-2">
                            <span className="font-mono">{it.sku_id}</span>
                            <span>×{Number(it.quantity)}</span>
                            {it.line_total != null && (
                              <span className="text-gray-500">${Number(it.line_total).toFixed(2)}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
