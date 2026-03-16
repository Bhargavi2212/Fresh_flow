export default function OrderConfirmation({ response, onPlaceAnother }) {
  if (!response) return null;
  const items = response.parsed_items || [];
  const total = response.total_amount != null ? Number(response.total_amount) : 0;
  const status = response.status || 'needs_review';
  const confidence = response.confidence_score != null ? Number(response.confidence_score) : null;
  const hasProcurement = Array.isArray(response.procurement_signals) && response.procurement_signals.length > 0;
  const noItems = !response.order_id || items.length === 0;
  const displayMessage =
    response.message ||
    (noItems
      ? "We couldn't identify any items in your order. Please list the items you need or try 'Reorder last order'."
      : null);

  const confidenceColor = (c) => {
    if (c == null) return 'bg-gray-200';
    if (c >= 0.9) return 'bg-green-600';
    if (c >= 0.7) return 'bg-amber-500';
    return 'bg-red-500';
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        {noItems ? 'Order not placed' : 'Order Confirmation'}
      </h3>
      {displayMessage && (
        <div className="mb-3 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-900">
          {displayMessage}
        </div>
      )}
      {!noItems && (
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="rounded bg-gray-100 px-2 py-1 text-xs font-mono">{response.order_id}</span>
          <span
            className={`rounded px-2 py-1 text-xs font-medium ${
              status === 'confirmed' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'
            }`}
          >
            {status === 'confirmed' ? 'Confirmed' : 'Needs Review'}
          </span>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          {items.length > 0 && (
            <>
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-600">
              <th className="py-2 pr-2">Product</th>
              <th className="py-2 pr-2">Qty</th>
              <th className="py-2 pr-2">Unit Price</th>
              <th className="py-2 pr-2">Line Total</th>
              <th className="py-2">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => {
              const name = item.product_name ?? item.productName ?? item.sku_id ?? '—';
              const qty = item.quantity ?? item.qty ?? '—';
              const unit = item.unit_of_measure ?? item.unit ?? '';
              const up = item.unit_price ?? item.unitPrice;
              const lt = item.line_total ?? item.lineTotal;
              const conf = item.confidence != null ? Number(item.confidence) : null;
              const avail = item.availability_status ?? item.availabilityStatus;
              const note = avail === 'partial' || avail === 'out_of_stock' ? (item.substituted_from || item.substitutedFrom || 'See notes') : null;
              return (
                <tr key={i} className="border-b border-gray-100">
                  <td className="py-2 pr-2">
                    <span>{name}</span>
                    {note && (
                      <span className="block text-amber-600 text-xs mt-0.5">⚠️ {note}</span>
                    )}
                  </td>
                  <td className="py-2 pr-2">{qty} {unit}</td>
                  <td className="py-2 pr-2">{up != null ? `$${Number(up).toFixed(2)}` : '—'}</td>
                  <td className="py-2 pr-2">{lt != null ? `$${Number(lt).toFixed(2)}` : '—'}</td>
                  <td className="py-2">
                    {conf != null && (
                      <div className="flex items-center gap-1">
                        <div className="w-12 h-2 rounded overflow-hidden bg-gray-200">
                          <div
                            className={`h-full rounded ${confidenceColor(conf)}`}
                            style={{ width: `${Math.min(100, conf * 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500">{(conf * 100).toFixed(0)}%</span>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
            </>
          )}
        </table>
      </div>
      <div className="mt-3 pt-3 border-t border-gray-200 flex flex-wrap items-center justify-between gap-2">
        <div>
          {items.length > 0 && (
            <>
              <span className="font-semibold">Total: ${total.toFixed(2)}</span>
              {confidence != null && (
                <span className="ml-2 text-sm text-gray-500">Confidence: {(confidence * 100).toFixed(0)}%</span>
              )}
            </>
          )}
        </div>
        <button
          type="button"
          onClick={onPlaceAnother}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Place Another Order
        </button>
      </div>
      {hasProcurement && (
        <p className="mt-2 text-sm text-amber-700">
          Note: Some items were low in stock. We've placed a purchase order to restock.
        </p>
      )}
    </div>
  );
}
