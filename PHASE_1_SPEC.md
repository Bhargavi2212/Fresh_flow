# Phase 1: Data Foundation + API Scaffold + Embeddings Pipeline

> **Read PROJECT.md and .cursorrules first.** Then come back to this spec.
> **Prerequisite:** Nothing. This is Phase 1. Starting from scratch.
> **Goal:** A running PostgreSQL database with pgvector, populated with realistic food distribution data (products, customers, inventory, suppliers, 6 months of order history). A FastAPI backend that connects to the database and serves basic REST endpoints. The entire product catalog embedded with Amazon Titan Text Embeddings V2 and stored as vectors in pgvector. A semantic search tool that can find "king salmon" when someone types "chinook" or "spring salmon."
> **Done means:** `docker compose up` starts PostgreSQL and FastAPI. The database has ~600 products, ~75 customers, inventory for all products, ~15 suppliers, and 6 months of historical orders. You can call `GET /api/products/search?q=white+fish` and get back semantically ranked results. You can call `GET /api/health` and see all systems green. Bedrock connection to Nova 2 Lite and Titan Embeddings V2 is verified and working.

---

## Context for the AI Agent

This is Phase 1 of 5 for FreshFlow AI, a multi-agent operations platform for food distributors. Nothing exists yet — you are starting from scratch.

FreshFlow uses Amazon Nova 2 Lite (via Bedrock) for AI agents and Amazon Titan Text Embeddings V2 (via Bedrock) for semantic product search. The agent framework is Strands Agents SDK. The database is PostgreSQL with pgvector for vector similarity search.

In this phase you are NOT building any agents, no SMS integration, no dashboard, no order processing. You are building the data foundation that every agent will depend on in Phase 2 and beyond. If the data is bad, everything else breaks.

---

## What You Are Building

### 1. Docker Environment

A Docker Compose setup that starts two services: PostgreSQL 16 with the pgvector extension enabled, and the FastAPI backend. The backend depends on the database being healthy before it starts.

Environment variables needed in `.env`: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION (us-east-1), DATABASE_URL (postgres connection string), TWILIO_ACCOUNT_SID (placeholder for Phase 3), TWILIO_AUTH_TOKEN (placeholder), TWILIO_PHONE_NUMBER (placeholder).

The Dockerfile for the backend should use Python 3.11 slim, install requirements, and run uvicorn on port 8000.

### 2. Database Schema

Create all tables in a single `schema.sql` file that runs on container startup. The tables and their purposes:

**products** — The product catalog. Every item the distributor sells. Fields: sku_id (primary key, varchar like "SEA-SAL-001"), name (varchar, the full product name like "King Salmon Fillet, 10lb Case"), aliases (text array — critical field, stores alternate names like ["king salmon", "chinook", "spring salmon"]), category (varchar like "Seafood"), subcategory (varchar like "Fresh Fish"), unit_of_measure (varchar — "case", "lb", "each", "flat", "dozen"), case_size (decimal — how many units per case, e.g. 10 for a 10lb case), unit_price (decimal — sell price to customer), cost_price (decimal — what distributor pays), shelf_life_days (integer), storage_type (varchar — "frozen", "refrigerated", "ambient"), supplier_id (varchar, foreign key to suppliers), status (varchar, default "active"), embedding (vector(1024) — for Titan V2 embeddings). Index on category, subcategory, status. Vector index on embedding using ivfflat or hnsw.

**customers** — Restaurant and business accounts. Fields: customer_id (primary key, varchar like "CUST-012"), name (varchar like "Bella Vista Restaurant"), type (varchar — "fine_dining", "casual", "fast_casual", "institutional", "grocery"), phone (varchar — used to identify SMS senders), email (varchar), delivery_days (text array like ["Mon", "Wed", "Fri"]), payment_terms (varchar — "NET15", "NET30", "COD"), credit_limit (decimal), avg_order_value (decimal), account_health (varchar — "active", "at_risk", "churning"), days_since_last_order (integer), created_at (timestamp). Index on phone (unique — this is how we resolve customers from SMS), email.

**customer_preferences** — Substitution rules and preferences per customer. Fields: id (serial primary key), customer_id (foreign key), preference_type (varchar — "substitution", "exclusion", "preference", "always_organic"), description (text — human readable like "if no halibut, substitute cod, never tilapia"), product_sku (varchar — the original product), substitute_sku (varchar — the acceptable substitute). Index on customer_id.

**inventory** — Current stock levels per product. Fields: id (serial primary key), sku_id (foreign key to products), quantity (decimal), reorder_point (decimal), reorder_quantity (decimal), lot_number (varchar), received_date (date), expiration_date (date), warehouse_zone (varchar — "frozen", "refrigerated", "ambient"), updated_at (timestamp). Index on sku_id, warehouse_zone. Some products should have multiple lot entries with different expiration dates (for FIFO logic).

**suppliers** — Companies the distributor buys from. Fields: supplier_id (primary key, varchar like "SUP-001"), name (varchar like "Pacific Seafood"), lead_time_days (integer — how many days from order to delivery), min_order_value (decimal), reliability_score (decimal 0.00-1.00), phone (varchar), email (varchar).

**supplier_products** — Which supplier sells which products at what price. Fields: id (serial primary key), supplier_id (foreign key), sku_id (foreign key), supplier_price (decimal — may differ from product cost_price), min_order_qty (decimal), available (boolean). Multiple suppliers can carry the same product at different prices. Index on supplier_id, sku_id.

**orders** — Historical customer orders (seed with 6 months). Fields: order_id (primary key, varchar like "ORD-2025-001234"), customer_id (foreign key), channel (varchar — "sms", "email", "phone", "web"), raw_message (text — original unprocessed text, null for historical seed data), status (varchar — "pending", "confirmed", "needs_review", "fulfilled", "cancelled"), confidence_score (decimal 0.00-1.00, null for historical), total_amount (decimal), created_at (timestamp), confirmed_at (timestamp), agent_trace (jsonb — null for historical, will store agent reasoning in Phase 2). Index on customer_id, status, created_at.

**order_items** — Line items per order. Fields: id (serial primary key), order_id (foreign key), sku_id (foreign key), raw_text (varchar — what the customer actually said, null for historical), quantity (decimal), unit_price (decimal), line_total (decimal), match_confidence (decimal 0.00-1.00, null for historical), status (varchar — "available", "partial", "out_of_stock", "substituted"), substituted_from (varchar — original SKU if this was a substitution, usually null), notes (text). Index on order_id.

**purchase_orders** — Outbound POs to suppliers (mostly empty in Phase 1, agents create these in Phase 3). Fields: po_id (primary key, varchar like "PO-2026-000001"), supplier_id (foreign key), status (varchar — "draft", "sent", "confirmed", "received"), total_amount (decimal), triggered_by (varchar — order_id that triggered this), created_at (timestamp).

**po_items** — Line items per purchase order. Fields: id (serial primary key), po_id (foreign key), sku_id (foreign key), quantity (decimal), unit_price (decimal), line_total (decimal).

**customer_alerts** — Intelligence alerts (agents create these in Phase 4). Fields: id (serial primary key), customer_id (foreign key), alert_type (varchar — "churn_risk", "upsell", "anomaly", "milestone"), description (text), severity (varchar — "low", "medium", "high"), acknowledged (boolean default false), created_at (timestamp).

Enable pgvector extension: `CREATE EXTENSION IF NOT EXISTS vector;`

### 3. Seed Data Scripts

Create a `backend/db/seeds/` directory with Python scripts that generate realistic synthetic data. Each script should be runnable independently and idempotent (drop and recreate if data exists).

**seed_products.py** — Generate ~600 products across these categories:
- Seafood > Fresh Fish (~80 items): salmon varieties, halibut, cod, sole, branzino, snapper, swordfish, tuna, mahi mahi, etc. Each with 2-5 aliases. Case sizes of 5-20 lbs.
- Seafood > Shellfish (~50 items): shrimp (various sizes: 16/20, 21/25, 26/30), lobster, crab, scallops, oysters, clams, mussels. Aliases like "jumbos" for jumbo shrimp.
- Seafood > Frozen (~40 items): frozen versions of popular fish. Longer shelf life (180+ days).
- Produce > Fruits (~80 items): strawberries (sold by flat), blueberries, raspberries, lemons, limes, avocados, mangoes, etc. Unit of measure is "flat", "case", "lb".
- Produce > Vegetables (~80 items): Roma tomatoes, heirloom tomatoes, mixed greens, arugula, spinach, peppers, onions, mushrooms, herbs (basil, cilantro, parsley by the bunch).
- Dairy (~60 items): heavy cream, butter, various cheeses, eggs (by dozen and case), milk, yogurt.
- Dry Goods (~80 items): olive oil, vinegars, flour, sugar, pasta, rice, canned tomatoes, spices.
- Paper & Supplies (~50 items): to-go containers, napkins, gloves, plastic wrap, foil.
- Beverages (~80 items): sparkling water, juices, sodas by case.

Pricing should be realistic: fresh salmon $60-90/case, shrimp $40-80 depending on size, strawberry flats $18-25, dairy products $3-15, dry goods $5-40.

Aliases are CRITICAL. Every product must have at least 2 aliases. Fish should have common name, scientific-adjacent name, and any slang. "King salmon" = ["chinook", "chinook salmon", "spring salmon", "king"]. "Jumbo shrimp 16/20" = ["jumbos", "jumbo shrimp", "16/20 shrimp", "large shrimp"].

**seed_suppliers.py** — Generate 15 suppliers. Mix of: 3-4 seafood suppliers (Pacific Seafood, Boston Fish Market, Ocean Pride, etc.), 3-4 produce suppliers (Valley Fresh Farms, Sunrise Produce, etc.), 2-3 dairy suppliers, 2-3 dry goods suppliers, 1-2 paper/supply companies. Each with realistic lead times (fresh seafood: 1-2 days, produce: 1-2 days, frozen: 3-5 days, dry goods: 5-7 days). Reliability scores between 0.75 and 0.98.

**seed_supplier_products.py** — Link products to suppliers. Most products available from 2-3 suppliers at different prices. The cheapest supplier should have the longest lead time or highest minimum order to create interesting procurement tradeoffs.

**seed_customers.py** — Generate 75 customer accounts:
- ~20 fine dining restaurants (high avg order value $500-1500, order 3x/week, specific preferences)
- ~25 casual restaurants (avg $200-600, order 2-3x/week)
- ~10 fast casual / pizza / food trucks (avg $100-300, order 2x/week)
- ~10 institutional (hospitals, schools — avg $800-2000, order 2-3x/week, bulk items)
- ~10 grocery/specialty shops (avg $300-800, order 1-2x/week)
Each with unique phone number (format: +1212555XXXX), realistic delivery days, payment terms, and 5-10 account with "at_risk" or "churning" health status.

**seed_customer_preferences.py** — Generate 2-5 preferences per customer. Substitution rules like "if no halibut, substitute with cod" or "never substitute farmed salmon." Some customers marked "always_organic" for produce. Some with exclusions like "no shellfish" (allergy).

**seed_inventory.py** — Generate inventory for all ~600 products. Most products should be well-stocked (quantity > 2x typical daily demand). But intentionally make 30-40 products low (quantity near or below reorder_point) and 10-15 products out of stock (quantity = 0). Some fresh items should have expiration dates within 2-3 days to test FIFO. Some frozen items with lots received months ago. This creates realistic scenarios for the agents in Phase 2.

**seed_orders.py** — Generate 6 months of historical order data (roughly October 2025 through March 2026). Each customer should have orders matching their type and frequency. A fine dining restaurant ordering 3x/week for 26 weeks = ~78 orders. Total across all customers should be roughly 8,000-12,000 historical orders. Each order has 4-12 line items typical of the customer type (seafood-heavy for fine dining, bulk staples for institutional). Order amounts should be consistent with the customer's avg_order_value with realistic variance. Some customers should show a declining pattern in the last 4-6 weeks (these are the "at_risk" ones).

**seed_all.py** — Master script that runs all seed scripts in the correct order: suppliers → products → supplier_products → customers → customer_preferences → inventory → orders. Should be callable as `python -m backend.db.seeds.seed_all`.

### 4. Embedding Pipeline

**embed_catalog.py** — After products are seeded, this script embeds every product using Amazon Titan Text Embeddings V2. For each product, concatenate: "{name} {' '.join(aliases)} {category} {subcategory} {unit_of_measure}". Call Bedrock's invoke_model with model ID "amazon.titan-embed-text-v2:0", dimensions 1024, normalize true. Store the resulting vector in the product's embedding column. This script should be idempotent — skip products that already have embeddings unless a --force flag is passed. Log progress (e.g., "Embedded 100/600 products...").

### 5. FastAPI Backend

**main.py** — FastAPI application entry point. CORS middleware allowing all origins (for development). Include routers from the api directory. Database connection pool on startup, cleanup on shutdown. WebSocket endpoint at /ws for real-time dashboard updates (just the skeleton — actual events come in Phase 4).

**config.py** — Load all environment variables. Expose as a Settings pydantic model. AWS credentials, database URL, Twilio config (placeholders), app settings.

**services/bedrock_service.py** — Wrapper around boto3 bedrock-runtime client. Two functions: one that calls Titan Embeddings V2 to embed a text string and returns a vector, one that calls Nova 2 Lite with a prompt and returns the response text. Both should handle errors gracefully with retries. This service will be used by the embedding pipeline now and by agents in Phase 2.

**services/database.py** — Async database connection using asyncpg or SQLAlchemy async. Connection pool. Helper functions for common queries.

### 6. API Endpoints (Phase 1 — Read Only)

All endpoints return JSON. All are GET requests in Phase 1 (write operations come in Phase 2 when agents create orders).

**GET /api/health** — Returns status of database connection and Bedrock connection. Should actually test both connections, not just return 200.

**GET /api/products** — List products with optional filters: category, subcategory, storage_type, status. Paginated (limit/offset). Returns product fields WITHOUT the embedding vector (too large).

**GET /api/products/search?q={query}** — THE KEY ENDPOINT. Takes a natural language query string, embeds it using Titan V2, runs cosine similarity search against pgvector, returns top 10 products ranked by similarity score. Each result includes the similarity score (0-1). This is the endpoint that proves the embedding pipeline works.

**GET /api/products/{sku_id}** — Single product detail with full info including supplier and current inventory level.

**GET /api/customers** — List all customers with optional filters: type, account_health. Paginated.

**GET /api/customers/{customer_id}** — Single customer with their preferences, recent orders (last 10), and computed stats (total orders, avg value, last order date).

**GET /api/inventory** — Current inventory levels. Filterable by warehouse_zone, low_stock (boolean — quantity < reorder_point), expiring_soon (boolean — expiration_date within 3 days).

**GET /api/inventory/{sku_id}** — Inventory detail for a specific product including all lots with expiration dates.

**GET /api/suppliers** — List all suppliers.

**GET /api/dashboard/stats** — Aggregated stats for the dashboard: total products, total customers, total orders (last 30 days), low stock count, expiring soon count, at-risk customer count. Single endpoint, computed from the database.

---

## Dependencies

Python packages (put in requirements.txt):
- fastapi
- uvicorn[standard]
- asyncpg
- sqlalchemy[asyncio]
- pgvector
- boto3
- pydantic
- pydantic-settings
- python-dotenv
- twilio (install now, use in Phase 3)
- strands-agents (install now, use in Phase 2)
- strands-agents-tools (install now, use in Phase 2)

---

## Non-Negotiable Rules

1. Every product MUST have at least 2 aliases. This is what makes semantic search useful.
2. Product aliases must include common slang and abbreviations that restaurant workers actually use.
3. Seed data must be realistic — pricing, quantities, shelf lives should match real food distribution.
4. The embedding pipeline must use Titan Text Embeddings V2 model ID "amazon.titan-embed-text-v2:0" with 1024 dimensions.
5. The /api/products/search endpoint must use pgvector cosine similarity (the `<=>` operator), not keyword matching.
6. Inventory seed must have intentional low-stock and out-of-stock items — at least 30 low and 10 zero.
7. Historical orders must show declining patterns for at_risk customers.
8. Customer phone numbers must be unique — they're used for SMS customer resolution in Phase 3.
9. All API responses must be JSON with consistent structure (data field for results, meta for pagination).
10. Docker Compose must start everything with a single `docker compose up` command.

---

## What NOT to Build in This Phase

- No Strands agents or agent logic (Phase 2)
- No Twilio SMS integration (Phase 3)
- No order creation endpoints — all endpoints are read-only
- No React dashboard (Phase 4)
- No WebSocket events (Phase 4)
- No authentication or user management — this is a demo app
- No purchase order creation
- No customer alert creation
- No background task processing

---

## Acceptance Criteria

- [ ] `docker compose up` starts PostgreSQL and FastAPI without errors
- [ ] Database has pgvector extension enabled
- [ ] All 11 tables created with correct schemas, foreign keys, and indexes
- [ ] Products table has ~600 rows across all categories
- [ ] Every product has at least 2 entries in its aliases array
- [ ] Customers table has ~75 rows with mix of types
- [ ] Customer_preferences table has 2-5 preferences per customer
- [ ] Inventory table has stock for all products, with 30+ items below reorder_point and 10+ items at zero
- [ ] Suppliers table has ~15 suppliers
- [ ] Supplier_products links products to 2-3 suppliers each
- [ ] Orders table has ~8,000-12,000 historical orders spanning 6 months
- [ ] Order_items populated with realistic line items per order
- [ ] At_risk customers show declining order frequency in last 6 weeks of data
- [ ] Bedrock connection works — can call Titan Embeddings V2 and get a vector back
- [ ] Bedrock connection works — can call Nova 2 Lite and get a text response back
- [ ] All ~600 products have non-null embedding vectors in the database
- [ ] GET /api/health returns 200 with database and Bedrock status both green
- [ ] GET /api/products returns paginated product list
- [ ] GET /api/products/search?q=king+salmon returns King Salmon as top result
- [ ] GET /api/products/search?q=white+fish returns halibut, cod, sole, branzino (white fish varieties)
- [ ] GET /api/products/search?q=jumbos returns Jumbo Shrimp as top result
- [ ] GET /api/products/search?q=berries returns strawberries, blueberries, raspberries
- [ ] GET /api/customers returns paginated customer list filterable by type
- [ ] GET /api/customers/{id} returns customer with preferences and recent orders
- [ ] GET /api/inventory?low_stock=true returns 30+ items
- [ ] GET /api/inventory?expiring_soon=true returns items expiring within 3 days
- [ ] GET /api/dashboard/stats returns all aggregated counts correctly
- [ ] Entire seed process completes in under 5 minutes
- [ ] Embedding pipeline completes in under 10 minutes for ~600 products

---

## How to Give This to Cursor

Save this file as `docs/PHASE_1_SPEC.md` in your project root. Make sure PROJECT.md and .cursorrules are also in the root.

Open Cursor agent chat and type:

> Read docs/PHASE_1_SPEC.md, PROJECT.md, and .cursorrules. This is Phase 1 of FreshFlow AI. Nothing exists yet — you are starting from scratch. Do NOT start building yet. First, create a detailed implementation plan: list every file you will create, what each contains, the order you will work in, and dependencies between files. Present the full plan and wait for my approval before writing any code.

Review the plan. Make sure it matches this spec. Push back if Cursor adds things not in the spec or skips anything listed here. Once the plan is approved, let Cursor build.

After completion, run through every acceptance criterion.

---

## What Comes Next

Once all acceptance criteria pass, proceed to **Phase 2: Core Agents (Order Intake + Inventory)**. That phase will:
- Build the Order Intake Agent using Strands Agents SDK + Nova 2 Lite
- Build the Inventory Agent
- Create the @tool functions: search_products (uses the embeddings from Phase 1), get_customer_history, get_customer_preferences, check_stock, get_expiring_items
- Wire the agents-as-tools pattern where Order Intake output feeds into Inventory check
- Add POST /api/ingest/web endpoint for testing orders through the API
- By end of Phase 2, you can POST a raw order text and get back structured, inventory-checked line items
