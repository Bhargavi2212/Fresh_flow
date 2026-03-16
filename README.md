# FreshFlow

**AI-assisted order operations platform** for food distributors (seafood + produce). Ingest orders from web and SMS, parse natural-language text into structured line items, validate inventory, create supplier purchase orders when needed, store full agent traces, and stream real-time updates to an operations dashboard.

---

## What This Project Builds

- **FastAPI backend** — Order ingest (web + SMS), operational APIs, WebSocket events.
- **PostgreSQL + pgvector** — Catalog, inventory, customers, orders, purchase orders, customer alerts; semantic product search via embeddings.
- **Multi-agent orchestration** — Bedrock (Nova + Titan) with tool-calling: order parsing (RAG + Converse), inventory checks, procurement, customer intelligence.
- **React dashboard** — Live operations view: order feed, approve/reject for needs-review orders, stats, inventory, POs, alerts, agent activity.
- **Customer portal** — Customer selection, free-text order input, “the usual” / quick reorder, submission to ingest API, live progress and confirmation.

---

## Repository Structure

| Path | Description |
|------|-------------|
| `backend/` | API, services, agents, tools, DB schema and seeds, eval harness |
| `backend/api/` | Route modules: health, products, customers, inventory, suppliers, dashboard, ingest, orders, purchase_orders, customer_alerts, websocket |
| `backend/agents/` | Orchestrator, order intake (RAG + Converse), inventory, procurement, customer intel, output parsing |
| `backend/tools/` | Product search, customer lookup, inventory check, substitutions, supplier lookup, demand forecast, PO writer, order writer, SMS sender, customer intel tools |
| `backend/services/` | Database (async + sync), Bedrock, WebSocket manager, input sanitizer, Twilio, token tracker |
| `backend/db/` | `schema.sql`, seeds, `seed_all.py` |
| `backend/eval/` | `run_eval.py`, test orders for orchestrator accuracy |
| `dashboard/` | React (Vite) app: Dashboard and Customer Portal |
| `docker-compose.yml` | Local stack: Postgres (pgvector), backend, dashboard |
| Root `Dockerfile` | Backend container build |
| `dashboard/Dockerfile` | Dashboard container build |

---

## Backend Architecture

### 1. API Entrypoint and Lifecycle

`backend/main.py` creates the FastAPI app, enables CORS, and in lifespan:

- Sets the WebSocket manager’s event loop for sync broadcasts.
- Opens the asyncpg connection pool; closes it on shutdown.

Routers are mounted for: health, products, customers, inventory, suppliers, dashboard, ingest, orders, purchase_orders, customer_alerts, websocket.

### 2. API Surface

| Group | Endpoints | Notes |
|-------|-----------|--------|
| **Catalog & master data** | `GET /api/products`, `GET /api/customers`, `GET/PATCH /api/inventory`, `GET /api/suppliers` | Products support search; inventory filterable. |
| **Orders** | `GET /api/orders`, `GET /api/orders/{order_id}`, `PATCH /api/orders/{order_id}` | List: filter by status, channel, customer_id, created_after/created_before; pagination. Single order returns full detail + line items + agent_trace + customer. **PATCH** updates status (`pending`, `confirmed`, `needs_review`, `fulfilled`, `cancelled`): sets `confirmed_at` when status → `confirmed`; on `cancelled`, releases reserved inventory back to stock; rejects placeholder IDs (`pending`, `temp-*`); broadcasts `order_confirmed` on manual confirm so other dashboards update. |
| **Operations** | `GET /api/dashboard/stats`, `GET /api/purchase-orders`, `GET/PATCH /api/customer-alerts` | Dashboard stats: orders/revenue today, orders needing review, low stock, expiring soon, POs today, active alerts. Alerts: list with filters, PATCH to acknowledge. |
| **Ingestion** | `POST /api/ingest/web`, `POST /api/ingest/sms` | **Web**: JSON body (raw_message, customer_id, channel); sanitizes input, runs orchestrator with timeout; returns order_id, status, parsed_items, unresolved_mentions, etc. **SMS**: Twilio webhook (From, Body); looks up customer by phone; rate limit (e.g. 10/hour per number); returns TwiML ack and runs orchestrator in background; confirmation via SMS. |
| **System** | `GET /api/health`, `WebSocket /ws` | Health check; WebSocket for live events (agent_activity, order_confirmed, order_received, inventory_update, purchase_order_created, customer_alert). |

### 3. Services Layer

| Service | Role |
|---------|------|
| `database.py` | Async asyncpg pool; `fetch_one`, `fetch_all`, `execute`. |
| `sync_database.py` | Thread-local sync wrappers for tools (e.g. order_writer, inventory deduction). |
| `bedrock_service.py` | Titan embeddings, Nova invocations; retries and guardrails. |
| `websocket_manager.py` | Connection registry; `broadcast()` (async) and `broadcast_sync()` for tools. |
| `input_sanitizer.py` | Prompt-injection filtering; parsed-order output validation. |
| `twilio_service.py` | SMS sending with graceful failure. |
| `token_tracker.py` | Per-run token/cost accounting. |
| `product_retrieval.py` | Product search (semantic + keyword) used by RAG and tools. |

### 4. Agents and Tools

**Agents**

- **Order intake** — `order_intake.py` (facade), `order_intake_converse.py` (Bedrock Converse + tools), `order_intake_rag.py` (deterministic extraction + retrieval). Converse prompt: call `search_products` for every product; if item not in catalog, output with `sku_id` null and add to `items_needing_review` (no hallucinated SKUs).
- **Inventory** — `inventory_agent.py`: stock levels, shortages, substitutions, expiration, reorder signals.
- **Procurement** — `procurement.py`: supplier selection and purchase order creation from reorder signals.
- **Customer intelligence** — `customer_intel.py`: post-order churn/upsell/anomaly analysis; writes alerts.
- **Output parsing** — `output_parser.py`: robust JSON extraction from model output.
- **Orchestrator** — `orchestrator.py`: single code-first pipeline (see below).

**Tools (representative)**

- Product/customer: `product_search.py`, `customer_lookup.py`, `get_usual_order`, `get_customer_preferences`, `get_customer_history`.
- Inventory: `inventory_check.py`, `substitutions.py`; deduction in `order_writer.py` (FIFO).
- Procurement: `supplier_lookup.py`, `demand_forecast.py`, `po_writer.py`.
- Order persistence: `order_writer.py` — saves order + line items, deducts inventory, broadcasts `order_confirmed` and `inventory_update`.
- SMS: `sms_sender.py` (e.g. order confirmation).
- Customer intel: `customer_intel_tools.py` (alerts, analytics).

### 5. Orchestrator Flow

`run_orchestrator(raw_message, customer_id, channel, ...)` runs a deterministic pipeline:

1. **Fast path** — If message is “the usual” / “same as last time”, build items from `get_usual_order`; skip parsing.
2. **Parse** — Call RAG parser (`parse_order_rag`). If there are unresolved items, optionally run Converse and merge results. On parse error or 0 items, try free-text fallback (extract phrases, search_products, build items with similarity threshold). Validate output (sanitizer).
3. **Security / validation** — Reject disallowed content; enforce structure.
4. **Inventory** — Run inventory agent; get availability, substitutions, reorder signals.
5. **Status** — Set order status to `confirmed` or `needs_review` from confidence and availability (e.g. low confidence or out-of-stock → needs_review).
6. **Procurement** — If reorder signals exist, run procurement agent and create POs.
7. **Persist** — Build order payload; call `order_writer.save_confirmed_order`. Get real `order_id` (e.g. `ORD-2026-XXXXXX`); deduct inventory FIFO; broadcast `order_confirmed` and `inventory_update`.
8. **Confirmation** — Send customer SMS (best effort).
9. **Customer intel** — Analyze order; append to trace; create alerts if needed.
10. **Summary** — Broadcast final agent_activity; return summary (order_id, status, item counts, revenue, etc.).

WebSocket events are emitted at each stage so the dashboard can show live progress. Order ID is a placeholder until the order is saved; the frontend must not send PATCH for placeholder IDs.

---

## Data Model (Summary)

- **Core**: `suppliers`, `products` (with `embedding` vector), `customers`, `customer_preferences`, `inventory` (lots with quantity, expiration).
- **Transactions**: `orders` (order_id, customer_id, channel, raw_message, status, confidence_score, total_amount, created_at, confirmed_at, agent_trace), `order_items` (sku_id, quantity, unit_price, line_total, match_confidence, status, substituted_from, notes), `purchase_orders`, `po_items`.
- **Intelligence**: `customer_alerts` (alert_type, severity, acknowledged).
- pgvector (HNSW) used for semantic product search.

---

## Frontend

### Dashboard (`/`)

- **Stats** — From `GET /api/dashboard/stats`: orders today, revenue, orders needing review, low stock, expiring soon, POs today, active alerts. Updated incrementally from WebSocket (e.g. `order_confirmed` with numeric-safe revenue).
- **Order feed** — From `GET /api/orders` (with date range) merged with WebSocket `order_received` / `order_confirmed`. Expand row → `GET /api/orders/{id}` and show **OrderDetail** (raw message, line items with confidence, agent trace). For status **needs_review**, show **Approve** and **Reject** (calls `PATCH /api/orders/{id}` with `confirmed` or `cancelled`); placeholder IDs show “Order still processing” and no buttons. Refetch orders after status change.
- **Agent activity log** — WebSocket `agent_activity` events with timestamps and stage (orchestrator, order_intake, inventory, procurement, order_writer).
- **Inventory panel** — Low stock and inventory update events.
- **Purchase orders** — Recent POs and PO-created events.
- **Customer alerts** — List and acknowledge; count updated via WebSocket.
- Reconnect-safe event processing (reset applied-event cursor when event queue is reset).

### Customer Portal (`/order`, `/order/:customerId`)

- Customer selection; free-text order input; “The usual” and quick reorder from last order.
- Submit to `POST /api/ingest/web`; show progress via WebSocket and final confirmation (order_id, items, status).

---

## Runtime and Deployment

### Docker (local)

- **Stack**: `docker-compose.yml` — Postgres (pgvector) on 5432, backend on 8001, dashboard on 3000.
- **Backend**: Root `Dockerfile` — Python deps, Uvicorn.
- **Dashboard**: `dashboard/Dockerfile` — Vite build; build args `VITE_API_URL`, `VITE_WS_URL` (e.g. `http://localhost:8001`, `ws://localhost:8001/ws`).

Commands:

```bash
# Build (no cache)
docker compose build --no-cache

# Run
docker compose up -d

# Logs
docker compose up
```

### Environment

Copy `.env.example` to `.env`. Key variables:

- **AWS** — `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` (Bedrock: Nova, Titan).
- **Database** — `DATABASE_URL` (e.g. `postgresql://postgres:postgres@postgres:5432/freshflow` for Docker).
- **Twilio** (SMS ingest) — `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`. If unset, SMS ingest returns 503.

### Seeds and Eval

- **Seeds** — `backend/db/seeds/`; run `seed_all.py` (or equivalent) in dependency order to populate suppliers, products, inventory, customers, preferences, and sample orders.
- **Eval** — `backend/eval/run_eval.py` replays `test_orders.json` through the orchestrator and reports SKU/quantity/status accuracy and timing.

---

## Product Intent

FreshFlow is an **AI order operations copilot** for distribution:

- Turn unstructured order intake (web + SMS) into reliable, structured line items.
- Keep fulfillment and replenishment decisions explainable and traceable in `agent_trace`.
- Support human-in-the-loop: **needs_review** orders can be approved or rejected from the dashboard; reject releases inventory.
- Avoid ghost IDs and bad data: no PATCH for placeholder order IDs; RAG/Converse rules prevent hallucinated SKUs; revenue and event handling are numeric and reconnect-safe.
- Give operators real-time visibility (WebSocket) and customers clear confirmation and progress.
