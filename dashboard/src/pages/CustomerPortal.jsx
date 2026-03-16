import { useState, useEffect, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useWebSocket } from '../hooks/useWebSocket.js';
import OrderInput from '../components/OrderInput.jsx';
import QuickReorder from '../components/QuickReorder.jsx';
import OrderProgress from '../components/OrderProgress.jsx';
import OrderConfirmation from '../components/OrderConfirmation.jsx';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001';

function formatDateTime(value) {
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return '—';
  }
}

export default function CustomerPortal() {
  const { customerId } = useParams();
  const { events, connected } = useWebSocket();

  const [customer, setCustomer] = useState(null);
  const [customersList, setCustomersList] = useState([]);
  const [recentOrders, setRecentOrders] = useState([]);
  const [orderState, setOrderState] = useState('idle');
  const [orderResponse, setOrderResponse] = useState(null);
  const [submitTimestamp, setSubmitTimestamp] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [prefillMessage, setPrefillMessage] = useState('');
  const [loadingCustomer, setLoadingCustomer] = useState(true);
  const [expandedOrderId, setExpandedOrderId] = useState(null);
  const [orderDetails, setOrderDetails] = useState({});
  const [pendingClarification, setPendingClarification] = useState(null);
  const [clarificationChoices, setClarificationChoices] = useState({});

  useEffect(() => {
    if (!customerId) {
      setCustomer(undefined);
      setLoadingCustomer(false);
      (async () => {
        try {
          const res = await fetch(`${API_URL}/api/customers?limit=100`);
          const data = await res.json();
          setCustomersList(data?.data ?? []);
        } catch {
          setCustomersList([]);
        }
      })();
      return;
    }
    setCustomer(undefined);
    setLoadingCustomer(true);
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/customers/${customerId}`);
        if (cancelled) return;
        if (!res.ok) {
          setCustomer(null);
          return;
        }
        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          setCustomer(null);
          return;
        }
        const data = await res.json();
        const c = data?.data ?? data;
        if (!cancelled && c && typeof c === 'object' && (c.customer_id != null || c.name != null)) setCustomer(c);
        else if (!cancelled) setCustomer(null);
      } catch (err) {
        if (!cancelled) setCustomer(null);
      } finally {
        if (!cancelled) setLoadingCustomer(false);
      }
    })();
    return () => { cancelled = true; };
  }, [customerId]);

  useEffect(() => {
    if (!customerId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/orders?customer_id=${customerId}&limit=10`);
        if (cancelled) return;
        const data = await res.json();
        setRecentOrders(data?.data ?? []);
      } catch (err) {
        if (!cancelled) setRecentOrders([]);
      }
    })();
    return () => { cancelled = true; };
  }, [customerId]);

  const orderEvents = useMemo(() => {
    if (!submitTimestamp) return [];
    const orderId = orderResponse?.order_id;
    return events.filter((ev) => {
      const evTime = ev.timestamp ? new Date(ev.timestamp).getTime() : 0;
      if (evTime < submitTimestamp - 2000) return false;
      if (ev.order_id === 'pending') return true;
      if (orderId && ev.order_id === orderId) return true;
      if (ev.type === 'agent_activity') return true;
      return false;
    });
  }, [events, submitTimestamp, orderResponse?.order_id]);

  const handleSubmit = async (message, choices = {}) => {
    setOrderState('processing');
    setSubmitTimestamp(Date.now());
    setOrderResponse(null);
    setErrorMessage(null);
    setPrefillMessage('');
    setPendingClarification(null);
    setClarificationChoices({});
    try {
      const res = await fetch(`${API_URL}/api/ingest/web`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: customerId,
          message,
          channel: 'web',
          clarification_choices: choices,
        }),
      });
      const errBody = await res.json().catch(() => ({}));
      const detail = errBody.detail ?? (typeof errBody === 'string' ? errBody : null);
      if (!res.ok) {
        if (res.status === 504) {
          setErrorMessage('Order is taking longer than expected, please wait...');
        } else if (res.status === 404) {
          setErrorMessage(detail || 'Customer not found');
        } else {
          setErrorMessage(detail || `Order failed (${res.status})`);
        }
        setOrderState('error');
        return;
      }
      setOrderResponse(errBody);
      setOrderState('done');
      if (errBody?.status === 'awaiting_customer_confirmation' && Array.isArray(errBody?.unresolved_mentions) && errBody.unresolved_mentions.length > 0) {
        setPendingClarification({ message, unresolved_mentions: errBody.unresolved_mentions });
      } else {
        setPrefillMessage(''); // clear textarea after successful confirmation
        // Refetch recent orders so "Last order" and list stay in sync
        if (customerId) {
          fetch(`${API_URL}/api/orders?customer_id=${customerId}&limit=10`)
            .then((r) => r.json())
            .then((d) => setRecentOrders(d?.data ?? []))
            .catch(() => {});
        }
      }
    } catch (err) {
      setErrorMessage(err.message || 'Order failed');
      setOrderState('error');
    }
  };

  const handlePlaceAnother = () => {
    setOrderState('idle');
    setOrderResponse(null);
    setErrorMessage(null);
    setPrefillMessage('');
    setPendingClarification(null);
    setClarificationChoices({});
  };



  const canSubmitClarification = useMemo(() => {
    if (!pendingClarification?.unresolved_mentions?.length) return false;
    return pendingClarification.unresolved_mentions.every((m) => Boolean((clarificationChoices[m.phrase] || '').trim()));
  }, [pendingClarification, clarificationChoices]);

  const handleClarificationSubmit = () => {
    if (!pendingClarification?.message || !canSubmitClarification || orderState === 'processing') return;
    handleSubmit(pendingClarification.message, clarificationChoices);
  };

  const hasResolvedCustomer = customer !== undefined;
  const hasValidCustomer =
    customer != null &&
    typeof customer === 'object' &&
    (customer.customer_id != null || customer.name != null);

  if (customerId && (!hasResolvedCustomer || loadingCustomer)) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center max-w-lg mx-auto p-4">
        <p className="text-gray-600">Loading customer...</p>
      </div>
    );
  }

  if (!customerId) {
    return (
      <div className="min-h-screen bg-white text-gray-900 max-w-lg mx-auto px-4 py-6">
        <header className="mb-6">
          <h1 className="text-xl font-semibold">FreshFlow 🐟</h1>
          <p className="text-sm text-gray-500 mt-1">Select a customer to place an order</p>
        </header>
        <ul className="space-y-2">
          {(customersList.length === 0 && !loadingCustomer) && (
            <li className="text-gray-500 text-sm">No customers found.</li>
          )}
          {customersList.map((c) => (
            <li key={c.customer_id}>
              <Link
                to={`/order/${c.customer_id}`}
                className="block rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50 hover:border-gray-300"
              >
                <span className="font-medium">{c.name || c.customer_id}</span>
                <span className="text-gray-500 text-sm ml-2">
                  {c.type ? c.type.replace(/_/g, ' ') : ''} · {c.customer_id}
                </span>
              </Link>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-sm text-gray-500">
          <Link to="/" className="text-blue-600 hover:underline">Back to Dashboard</Link>
        </p>
      </div>
    );
  }

  if (customerId && (customer == null || !hasValidCustomer)) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center max-w-lg mx-auto p-4">
        <p className="text-center text-gray-700">
          Customer not found. <Link to="/order" className="text-blue-600 hover:underline">Select another customer</Link> or contact your sales rep.
        </p>
      </div>
    );
  }

  if (!customer || typeof customer !== 'object') {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center max-w-lg mx-auto p-4">
        <p className="text-gray-600">Loading...</p>
      </div>
    );
  }

  const name = customer?.name ?? 'there';
  const type = typeof customer?.type === 'string' ? customer.type : '';
  let deliveryDays = '';
  try {
    const d = customer?.delivery_days;
    if (Array.isArray(d)) deliveryDays = d.join(', ');
    else if (d != null && typeof d === 'string') deliveryDays = d;
  } catch (_) {}

  return (
    <div className="min-h-screen bg-white text-gray-900 max-w-lg mx-auto px-4 py-4">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold">FreshFlow 🐟</h1>
          <p className="text-base mt-0.5">Hi, {name}!</p>
          <p className="text-sm text-gray-500">
            {type ? type.replace(/_/g, ' ') : ''} {deliveryDays ? `· Delivers ${deliveryDays}` : ''}
          </p>
          <Link to="/order" className="text-xs text-blue-600 hover:underline mt-1 inline-block">Switch customer</Link>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 text-sm ${connected ? 'text-green-600' : 'text-amber-600'}`}
        >
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-amber-500'}`} />
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </header>

      <section className="mb-6">
        <QuickReorder
          recentOrders={recentOrders}
          onReorder={handleSubmit}
          onPrefill={setPrefillMessage}
          disabled={orderState === 'processing'}
          apiUrl={API_URL}
        />
      </section>

      {recentOrders.length > 0 && (
        <section className="mb-6 rounded-lg border border-gray-200 bg-white overflow-hidden">
          <h3 className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-sm font-medium text-gray-700">Order history</h3>
          <ul className="divide-y divide-gray-100">
            {recentOrders.map((o) => (
              <li key={o.order_id} className="border-b border-gray-100 last:border-b-0">
                <button
                  type="button"
                  className="w-full px-4 py-2 flex flex-wrap items-center justify-between gap-2 text-sm text-left hover:bg-gray-50"
                  onClick={() => {
                    const next = expandedOrderId === o.order_id ? null : o.order_id;
                    setExpandedOrderId(next);
                    if (next && !orderDetails[next]) {
                      fetch(`${API_URL}/api/orders/${next}`)
                        .then((r) => r.json())
                        .then((data) => {
                          if (data?.data) setOrderDetails((prev) => ({ ...prev, [next]: data.data }));
                        })
                        .catch(() => {});
                    }
                  }}
                >
                  <span className="font-mono text-gray-600">{o.order_id}</span>
                  <span className="text-gray-500">{o.created_at ? formatDateTime(o.created_at) : '—'}</span>
                  <span className="font-medium">${o.total_amount != null ? Number(o.total_amount).toFixed(2) : '0.00'}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${o.status === 'fulfilled' || o.status === 'confirmed' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}`}>
                    {o.status === 'fulfilled' ? 'Fulfilled' : o.status === 'confirmed' ? 'Confirmed' : o.status}
                  </span>
                  <span className="text-gray-400">{expandedOrderId === o.order_id ? '▼' : '▶'}</span>
                </button>
                {expandedOrderId === o.order_id && (
                  <div className="px-4 pb-3 pt-0 bg-gray-50 border-t border-gray-100">
                    {orderDetails[o.order_id]?.items?.length > 0 ? (
                      <ul className="text-sm text-gray-700 space-y-1">
                        {orderDetails[o.order_id].items.map((it, i) => (
                          <li key={i} className="flex flex-wrap gap-x-2 gap-y-0.5">
                            <span className="font-mono text-gray-600">{it.sku_id}</span>
                            {(it.product_name ?? it.raw_text) && <span className="text-gray-600">({it.product_name ?? it.raw_text})</span>}
                            <span>×{Number(it.quantity)}</span>
                            {it.line_total != null && <span className="text-gray-500">${Number(it.line_total).toFixed(2)}</span>}
                          </li>
                        ))}
                      </ul>
                    ) : !orderDetails[o.order_id] ? (
                      <p className="text-sm text-gray-500">Loading items…</p>
                    ) : (
                      <p className="text-sm text-gray-500">No line items.</p>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}



      {pendingClarification?.unresolved_mentions?.length > 0 && (
        <section className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="text-sm font-semibold text-amber-900 mb-2">Confirm items before placing order</h3>
          <p className="text-sm text-amber-800 mb-3">We found ambiguous item mentions. Pick the correct SKU for each phrase.</p>
          <div className="space-y-3">
            {pendingClarification.unresolved_mentions.map((mention) => (
              <div key={mention.phrase} className="rounded border border-amber-200 bg-white p-3">
                <p className="text-sm text-gray-700 mb-2">
                  <span className="font-medium">"{mention.phrase}"</span>
                </p>
                <select
                  className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                  value={clarificationChoices[mention.phrase] || ''}
                  onChange={(e) => setClarificationChoices((prev) => ({ ...prev, [mention.phrase]: e.target.value }))}
                  disabled={orderState === 'processing'}
                >
                  <option value="">Select matching SKU…</option>
                  {(mention.top_candidates || []).map((c) => (
                    <option key={`${mention.phrase}-${c.sku_id}`} value={c.sku_id}>
                      {c.name || c.sku_id} ({c.sku_id})
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={handleClarificationSubmit}
            disabled={!canSubmitClarification || orderState === 'processing'}
            className="mt-4 w-full rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            Confirm selections and place order
          </button>
        </section>
      )}

      <section className="mb-6 rounded-lg border border-gray-200 bg-gray-50 p-4">
        <OrderInput
          onSubmit={handleSubmit}
          disabled={orderState === 'processing'}
          customerName={name}
          value={prefillMessage}
          onChange={setPrefillMessage}
          onClear={() => setPrefillMessage('')}
        />
      </section>

      {errorMessage && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-800">
          {errorMessage}
        </div>
      )}

      {(orderState === 'processing' || (orderState === 'done' && orderEvents.length > 0)) && (
        <section className="mb-6">
          <OrderProgress events={orderEvents} status={orderState} />
        </section>
      )}

      {orderState === 'done' && orderResponse && (
        <section className="mb-6">
          <OrderConfirmation response={orderResponse} onPlaceAnother={handlePlaceAnother} />
        </section>
      )}
    </div>
  );
}
