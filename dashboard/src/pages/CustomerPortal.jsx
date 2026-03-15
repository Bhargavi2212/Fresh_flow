import { useState, useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useWebSocket } from '../hooks/useWebSocket.js';
import OrderInput from '../components/OrderInput.jsx';
import QuickReorder from '../components/QuickReorder.jsx';
import OrderProgress from '../components/OrderProgress.jsx';
import OrderConfirmation from '../components/OrderConfirmation.jsx';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001';

export default function CustomerPortal() {
  const { customerId } = useParams();
  const { events, connected } = useWebSocket();

  const [customer, setCustomer] = useState(null);
  const [recentOrders, setRecentOrders] = useState([]);
  const [orderState, setOrderState] = useState('idle');
  const [orderResponse, setOrderResponse] = useState(null);
  const [submitTimestamp, setSubmitTimestamp] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [prefillMessage, setPrefillMessage] = useState('');
  const [loadingCustomer, setLoadingCustomer] = useState(true);

  useEffect(() => {
    if (!customerId) {
      setLoadingCustomer(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoadingCustomer(true);
      try {
        const res = await fetch(`${API_URL}/api/customers/${customerId}`);
        if (cancelled) return;
        if (res.status === 404) {
          setCustomer(null);
          return;
        }
        const data = await res.json();
        setCustomer(data?.data ?? data);
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
        const res = await fetch(`${API_URL}/api/orders?customer_id=${customerId}&limit=5`);
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

  const handleSubmit = async (message) => {
    setOrderState('processing');
    setSubmitTimestamp(Date.now());
    setOrderResponse(null);
    setErrorMessage(null);
    setPrefillMessage('');
    try {
      const res = await fetch(`${API_URL}/api/ingest/web`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: customerId,
          message,
          channel: 'web',
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
      setPrefillMessage(''); // clear textarea after successful confirmation
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
  };

  if (loadingCustomer) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center max-w-lg mx-auto">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (!customerId || customer === null) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center max-w-lg mx-auto p-4">
        <p className="text-center text-gray-700">
          Customer not found. Contact your sales rep to get set up.
        </p>
      </div>
    );
  }

  const name = customer.name || 'there';
  const type = customer.type || '';
  const deliveryDays = Array.isArray(customer.delivery_days)
    ? customer.delivery_days.join(', ')
    : customer.delivery_days || '';

  return (
    <div className="min-h-screen bg-white text-gray-900 max-w-lg mx-auto px-4 py-4">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold">FreshFlow 🐟</h1>
          <p className="text-base mt-0.5">Hi, {name}!</p>
          <p className="text-sm text-gray-500">
            {type ? type.replace(/_/g, ' ') : ''} {deliveryDays ? `· Delivers ${deliveryDays}` : ''}
          </p>
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
