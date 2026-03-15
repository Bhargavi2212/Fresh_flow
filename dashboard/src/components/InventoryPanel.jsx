import { useState, useEffect, useMemo } from 'react';

/**
 * Low-stock and expiring items. Fetch with both low_stock=true and expiring_soon=true;
 * merge and dedupe by sku_id. Sort: out of stock first, then expiring, then low.
 */
export default function InventoryPanel({ apiUrl, inventoryUpdateEvents }) {
  const [lowStock, setLowStock] = useState([]);
  const [expiring, setExpiring] = useState([]);
  const [products, setProducts] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function fetchInventory() {
      try {
        const [lowRes, expRes, prodRes] = await Promise.all([
          fetch(`${apiUrl}/api/inventory?low_stock=true&limit=100`),
          fetch(`${apiUrl}/api/inventory?expiring_soon=true&limit=100`),
          fetch(`${apiUrl}/api/products?limit=100`),
        ]);
        if (cancelled) return;
        const lowData = await lowRes.json();
        const expData = await expRes.json();
        const prodData = await prodRes.json();
        setLowStock(lowData?.data ?? []);
        setExpiring(expData?.data ?? []);
        const map = {};
        (prodData?.data ?? []).forEach((p) => { map[p.sku_id] = p.name; });
        setProducts(map);
      } catch (err) {
        console.error('Inventory fetch failed', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchInventory();
    return () => { cancelled = true; };
  }, [apiUrl, inventoryUpdateEvents?.length]);

  const merged = useMemo(() => {
    const bySku = new Map();
    lowStock.forEach((r) => {
      const q = Number(r.quantity);
      const rp = Number(r.reorder_point);
      bySku.set(r.sku_id, {
        ...r,
        quantity: q,
        reorder_point: rp,
        status: q <= 0 ? 'out_of_stock' : q < rp ? 'low_stock' : 'low_stock',
        product_name: products[r.sku_id] ?? r.sku_id,
      });
    });
    expiring.forEach((r) => {
      const existing = bySku.get(r.sku_id);
      bySku.set(r.sku_id, {
        ...(existing || r),
        ...r,
        expiring_soon: true,
        product_name: products[r.sku_id] ?? r.sku_id,
        quantity: Number(r.quantity),
        reorder_point: Number(r.reorder_point),
        status: existing?.status || (Number(r.quantity) <= 0 ? 'out_of_stock' : 'expiring_soon'),
      });
    });
    const list = Array.from(bySku.values());
    list.sort((a, b) => {
      const order = { out_of_stock: 0, expiring_soon: 1, low_stock: 2 };
      const ao = a.quantity <= 0 ? 'out_of_stock' : a.expiring_soon ? 'expiring_soon' : 'low_stock';
      const bo = b.quantity <= 0 ? 'out_of_stock' : b.expiring_soon ? 'expiring_soon' : 'low_stock';
      return (order[ao] ?? 2) - (order[bo] ?? 2);
    });
    return list;
  }, [lowStock, expiring, products]);

  if (loading && merged.length === 0) {
    return (
      <section className="bg-white rounded-lg border border-gray-200 p-4">
        <h2 className="text-lg font-semibold mb-3">Inventory Alerts</h2>
        <p className="text-gray-500 text-sm">Loading…</p>
      </section>
    );
  }

  return (
    <section className="bg-white rounded-lg border border-gray-200 p-4">
      <h2 className="text-lg font-semibold mb-3">Inventory Alerts</h2>
      {merged.length === 0 ? (
        <p className="text-gray-500 text-sm">No low-stock or expiring items.</p>
      ) : (
        <div className="overflow-x-auto max-h-64 overflow-y-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-1.5 pr-2">Product</th>
                <th className="py-1.5 pr-2">Qty</th>
                <th className="py-1.5 pr-2">Reorder</th>
                <th className="py-1.5">Status</th>
              </tr>
            </thead>
            <tbody>
              {merged.map((row, i) => (
                <tr key={row.sku_id + i} className="border-b border-gray-100">
                  <td className="py-1.5 pr-2 font-medium">{row.product_name}</td>
                  <td className="py-1.5 pr-2">{row.quantity}</td>
                  <td className="py-1.5 pr-2">{row.reorder_point ?? '—'}</td>
                  <td className="py-1.5">
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        row.quantity <= 0
                          ? 'bg-red-100 text-red-800'
                          : row.expiring_soon
                            ? 'bg-orange-100 text-orange-800'
                            : 'bg-amber-100 text-amber-800'
                      }`}
                    >
                      {row.quantity <= 0 ? 'Out of Stock' : row.expiring_soon ? 'Expiring Soon' : 'Low Stock'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
