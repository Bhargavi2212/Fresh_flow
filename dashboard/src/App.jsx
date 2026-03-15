import { useState, useEffect, useMemo, useRef } from 'react';
import { useWebSocket } from './hooks/useWebSocket.js';
import OrderFeed from './components/OrderFeed.jsx';
import OrderDetail from './components/OrderDetail.jsx';
import AgentActivityLog from './components/AgentActivityLog.jsx';
import InventoryPanel from './components/InventoryPanel.jsx';
import PurchaseOrders from './components/PurchaseOrders.jsx';
import CustomerAlerts from './components/CustomerAlerts.jsx';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001';

function App() {
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

  // Initial REST fetch
  useEffect(() => {
    let cancelled = false;
    async function fetchInitial() {
      try {
        const [statsRes, ordersRes, poRes, alertsRes] = await Promise.all([
          fetch(`${API_URL}/api/dashboard/stats`),
          fetch(`${API_URL}/api/orders?limit=20`),
          fetch(`${API_URL}/api/purchase-orders?limit=10`),
          fetch(`${API_URL}/api/customer-alerts?limit=10`),
        ]);
        if (cancelled) return;
        const statsData = await statsRes.json();
        if (statsData?.data) setStats((s) => ({ ...s, ...statsData.data }));
        const ordersData = await ordersRes.json();
        if (ordersData?.data) setOrders(ordersData.data);
        const poData = await poRes.json();
        if (poData?.items) setPurchaseOrders(poData.items);
        const alertsData = await alertsRes.json();
        if (alertsData?.items) setAlerts(alertsData.items);
      } catch (err) {
        console.error('Initial fetch failed', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchInitial();
    return () => { cancelled = true; };
  }, []);

  // WebSocket-driven stat card updates (only apply new events since last run)
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
  const dateTimeStr = now.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      {/* Top bar */}
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

      {/* Stat cards */}
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

      {/* Two columns */}
      <main className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-[1600px] mx-auto">
        <div className="space-y-4">
          <OrderFeed
            orders={orders}
            wsOrderEvents={orderReceivedAndConfirmed}
            apiUrl={API_URL}
            loading={loading}
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

export default App;
