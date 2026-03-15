# Phase 3: Orchestrator + Procurement Agent + SMS Integration

> **Read PROJECT.md and .cursorrules first.** Then come back to this spec.
> **Prerequisite:** Phase 2 is complete. Order Intake Agent parses raw orders into structured items with confidence scores. Inventory Agent checks stock, suggests substitutions, and flags procurement signals. POST /api/ingest/web works end-to-end. Orders are saved to the database with agent traces.
> **Goal:** The full agent pipeline working end-to-end with real SMS. An Orchestrator Agent coordinates all specialists using agents-as-tools. A Procurement Agent generates purchase orders when inventory is low. Twilio SMS receives orders and sends confirmations. This is the hackathon demo flow.
> **Done means:** You text the Twilio phone number "need 3 cases king salmon, 20 lbs jumbo shrimp, and whatever white fish you got." Within 30 seconds you receive a confirmation SMS back with your order summary, inventory notes, and total. The dashboard API shows the order, any generated purchase orders, and the full agent trace. If shrimp was low, a purchase order was automatically generated to a supplier.

---

## Context for the AI Agent

This is Phase 3 of 5. Phases 1-2 are complete — database with data, embeddings, two working agents (Order Intake and Inventory), and a web endpoint for testing.

In this phase you are adding three major pieces: the Orchestrator Agent that ties everything together, the Procurement Agent that handles supplier-side purchasing, and Twilio SMS integration for real-world order intake. This phase completes the core product loop — message in, intelligence applied, confirmation out, purchase orders generated.

The Orchestrator uses Strands' agents-as-tools pattern. The Order Intake Agent, Inventory Agent, and Procurement Agent from previous phases (and this phase) are each wrapped as @tool functions. The Orchestrator is a Strands Agent whose tools are other agents. When Nova reasons about what to do next, it calls these agent-tools in the right sequence.

---

## What You Are Building

### 1. Procurement Agent

A Strands Agent that takes procurement signals (items flagged as low or out of stock by the Inventory Agent) and generates optimal purchase orders to suppliers.

**System prompt** — Tell the agent:

You are a procurement optimization specialist for FreshFlow food distributor. You receive a list of products that need replenishment (either out of stock or approaching reorder point) and your job is to generate the most cost-effective purchase orders to suppliers.

Rules: For each product that needs replenishment, use get_suppliers_for_product to find which suppliers carry it, at what price, with what lead time and minimum order quantity. Choose the best supplier based on: lowest price first, but if two suppliers are within 5% of each other on price, prefer the one with shorter lead time. If the shorter lead time supplier is more than 10% more expensive, still go with the cheaper one unless the item is urgently needed (out of stock, not just low). Respect minimum order quantities — if a supplier requires a minimum of 10 cases and we only need 3, either find another supplier without that minimum or round up to the minimum if the product has long shelf life and steady demand. Consolidate items per supplier — if we need salmon and halibut from the same supplier, put them on one purchase order to help meet minimum order values. For perishable items (shelf_life_days under 7), do not order more than 5 days of projected demand to avoid waste. Projected daily demand can be estimated from order history.

Output format: JSON object with: purchase_orders (array of POs, each with: supplier_id, supplier_name, items array (sku_id, product_name, quantity, unit_price, line_total), po_total, expected_delivery_date, reasoning (why this supplier was chosen)), total_procurement_cost, items_not_sourced (any items where no supplier was available or minimums couldn't be met).

**Tools for this agent:**

**get_suppliers_for_product tool** — Takes a sku_id. Queries the supplier_products table joined with suppliers. Returns JSON with: array of suppliers carrying this product, each with supplier_id, supplier_name, supplier_price, min_order_qty, lead_time_days, reliability_score, available (boolean). Sorted by price ascending.

**get_demand_forecast tool** — Takes a sku_id and a days parameter (default 7). Queries historical order_items for this SKU over the last 30 days, computes average daily demand, and returns JSON with: avg_daily_quantity, projected_demand_for_period (avg_daily × days), total_orders_last_30_days. This is a simple heuristic, not a real forecast model — but it gives the Procurement Agent data to reason about.

**create_purchase_order tool** — Takes supplier_id, items (array of sku_id + quantity), and triggered_by (the order_id that caused this). Writes to purchase_orders and po_items tables. Generates a po_id in format "PO-2026-XXXXXX." Returns the created PO as JSON.

**Extended thinking:** high effort. Procurement involves multi-variable optimization — comparing suppliers, balancing price vs lead time, consolidating orders, respecting minimums. This is where Nova's reasoning shines.

**Wrap as tool:** Wrap as @tool function called generate_purchase_orders that takes procurement_signals_json (string — the procurement_signals array from Inventory Agent output) and triggered_by_order_id (string) and returns the JSON with generated purchase orders.

### 2. Orchestrator Agent

The supervisor agent. This is the brain of the system. It receives a raw order and coordinates the full workflow by calling specialist agents as tools.

**System prompt** — Tell the agent:

You are the operations manager for FreshFlow, a seafood and produce food distributor. When an order comes in, you coordinate the full processing workflow by delegating to specialist agents.

Follow this exact workflow for every order:

Step 1 — PARSE: Call parse_order with the raw message text and customer_id. This agent will parse the natural language into structured line items matched to SKUs. Review the output — if any items have confidence below 0.7, the order needs human review.

Step 2 — CHECK INVENTORY: Call check_order_inventory with the parsed items JSON and customer_id. This agent will verify stock levels, flag shortfalls, suggest substitutions, and identify items that need reordering.

Step 3 — DECIDE STATUS: Based on the combined results, determine the order status. If all items have confidence above 0.9 AND all items are fully available, set status to "confirmed" — this order can be auto-processed. If any item has confidence below 0.8, or any critical item is out of stock with no acceptable substitution, set status to "needs_review" — a human must check this. Everything else is "confirmed" but include notes about partial availability or substitutions.

Step 4 — PROCURE IF NEEDED: If the inventory check produced any procurement_signals (items below reorder point or out of stock), call generate_purchase_orders with those signals. This ensures replenishment orders are placed proactively.

Step 5 — SAVE AND CONFIRM: Call save_confirmed_order to write the order to the database. Then call send_order_confirmation to notify the customer.

Always return a complete summary JSON with: order_id, status, customer_name, channel, item_count, total_amount, items_confirmed (count), items_needing_review (count), substitutions_made (count), purchase_orders_generated (count), confirmation_sent (boolean).

**Tools available to the Orchestrator:** parse_order (from Phase 2), check_order_inventory (from Phase 2), generate_purchase_orders (new in this phase), save_confirmed_order (new), send_order_confirmation (new).

**Extended thinking:** medium. The Orchestrator needs to reason about the workflow and make status decisions, but the heavy reasoning happens inside the specialist agents.

**Important: The Orchestrator does NOT have access to low-level tools like search_products or check_stock.** It only calls other agents. The agents-as-tools pattern means each specialist handles its own domain internally. The Orchestrator just coordinates.

### 3. Order Lifecycle Tools

**save_confirmed_order tool** — Takes the complete order data (customer_id, channel, raw_message, status, confidence_score, items array with all enrichments from both agents, agent_trace containing full reasoning from all agents). Writes to orders table and order_items table. Generates order_id in format "ORD-2026-XXXXXX." Returns the order_id and status.

**send_order_confirmation tool** — Takes order_id, customer_phone, customer_name, status, items_summary (condensed list of items with availability notes), total_amount, and any special_notes (like "shrimp was running low, secured your quantity but recommend ordering early next week"). Formats a confirmation SMS message and sends it via Twilio. The message should be concise but informative — restaurant owners read these on their phone at midnight. Keep it under 320 characters if possible (2 SMS segments). If the order needs_review, the message should say "Got your order, but we need to confirm a few items — your rep will follow up in the morning." Returns a JSON with sent (boolean), twilio_sid, message_body.

### 4. Twilio SMS Integration

**Inbound SMS (receiving orders):**

A POST endpoint at /api/ingest/sms that Twilio calls as a webhook when an SMS arrives at the FreshFlow phone number. Twilio sends form-encoded data with From (sender phone number), Body (message text), and other metadata.

The endpoint does the following:
1. Extract the sender phone number and message body from the Twilio webhook payload.
2. Look up the customer by phone number in the customers table. The phone field was indexed in Phase 1.
3. If no customer found: respond with a TwiML message saying "Hi! We don't recognize this number. Please contact your sales rep to get set up." Do not process further.
4. If customer found: immediately respond with a TwiML message saying "Got it, {customer_name}! Processing your order now..." This acknowledgment must return to Twilio within 15 seconds — do not wait for agent processing.
5. Kick off order processing asynchronously. Use Python's asyncio.create_task or a background mechanism so the Twilio webhook returns quickly. The processing calls the Orchestrator Agent with the raw message, customer_id, channel "sms", and sender phone number.
6. When the Orchestrator finishes, the send_order_confirmation tool sends the actual confirmation SMS via Twilio's REST API (not TwiML — this is a separate outbound message sent after processing completes).

**Outbound SMS (sending confirmations):**

A Twilio service module that wraps the Twilio REST client. It has a function to send an SMS given a to_phone, from_phone (the FreshFlow Twilio number), and message_body. It uses the Twilio Python SDK's messages.create method. Handle errors gracefully — if Twilio send fails, log the error but don't crash the order processing.

**Twilio Configuration:**

The Twilio account SID, auth token, and phone number come from environment variables (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER) set in .env. The README should include instructions for: creating a Twilio account, buying a phone number, and setting the webhook URL to https://{your-server}/api/ingest/sms. For local development, use ngrok to expose the local server and set the ngrok URL as the Twilio webhook.

### 5. Update the Web Ingestion Endpoint

Update POST /api/ingest/web from Phase 2 to use the Orchestrator Agent instead of calling Order Intake and Inventory sequentially. The web endpoint should now just call the Orchestrator (same as SMS does) and return the full result. This ensures both channels use the exact same processing pipeline.

### 6. Purchase Order API Endpoints

**GET /api/purchase-orders** — List all purchase orders with filters: status, supplier_id, date range. Paginated, newest first.

**GET /api/purchase-orders/{po_id}** — Single PO with all line items and the triggering order details.

### 7. Updated Dashboard Stats

Update GET /api/dashboard/stats to include: purchase_orders_today (count), purchase_orders_total_value_today, orders_auto_confirmed_today, orders_needing_review_today.

---

## Non-Negotiable Rules

1. The Orchestrator only calls agent-tools (parse_order, check_order_inventory, generate_purchase_orders, save_confirmed_order, send_order_confirmation). It does NOT have access to low-level tools like search_products or check_stock.
2. Twilio webhook must return a TwiML response within 15 seconds. Agent processing happens asynchronously after the acknowledgment is sent.
3. The confirmation SMS is sent via Twilio REST API as a separate outbound message, not as the TwiML webhook response.
4. SMS confirmation messages should be concise — under 320 characters when possible. Restaurant owners read these at midnight on their phones.
5. Purchase orders must be written to the database with a link to the triggering order_id.
6. The Procurement Agent must check at least 2 suppliers per product before choosing one. Never just pick the first supplier found.
7. The Procurement Agent must not over-order perishables — max 5 days of projected demand for items with shelf_life under 7 days.
8. Both /api/ingest/sms and /api/ingest/web must use the same Orchestrator Agent — no separate processing paths.
9. The full agent trace from all agents (Orchestrator → Order Intake → Inventory → Procurement) must be stored in the order's agent_trace column.
10. If Twilio credentials are not configured (empty env vars), the SMS endpoints should return a clear error message rather than crashing. The web endpoint should still work without Twilio.

---

## What NOT to Build in This Phase

- No Customer Intelligence Agent (Phase 4)
- No React dashboard (Phase 4)
- No WebSocket real-time events (Phase 4)
- No customer alert creation
- No email ingestion (documented in architecture, not built for hackathon)
- No voice/voicemail processing
- No WhatsApp integration
- No order editing after creation (only status updates via PATCH)
- No user authentication — still a demo app

---

## Acceptance Criteria

- [ ] Procurement Agent generates POs when given procurement signals from the Inventory Agent
- [ ] Procurement Agent compares at least 2 suppliers per product and picks the best option
- [ ] Procurement Agent consolidates multiple items per supplier into single POs
- [ ] Procurement Agent respects supplier minimum order quantities
- [ ] Procurement Agent limits perishable orders to 5 days of projected demand
- [ ] get_suppliers_for_product tool returns correct supplier options with pricing
- [ ] get_demand_forecast tool returns reasonable daily demand estimates from historical data
- [ ] create_purchase_order tool writes POs to database correctly
- [ ] Orchestrator Agent calls parse_order → check_order_inventory → generate_purchase_orders in correct sequence
- [ ] Orchestrator correctly determines "confirmed" status when all items high-confidence and available
- [ ] Orchestrator correctly determines "needs_review" status when confidence is low or items unavailable
- [ ] Orchestrator triggers Procurement Agent only when there are procurement signals
- [ ] Orchestrator skips Procurement Agent when all items are well-stocked
- [ ] save_confirmed_order writes order and items to database with full agent trace
- [ ] send_order_confirmation sends a concise, informative SMS via Twilio
- [ ] POST /api/ingest/sms receives a Twilio webhook and returns TwiML acknowledgment within 5 seconds
- [ ] POST /api/ingest/sms identifies the customer from the sender phone number
- [ ] POST /api/ingest/sms returns "don't recognize this number" for unknown phones
- [ ] After SMS processing completes, the customer receives a confirmation SMS
- [ ] POST /api/ingest/web now uses the Orchestrator Agent (same pipeline as SMS)
- [ ] GET /api/purchase-orders returns generated POs
- [ ] GET /api/purchase-orders/{id} returns PO with line items
- [ ] GET /api/dashboard/stats includes purchase order and order status counts
- [ ] End-to-end SMS flow: send text → receive ack → receive confirmation with order details
- [ ] End-to-end flow with low-stock item: order triggers PO generation, PO is in database, confirmation notes the stock situation
- [ ] End-to-end flow with out-of-stock item: substitution suggested, order flagged needs_review, confirmation says "need to confirm a few items"
- [ ] Application works normally when Twilio credentials are missing (web endpoint still functional)
- [ ] Full agent trace stored and visible via GET /api/orders/{id}

---

## How to Give This to Cursor

Save this file as `docs/PHASE_3_SPEC.md`.

Open Cursor agent chat and type:

> Read docs/PHASE_3_SPEC.md, PROJECT.md, and .cursorrules. This is Phase 3 of FreshFlow AI. Phases 1-2 are complete — the database has data and embeddings, the Order Intake and Inventory agents work, and the web endpoint processes orders. In this phase you are building the Orchestrator Agent (agents-as-tools), the Procurement Agent, and Twilio SMS integration. Do NOT start building yet. First, create a detailed implementation plan: list every file you will create or modify, what each contains, the order you will work in, and dependencies. Present the full plan and wait for my approval before writing any code.

---

## What Comes Next

Once all acceptance criteria pass, proceed to **Phase 4: Customer Intelligence + Dashboard**. That phase will:
- Build the Customer Intelligence Agent (churn detection, upsell opportunities, order anomalies)
- Wire it into the Orchestrator workflow as the final step
- Build the React + Tailwind dashboard with real-time order feed, agent activity log, inventory alerts, customer intelligence alerts, and purchase order view
- Add WebSocket support for live updates as orders process
- By end of Phase 4, you have a complete demo-ready product: text a number → watch the dashboard light up in real time
