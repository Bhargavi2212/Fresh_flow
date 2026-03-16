import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useWebSocket } from '../hooks/useWebSocket.js';
import OrderFeed from '../components/OrderFeed.jsx';
import OrderDetail from '../components/OrderDetail.jsx';
import AgentActivityLog from '../components/AgentActivityLog.jsx';
import InventoryPanel from '../components/InventoryPanel.jsx';
import PurchaseOrders from '../components/PurchaseOrders.jsx';
import CustomerAlerts from '../components/CustomerAlerts.jsx';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001';

export default function Dashboard() {
  const { events, connected } = useWebSocket();
  const [stats, setStats] = useState({
    orders_today: 0,
    revenue_today: 0,
    orders_needing_review_today: 0,
    low_stock_count: 0,
    purchase_orders_today: 0,
    active_alerts_count: 0,
  });
  const [orders, setOrders] = useState([]);
  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState('7');
  const [customStart, setCustomStart] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  });
  const [customEnd, setCustomEnd] = useState(() => new Date().toISOString().slice(0, 10));

  useEffect(() => {
    let cancelled = false;
    async function fetchInitial() {
      try {
        const [statsRes, poRes, alertsRes] = await Promise.all([
          fetch(`${API_URL}/api/dashboard/stats`),
          fetch(`${API_URL}/api/purchase-orders?limit=10`),
          fetch(`${API_URL}/api/customer-alerts?limit=10`),
        ]);
        if (cancelled) return;
        const statsData = await statsRes.json();
        if (statsData?.data) setStats((s) => ({ ...s, ...statsData.data }));
        const poData = await poRes.json();
        if (poData?.items) setPurchaseOrders(poData.items);
        const alertsData = await alertsRes.json();
        if (alertsData?.items) setAlerts(alertsData.items);
      } catch (err) {
        console.error('Initial fetch failed', err);
      }
    }
    fetchInitial();
    return () => { cancelled = true; };
  }, []);

  const orderDateParams = useMemo(() => {
    const now = new Date();
    const toDate = (d) => d.toISOString().slice(0, 10);
    if (dateRange === '7') {
      const start = new Date(now);
      start.setDate(start.getDate() - 7);
      return { created_after: toDate(start), created_before: null };
    }
    if (dateRange === '30') {
      const start = new Date(now);
      start.setDate(start.getDate() - 30);
      return { created_after: toDate(start), created_before: null };
    }
    return {
      created_after: customStart || null,
      created_before: customEnd || null,
    };
  }, [dateRange, customStart, customEnd]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const { created_after, created_before } = orderDateParams;
    const params = new URLSearchParams({ limit: '100' });
    if (created_after) params.set('created_after', created_after);
    if (created_before) params.set('created_before', created_before);
    fetch(`${API_URL}/api/orders?${params}`)
      .then((res) => res.json())
      .then((data) => {
        if (!cancelled && data?.data) setOrders(data.data);
      })
      .catch((err) => {
        if (!cancelled) console.error('Orders fetch failed', err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [orderDateParams]);

  const refetchOrders = useCallback(() => {
    const { created_after, created_before } = orderDateParams;
    const params = new URLSearchParams({ limit: '100' });
    if (created_after) params.set('created_after', created_after);
    if (created_before) params.set('created_before', created_before);
    fetch(`${API_URL}/api/orders?${params}`)
      .then((res) => res.json())
      .then((data) => { if (data?.data) setOrders(data.data); })
      .catch((err) => console.error('Orders fetch failed', err));
  }, [orderDateParams]);

  const lastAppliedCount = useRef(0);
  useEffect(() => {
    const toApply = events.slice(0, events.length - lastAppliedCount.current);
    lastAppliedCount.current = events.length;
    toApply.forEach((ev) => {
      if (ev.type === 'order_confirmed') {
        setStats((s) => ({
          ...s,
          orders_today: s.orders_today + 1,
          revenue_today: s.revenue_today + (ev.total_amount || 0),
          orders_needing_review_today:
            ev.status === 'needs_review' ? s.orders_needing_review_today + 1 : s.orders_needing_review_today,
        }));
        setOrders((prev) => {
          if (prev.some((o) => o.order_id === ev.order_id)) return prev;
          return [
            {
              order_id: ev.order_id,
              customer_id: ev.customer_id ?? null,
              customer_name: ev.customer_name ?? null,
              channel: ev.channel ?? 'web',
              status: ev.status ?? 'confirmed',
              total_amount: ev.total_amount ?? null,
              created_at: ev.timestamp ?? new Date().toISOString(),
              item_count: ev.item_count ?? null,
            },
            ...prev,
          ];
        });
      } else if (ev.type === 'purchase_order_created') {
        setStats((s) => ({ ...s, purchase_orders_today: s.purchase_orders_today + 1 }));
      } else if (ev.type === 'customer_alert') {
        setStats((s) => ({ ...s, active_alerts_count: s.active_alerts_count + 1 }));
      } else if (ev.type === 'inventory_update' && ev.is_low_stock) {
        setStats((s) => ({ ...s, low_stock_count: s.low_stock_count + 1 }));
      }
    });
  }, [events]);

  const orderReceivedAndConfirmed = useMemo(() => {
    const byOrderId = new Map();
    events.forEach((ev) => {
      if (ev.type === 'order_received') byOrderId.set(ev.order_id, { ...ev, status: 'pending' });
      if (ev.type === 'order_confirmed' && ev.order_id) {
        byOrderId.set(ev.order_id, { type: 'order_confirmed', ...ev });
      }
    });
    return Array.from(byOrderId.values());
  }, [events]);

  const agentActivityEvents = useMemo(() => events.filter((e) => e.type === 'agent_activity'), [events]);
  const purchaseOrderEvents = useMemo(() => events.filter((e) => e.type === 'purchase_order_created'), [events]);
  const customerAlertEvents = useMemo(() => events.filter((e) => e.type === 'customer_alert'), [events]);

  const hasHighSeverityAlert = useMemo(
    () => alerts.some((a) => a.severity === 'high' && !a.acknowledged),
    [alerts]
  );

  const now = new Date();
  const dateTimeStr = now.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <h1 className="text-xl font-semibold">FreshFlow AI</h1>
        <div className="flex items-center gap-4">
          <span
            className={`inline-flex items-center gap-1.5 text-sm ${connected ? 'text-green-600' : 'text-amber-600'}`}
          >
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-amber-500'}`} />
            {connected ? 'Connected' : 'Disconnected'}
          </span>
          <span className="text-sm text-gray-500">{dateTimeStr}</span>
        </div>
      </header>

      <section className="px-4 py-3 border-b border-gray-200 bg-white">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatCard label="Orders Today" value={stats.orders_today} />
          <StatCard label="Revenue Today" value={`$${Number(stats.revenue_today).toFixed(0)}`} />
          <StatCard label="Needing Review" value={stats.orders_needing_review_today} className="text-amber-700" />
          <StatCard label="Low Stock" value={stats.low_stock_count} className="text-amber-700" />
          <StatCard label="POs Today" value={stats.purchase_orders_today} />
          <StatCard
            label="Active Alerts"
            value={stats.active_alerts_count}
            className={hasHighSeverityAlert ? 'text-red-700 border-red-200' : ''}
          />
        </div>
      </section>

      <main className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-[1600px] mx-auto">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium text-gray-700">Order feed:</span>
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="custom">Custom range</option>
            </select>
            {dateRange === 'custom' && (
              <>
                <label className="flex items-center gap-1.5 text-sm text-gray-600">
                  From
                  <input
                    type="date"
                    value={customStart}
                    onChange={(e) => setCustomStart(e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm"
                  />
                </label>
                <label className="flex items-center gap-1.5 text-sm text-gray-600">
                  To
                  <input
                    type="date"
                    value={customEnd}
                    onChange={(e) => setCustomEnd(e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm"
                  />
                </label>
              </>
            )}
          </div>
          <OrderFeed
            orders={orders}
            wsOrderEvents={orderReceivedAndConfirmed}
            apiUrl={API_URL}
            loading={loading}
            onOrderStatusChange={refetchOrders}
          />
          <AgentActivityLog events={agentActivityEvents} />
        </div>
        <div className="space-y-4">
          <InventoryPanel apiUrl={API_URL} inventoryUpdateEvents={events.filter((e) => e.type === 'inventory_update')} />
          <PurchaseOrders
            purchaseOrders={purchaseOrders}
            wsEvents={purchaseOrderEvents}
            apiUrl={API_URL}
          />
          <CustomerAlerts
            alerts={alerts}
            wsEvents={customerAlertEvents}
            apiUrl={API_URL}
            onAck={(id) => {
              setStats((s) => ({ ...s, active_alerts_count: Math.max(0, s.active_alerts_count - 1) }));
              setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, acknowledged: true } : a)));
            }}
          />
        </div>
      </main>
    </div>
  );
}

function StatCard({ label, value, className = '' }) {
  return (
    <div className={`rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 ${className}`}>
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}
