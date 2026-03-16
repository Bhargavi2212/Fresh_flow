# FreshFlow Project Overview

## What this project is building
FreshFlow is an AI-assisted order operations platform for a food distributor (seafood + produce focused). It ingests customer orders from web and SMS, parses natural-language order text into structured line items, validates inventory availability, optionally creates supplier purchase orders for replenishment, stores full order traces, and streams real-time updates to an operations dashboard.

At a high level, the product combines:
- A **FastAPI backend** (order ingest, operational APIs, websocket events).
- A **PostgreSQL + pgvector** data layer (catalog, inventory, customers, orders, purchase orders, alerts).
- A **multi-agent orchestration layer** (Bedrock/Nova + tool-calling for order parsing, inventory checks, procurement, customer intelligence).
- A **React dashboard and customer portal** (live operations view + customer ordering UI).

---

## Repository structure
- `backend/`: API, services, agents, tools, DB schema/seeding, and eval harness.
- `dashboard/`: React/Vite frontend for internal dashboard and customer portal.
- `docker-compose.yml`: Local stack orchestration (Postgres, backend, dashboard).
- Root `Dockerfile`: Backend container build.

---

## Backend architecture

### 1) API entrypoint and lifecycle
`backend/main.py` creates the FastAPI app, enables CORS, initializes websocket loop tracking and database pooling in lifespan hooks, and mounts routers for health, catalog/inventory/customer APIs, ingest, orders, purchase orders, customer alerts, and websocket endpoint.

### 2) API surface
Primary API groups under `backend/api/`:
- **Catalog & master data**: `/api/products`, `/api/customers`, `/api/inventory`, `/api/suppliers`.
- **Operations**: `/api/orders`, `/api/purchase-orders`, `/api/customer-alerts`, `/api/dashboard/stats`.
- **Ingestion**: `/api/ingest/web`, `/api/ingest/sms`.
- **System**: `/api/health`, `/ws` websocket.

Notable behavior:
- SMS ingest supports phone-based customer lookup, Twilio webhook responses, and per-number rate limiting.
- Web ingest sanitizes text and runs the orchestrator pipeline with timeout protection.
- Orders and purchase-order endpoints support filtering/pagination.
- Dashboard stats aggregates multiple KPIs from orders/inventory/alerts/POs.

### 3) Services layer
`backend/services/` contains infra and safety building blocks:
- `database.py`: asyncpg pool and query helpers.
- `sync_database.py`: thread-local sync wrappers used by tool functions running off main async flow.
- `bedrock_service.py`: Titan embeddings + Nova invocation wrappers with retries/guardrail support.
- `websocket_manager.py`: connection registry and async/sync broadcasting.
- `input_sanitizer.py`: prompt-injection filtering and parsed-order output validation.
- `twilio_service.py`: SMS sending abstraction with graceful-failure semantics.
- `token_tracker.py`: per-run token/cost accounting.

### 4) Agent + tool design
The core AI behavior is in `backend/agents/` and `backend/tools/`.

#### Agents
- **Order Intake** (`order_intake.py`, `order_intake_converse.py`): uses Bedrock Converse + tools to convert raw order text into structured items.
- **Inventory Agent** (`inventory_agent.py`): checks stock, shortages, substitutions, expiration warnings, and reorder signals.
- **Procurement Agent** (`procurement.py`): selects suppliers and emits purchase orders from reorder signals.
- **Customer Intelligence Agent** (`customer_intel.py`): post-order analysis for churn risk/upsell/anomaly alerts.
- **Output parsing** (`output_parser.py`): resilient JSON extraction/validation from model output.
- **Orchestrator** (`orchestrator.py`): code-first pipeline coordinator.

#### Tooling
Representative tools:
- Product/customer context: `product_search.py`, `customer_lookup.py`.
- Inventory + substitutions: `inventory_check.py`, `substitutions.py`.
- Supplier/procurement: `supplier_lookup.py`, `demand_forecast.py`, `po_writer.py`.
- Order persistence + deduction + trace: `order_writer.py`.
- SMS customer confirmation: `sms_sender.py`.
- Customer-intel persistence and analytics helpers: `customer_intel_tools.py`.

### 5) Orchestrator flow
`run_orchestrator(...)` implements a deterministic step pipeline:
1. Parse order (with “usual order” and free-text fallbacks).
2. Validate parsed output for security/data sanity.
3. Run inventory checks and substitutions.
4. Decide status (`confirmed` vs `needs_review`) from confidence/availability logic.
5. Trigger procurement agent if reorder signals exist.
6. Persist order + line items + trace and deduct inventory FIFO.
7. Send confirmation SMS (best effort).
8. Run customer-intel analysis and append trace.
9. Emit websocket events across stages for live UI updates.

---

## Data model
Schema (`backend/db/schema.sql`) includes:
- Core entities: `suppliers`, `products` (with vector embedding), `customers`, `customer_preferences`, `inventory`.
- Transaction entities: `orders`, `order_items`, `purchase_orders`, `po_items`.
- Intelligence entities: `customer_alerts`.

The schema uses pgvector (HNSW index) for semantic product search and includes operational indices for query-heavy endpoints.

---

## Seed and evaluation workflow
- Seed scripts under `backend/db/seeds/` generate realistic suppliers, catalog, inventory, customers, preferences, and historical orders.
- `seed_all.py` runs the full seed pipeline in dependency order.
- `backend/eval/run_eval.py` replays test orders (`test_orders.json`) through orchestrator and reports SKU/quantity/status accuracy and timing.

---

## Frontend architecture

### Dashboard app
The main route (`/`) renders `Dashboard.jsx`, which:
- Loads initial stats, recent POs, and alerts via REST.
- Fetches order lists with date filtering.
- Subscribes to websocket events (`useWebSocket`) and incrementally updates stats/feeds in near real-time.
- Composes specialized panels/components for order feed/detail, inventory state, procurement view, agent activity, and customer alerts.

### Customer portal
Routes `/order` and `/order/:customerId` render `CustomerPortal.jsx`:
- Customer selection flow.
- Order input + quick reorder actions (“the usual”, reorder last).
- Submission to `/api/ingest/web` and progress/confirmation UX.
- Uses websocket connectivity status for live feedback.

---

## Runtime/deployment
- **Local orchestration**: `docker-compose.yml` runs Postgres (pgvector), backend API, and dashboard.
- **Backend container**: root `Dockerfile` installs Python deps and runs Uvicorn.
- **Frontend container**: `dashboard/Dockerfile` builds via Vite and serves static bundle.

---

## Overall product intent
This codebase implements an end-to-end “AI order operations copilot” for distribution:
- Make unstructured order intake reliable.
- Keep fulfillment and replenishment decisions explainable.
- Preserve full machine traceability in `agent_trace`.
- Close the loop with real-time operator visibility and customer-facing confirmation.
