# Phase 4: Customer Intelligence Agent + React Dashboard

> **Read PROJECT.md and .cursorrules first.** Then come back to this spec.
> **Prerequisite:** Phase 3 is complete. The Orchestrator Agent coordinates Order Intake, Inventory, and Procurement agents via agents-as-tools. Twilio SMS integration works — you can text an order and receive a confirmation. Purchase orders are generated automatically when stock is low. Orders are saved with full agent traces.
> **Goal:** The Customer Intelligence Agent completes the agent pipeline — analyzing every order for churn risk, upsell opportunities, and anomalies. A React dashboard provides a real-time operations view where you can watch orders flow in, agents work, inventory shift, and alerts fire. This is the demo surface.
> **Done means:** You text an order to the Twilio number. The dashboard shows the order appearing in real-time, each agent's activity logged as it processes, inventory levels updating, a purchase order card appearing if stock was low, and a customer intelligence alert firing if the order pattern is unusual. The full pipeline — five agents, one text message — visible end-to-end on a single screen.

---

## Context for the AI Agent

This is Phase 4 of 5. Phases 1-3 are complete — the database has data and embeddings, all four specialist agents work (Order Intake, Inventory, Procurement, Customer Intel is new in this phase), the Orchestrator coordinates them, Twilio SMS sends and receives, orders and purchase orders are persisted.

In this phase you are building two things: the final agent (Customer Intelligence) and the React dashboard that visualizes the entire system. The dashboard is not an afterthought — it IS the demo. Judges will watch the dashboard while someone texts an order. Every piece of information they need to be impressed must be visible on this screen.

---

## What You Are Building

### 1. Customer Intelligence Agent

A Strands Agent that analyzes each processed order for customer behavior patterns and generates actionable alerts.

**System prompt** — Tell the agent:

You are a customer intelligence analyst for FreshFlow food distributor. After every order is processed and confirmed, you analyze the customer's ordering patterns and generate insights that help the sales team retain customers and grow accounts.

Rules: Use get_customer_full_history to load the customer's complete ordering history (not just last 10 — you need the full picture for trend analysis). Compare this order against their historical patterns across four dimensions:

Frequency — Is this customer ordering more or less often than their typical cadence? If a customer who usually orders 3 times per week hasn't ordered in 10+ days, that's a churn risk. If they're ordering more frequently, that's a growth signal.

Value — Is this order's total above or below their average? A sustained decline in order value over 3-4 orders suggests the customer is shifting spend to a competitor. A significant increase may indicate they're consolidating suppliers toward you (positive) or a one-time event.

Product mix — Are they ordering their usual products? If a restaurant that always orders salmon stopped ordering it, they may have changed their menu or found another supplier for that item. If they're ordering new categories they've never ordered before, that's an expansion signal.

Comparison to peers — Use get_similar_customers to find customers of the same type (e.g., other fine dining restaurants) with similar order profiles. If those peers commonly order products this customer doesn't, that's an upsell opportunity. "Restaurants similar to yours also order X — would you like to try it?"

For each insight, generate an alert with: alert_type (one of: churn_risk, upsell, anomaly, growth_signal, milestone), description (plain English, 1-2 sentences — written for a sales rep who will act on it), severity (low, medium, high). Only generate alerts that are actionable — don't create noise. A normal order from a regular customer should generate zero alerts.

Output format: JSON with: customer_id, customer_name, analysis_summary (2-3 sentence overall health assessment), alerts (array of alert objects), metrics (order_frequency_trend: "increasing"/"stable"/"declining", value_trend: "increasing"/"stable"/"declining", last_30_day_total, peer_comparison: "above_average"/"average"/"below_average").

**Tools for this agent:**

**get_customer_full_history tool** — Takes a customer_id. Queries ALL orders for this customer (not limited to 10). Returns JSON with: total_order_count, first_order_date, orders_last_7_days, orders_last_30_days, orders_last_90_days, avg_order_value_30d, avg_order_value_90d, value_trend_direction (computed by comparing last 30d avg to previous 30d avg), most_ordered_products (top 15 by frequency with quantities), recent_orders (last 20 with date, items, total), days_since_last_order, typical_order_frequency_per_week.

**get_similar_customers tool** — Takes a customer_id. Looks up the customer's type (fine_dining, casual, etc.) and finds other customers of the same type with "active" account health. Returns JSON with: peer_count, peer_avg_order_value, peer_avg_frequency, commonly_ordered_products_by_peers (top 20 products ordered by at least 30% of peers — these are potential upsell targets), products_this_customer_doesnt_order (from the peer common list, which ones this customer has never ordered).

**create_customer_alert tool** — Takes customer_id, alert_type, description, severity. Writes to customer_alerts table. Returns the created alert.

**update_customer_health tool** — Takes customer_id and new account_health status. Updates the customers table. Also updates days_since_last_order. This keeps the customer profile current after every order.

**Extended thinking:** medium. Pattern analysis requires reasoning but not the multi-variable optimization of procurement.

**Wrap as tool:** Wrap as @tool function called analyze_customer_order that takes customer_id (string) and order_summary_json (string — condensed order info: items, total, date) and returns JSON with analysis and any generated alerts.

### 2. Wire Customer Intelligence into the Orchestrator

Update the Orchestrator Agent's system prompt to add a Step 5 after saving the order:

Step 5 — ANALYZE CUSTOMER: Call analyze_customer_order with the customer_id and a summary of the confirmed order. This generates customer intelligence alerts if any patterns are notable. This step should NOT block order confirmation — the customer already received their SMS. This is background analysis that feeds the dashboard.

Add analyze_customer_order to the Orchestrator's tools list.

Update the save_confirmed_order tool to also store customer intelligence results in the agent_trace alongside the other agents' traces.

### 3. WebSocket for Real-Time Updates

Add a WebSocket endpoint at /ws that the React dashboard connects to. When events happen during order processing, broadcast them to all connected WebSocket clients.

Events to broadcast (each as a JSON message with a type field):

**order_received** — When an order first comes in (from SMS or web). Payload: order_id (temporary, pre-processing), customer_name, channel, raw_message, timestamp.

**agent_activity** — When each agent starts and finishes work. Payload: order_id, agent_name ("order_intake", "inventory", "procurement", "customer_intel"), status ("started", "completed"), summary (brief description of what the agent did — "Parsed 4 items, 3 high confidence, 1 needs review"), duration_ms, timestamp.

**order_confirmed** — When the order is fully processed. Payload: order_id, customer_name, status, item_count, total_amount, confidence_score, timestamp.

**inventory_update** — When inventory levels change due to an order. Payload: sku_id, product_name, previous_quantity, new_quantity, is_low_stock, timestamp.

**purchase_order_created** — When the Procurement Agent generates a PO. Payload: po_id, supplier_name, item_count, total_amount, timestamp.

**customer_alert** — When the Customer Intelligence Agent fires an alert. Payload: alert_id, customer_name, alert_type, description, severity, timestamp.

To broadcast these events, create a WebSocket manager class that tracks connected clients and has a broadcast method. Import this manager into the agent tools — each tool that creates a notable event calls the broadcast method. For example, save_confirmed_order broadcasts order_confirmed and inventory_update events. create_purchase_order broadcasts purchase_order_created. create_customer_alert broadcasts customer_alert.

### 4. React Dashboard

A single-page React application using Tailwind CSS for styling. The dashboard is one screen with multiple panels arranged in a grid layout. It should feel like a real-time operations center — information updating live as orders flow through.

**Overall layout:**

Top bar — FreshFlow AI logo/name on the left, connection status indicator (WebSocket connected/disconnected) on the right, current date/time.

Below the top bar, a row of summary stat cards — same data as GET /api/dashboard/stats: Orders Today, Revenue Today, Orders Needing Review, Low Stock Items, Purchase Orders Today, Active Alerts. Each card shows the number prominently with a label below it. The "Needing Review" and "Low Stock" cards should be amber/orange colored when the count is above zero. "Active Alerts" should be red when high-severity alerts exist.

Below the stat cards, a two-column layout:

**Left column (wider, roughly 60%):**

**Order Feed panel** — A scrolling list of recent orders, newest at top. Each order shows: timestamp, customer name, channel icon (phone icon for SMS, globe for web), status badge (green "Confirmed", amber "Needs Review"), item count, total amount. Clicking an order expands it inline to show: the raw message, each parsed line item with SKU match and confidence score (color-coded: green above 0.9, amber 0.7-0.9, red below 0.7), inventory status per item, any substitutions made, and the agent trace summary. New orders should animate in (slide down from top or fade in) when they arrive via WebSocket.

**Agent Activity Log panel** — Below the order feed. A timeline-style log showing what each agent is doing in real-time. Each entry shows: timestamp, agent name with a colored dot (blue for Order Intake, green for Inventory, purple for Procurement, orange for Customer Intel, gray for Orchestrator), status (spinning indicator for "started", checkmark for "completed"), and the summary text. This panel is what makes the demo impressive — judges watch the agents work step by step.

**Right column (roughly 40%):**

**Inventory Alerts panel** — List of low-stock and expiring items. Each shows: product name, current quantity, reorder point, status (Low Stock in amber, Out of Stock in red, Expiring Soon in orange). Sorted by severity — out of stock first, then expiring, then low. Should update when inventory_update events arrive.

**Purchase Orders panel** — Recent purchase orders generated by the Procurement Agent. Each shows: PO number, supplier name, item count, total amount, status badge, timestamp. Expandable to show line items.

**Customer Intelligence panel** — Recent alerts from the Customer Intelligence Agent. Each shows: customer name, alert type with icon (warning triangle for churn_risk, arrow up for upsell, exclamation for anomaly, star for growth_signal), description text, severity badge, timestamp. High severity alerts should have a subtle red left border.

**Data loading:** On initial page load, the dashboard fetches current data from the REST API endpoints (GET /api/dashboard/stats, GET /api/orders?limit=20, GET /api/inventory?low_stock=true, GET /api/purchase-orders?limit=10, GET /api/customer-alerts?limit=10). After that, WebSocket events update the UI in real-time without re-fetching.

**API endpoint for customer alerts:**

Add GET /api/customer-alerts — list recent alerts with filters: alert_type, severity, acknowledged (boolean), customer_id. Paginated, newest first.

Add PATCH /api/customer-alerts/{id} — mark an alert as acknowledged.

### 5. Styling and Feel

The dashboard should look professional and clean. Dark navy sidebar is not needed — this is a single-page dashboard, not a multi-page app. Use a white/light gray background. Cards have subtle shadows. Status badges use consistent colors: green for good/confirmed, amber for warning/review, red for critical/out_of_stock, blue for informational. Use a monospace font for order IDs and PO numbers. Agent names in the activity log should be color-coded consistently across the entire dashboard.

The dashboard should be responsive enough to look good on a laptop screen (the demo will likely be on a laptop). Mobile responsiveness is not needed.

---

## Non-Negotiable Rules

1. The Customer Intelligence Agent must only fire alerts when patterns are genuinely notable. A normal order from a regular customer generates zero alerts. Do not create alert noise.
2. Customer Intelligence runs AFTER the order is confirmed and customer is notified. It should not delay the confirmation SMS.
3. WebSocket events must be broadcast in real-time as each agent completes — not batched at the end.
4. The dashboard must work with just the REST API (initial load) even if WebSocket is disconnected. WebSocket adds real-time updates on top.
5. Agent Activity Log must show each agent individually — not just "order processed." The step-by-step visibility is the demo value.
6. Order Feed must show the raw message AND the parsed interpretation so judges can see the NLP working.
7. Confidence scores must be visually color-coded (green/amber/red) everywhere they appear.
8. The dashboard fetches data from the FastAPI backend only — no direct database connections from the frontend.
9. All dashboard components must handle empty states gracefully (no orders yet, no alerts, no POs).
10. Use Tailwind utility classes only — no custom CSS files. No component libraries (no Material UI, no Ant Design). Keep it lightweight.

---

## What NOT to Build in This Phase

- No login or authentication on the dashboard
- No multi-page routing — single dashboard page only
- No order editing or creation from the dashboard (orders come from SMS/web API)
- No purchase order management (approve/reject/send) — display only
- No customer profile pages — alerts only
- No settings or configuration screens
- No dark mode
- No mobile responsive design
- No historical charts or time-series analytics
- No export or download features

---

## Acceptance Criteria

- [ ] Customer Intelligence Agent generates churn_risk alert for a customer with declining order frequency
- [ ] Customer Intelligence Agent generates upsell alert based on peer comparison
- [ ] Customer Intelligence Agent generates zero alerts for a normal order from a regular customer
- [ ] Customer Intelligence Agent updates customer account_health and days_since_last_order
- [ ] analyze_customer_order is wired into the Orchestrator as the final step
- [ ] Customer intelligence results are stored in agent_trace on the order
- [ ] WebSocket endpoint accepts connections at /ws
- [ ] order_received event broadcasts when an order comes in
- [ ] agent_activity events broadcast for each agent (start and complete)
- [ ] order_confirmed event broadcasts when processing finishes
- [ ] inventory_update events broadcast when stock levels change
- [ ] purchase_order_created event broadcasts when a PO is generated
- [ ] customer_alert event broadcasts when an intelligence alert fires
- [ ] Dashboard loads and displays summary stat cards with correct numbers
- [ ] Dashboard shows Order Feed with recent orders, newest first
- [ ] Clicking an order in the feed expands to show raw message, parsed items, confidence scores, inventory status
- [ ] Agent Activity Log shows step-by-step agent processing in real-time via WebSocket
- [ ] Inventory Alerts panel shows low stock and expiring items
- [ ] Purchase Orders panel shows recent POs with line items
- [ ] Customer Intelligence panel shows recent alerts with severity
- [ ] New orders animate into the Order Feed when they arrive via WebSocket
- [ ] Agent Activity Log updates live as each agent starts and completes
- [ ] Stat cards update when new data arrives via WebSocket
- [ ] Dashboard handles empty states (no data) without errors
- [ ] GET /api/customer-alerts endpoint works with filters
- [ ] PATCH /api/customer-alerts/{id} marks alerts as acknowledged
- [ ] Full demo flow visible: text order → dashboard shows order received → agents working step by step → order confirmed → PO generated → customer alert fired → all within 30 seconds

---

## How to Give This to Cursor

Save this file as `docs/PHASE_4_SPEC.md`.

Open Cursor agent chat and type:

> Read docs/PHASE_4_SPEC.md, PROJECT.md, and .cursorrules. This is Phase 4 of FreshFlow AI. Phases 1-3 are complete — database with data, four agents (Order Intake, Inventory, Procurement — Customer Intelligence is new), Orchestrator, Twilio SMS, web endpoint, all working. In this phase you are building the Customer Intelligence Agent, wiring it into the Orchestrator, adding WebSocket for real-time events, and building the React dashboard. Do NOT start building yet. First, create a detailed implementation plan: list every file you will create or modify, what each contains, the order you will work in, and dependencies. Present the full plan and wait for my approval before writing any code.

---

## What Comes Next

Once all acceptance criteria pass, proceed to **Phase 5: Demo Polish + Submission**. That phase will:
- Tune agent prompts for demo reliability (consistent results on demo scenarios)
- Create curated demo data (specific customers, specific inventory states for dramatic demo)
- Build the architecture diagram for the submission
- Record backup demo video
- Write README and submission materials
- Deploy to AWS
- Rehearse the 3-minute demo
