# Phase 2: Core Agents — Order Intake + Inventory

> **Read PROJECT.md and .cursorrules first.** Then come back to this spec.
> **Prerequisite:** Phase 1 is complete. Database is populated with ~600 products (all embedded), ~75 customers, inventory, suppliers, and 6 months of order history. FastAPI is running. Bedrock connections to Nova 2 Lite and Titan Embeddings V2 are verified. The /api/products/search endpoint returns semantically ranked results.
> **Goal:** Two working Strands agents — Order Intake and Inventory — that can take a raw natural language order, parse it into structured line items matched to real SKUs, and check each item against current inventory. Plus a web endpoint to test the full flow without SMS.
> **Done means:** You POST a raw order like "need 3 cases king salmon, 20 lbs jumbo shrimp, 2 flats strawberries, and whatever white fish you got" to /api/ingest/web and get back structured JSON with each item matched to a SKU (with confidence scores), inventory availability checked, substitutions suggested for out-of-stock items, and low-stock items flagged for procurement.

---

## Context for the AI Agent

This is Phase 2 of 5. Phase 1 is complete — the database, seed data, embeddings, and read-only API all exist and work.

In this phase you are building the first two Strands agents and wiring them together using the agents-as-tools pattern. This is the core intelligence of the product. The Order Intake Agent is the hardest piece — it has to understand food distribution slang, handle mid-message corrections, resolve "the usual," and deal with vague requests like "whatever white fish you got." The Inventory Agent is simpler but critical — it checks real stock levels and suggests substitutions.

You are using Strands Agents SDK with Amazon Nova 2 Lite via BedrockModel. Every agent tool is a Python function decorated with @tool from Strands. The agents do NOT talk to each other directly — they are wired through the agents-as-tools pattern where each specialist agent is wrapped as a tool callable by a coordinator (in Phase 3, the Orchestrator will call them; in this phase, the /api/ingest/web endpoint calls them sequentially for testing).

---

## What You Are Building

### 1. Strands + Bedrock Configuration

A shared model configuration module that all agents import. It creates a BedrockModel instance pointing to Nova 2 Lite (model ID: us.amazon.nova-2-lite-v1:0) in us-east-1. The module should expose a function that creates a model with a specified extended thinking effort level, since different agents use different levels. Order Intake uses "medium" (needs reasoning for ambiguous matches). Inventory uses "low" (mostly lookups and comparisons).

The module should also expose an embedding function that calls Titan Text Embeddings V2 (model ID: amazon.titan-embed-text-v2:0) with 1024 dimensions and normalization enabled. This is the same function from Phase 1's bedrock_service but now accessible to agent tools.

### 2. Agent Tools (the @tool functions)

These are the tools that agents can call. Each is a Python function decorated with Strands' @tool decorator. The docstring on each tool is critical — Nova reads it to understand when and how to use the tool. Write clear, specific docstrings.

**search_products tool** — Takes a natural language query string and an optional top_k parameter (default 5). Embeds the query using Titan V2, runs cosine similarity against the products table's embedding column using pgvector's <=> operator, returns the top_k results as a JSON string. Each result includes: sku_id, name, aliases, category, subcategory, unit_of_measure, case_size, unit_price, shelf_life_days, storage_type, and similarity_score. The tool should also accept an optional category filter so the agent can narrow search to "Seafood > Fresh Fish" when it knows the customer wants fish.

**get_customer_history tool** — Takes a customer_id and an optional limit (default 10). Queries the orders and order_items tables to get the customer's most recent orders. Returns JSON with: list of recent orders, each with order date, items ordered (sku_id, name, quantity), and total amount. Also computes and returns: most_frequently_ordered_items (top 10 SKUs by frequency across all history — this powers "the usual"), average_order_value, typical_order_frequency (orders per week).

**get_customer_preferences tool** — Takes a customer_id. Queries the customer_preferences table. Returns JSON with all preferences: substitution rules (product A → product B), exclusions (never this product), flags (always_organic, etc.). Also returns the customer's basic profile: name, type, delivery_days.

**check_stock tool** — Takes a sku_id and a requested_quantity. Queries the inventory table for that SKU. Returns JSON with: current_total_quantity (sum across all lots), available_quantity (total minus committed-but-unshipped — for Phase 2, just use total since we don't track commitments yet), lot_details (array of lots with lot_number, quantity, received_date, expiration_date sorted by expiration ascending for FIFO), reorder_point, is_below_reorder (boolean), is_out_of_stock (boolean). If the requested quantity exceeds available, include a shortfall field showing how much is missing.

**get_expiring_items tool** — Takes an optional sku_id (if null, checks all items) and a days_threshold (default 3). Queries inventory for items with expiration_date within that many days from today. Returns JSON with items approaching expiration: sku_id, name, lot_number, quantity, expiration_date, days_until_expiry.

**find_substitutions tool** — Takes a sku_id and a customer_id. First checks customer_preferences for explicit substitution rules for this product. If found, returns those. If not, queries products in the same subcategory, excludes any products in the customer's exclusion list, and returns up to 3 alternatives sorted by similarity to the original product (use embedding similarity). Returns JSON with: has_explicit_preference (boolean), substitutions (array of sku_id, name, reason — either "customer preference" or "same category alternative"), excluded_products (any products the customer has explicitly excluded).

### 3. Order Intake Agent

A Strands Agent that parses raw natural language orders into structured line items. This is the hardest agent to get right.

**System prompt** — The system prompt defines the agent's role, rules, and output format. It should tell the agent:

You are an order parsing specialist for a seafood and produce food distributor called FreshFlow. You receive raw order messages from restaurant customers (sent via text, email, or voice) and your job is to convert them into structured line items matched to real products in the catalog.

The prompt must include these rules:

For every product mention in the message, use the search_products tool to find matching SKUs. Never guess a SKU — always search. If the customer says "the usual" or "same as last time" or "regular order," use get_customer_history to look up their most frequently ordered items and include those. If the customer says something vague like "whatever white fish you got" or "some good fish," use get_customer_preferences to check if they have a preference, then use search_products with the category to find what's available. Handle mid-message corrections: if someone says "3 cases salmon — actually make that 5," the final quantity should be 5, not 3 or 8. Convert between natural units and SKU units. If the customer says "20 lbs of salmon" and the SKU is a 10lb case, the quantity should be 2 cases. If they say "a dozen eggs" and the SKU is "Eggs, Case of 15 dozen," figure out the right quantity. Assign a confidence score (0.0 to 1.0) to each line item match. Above 0.9 means certain match. 0.7-0.9 means probable match. Below 0.7 means uncertain — flag for human review.

The output format must be a JSON object with: customer_id, order_items (array where each item has: sku_id, product_name, raw_text (what the customer actually said), quantity, unit_of_measure, unit_price, line_total, confidence, match_reasoning (one sentence explaining why this SKU was chosen)), total_amount, items_needing_review (array of items with confidence below 0.8), parsing_notes (any observations — corrections detected, vague requests resolved, etc.).

**Tools available to this agent:** search_products, get_customer_history, get_customer_preferences.

**Extended thinking:** medium effort. The agent needs to reason about ambiguous matches but doesn't need deep multi-step optimization.

**Wrap as tool:** After defining the agent, wrap it as a @tool function called parse_order that takes raw_text (string) and customer_id (string) and returns the structured JSON string. This is what the Orchestrator will call in Phase 3.

### 4. Inventory Agent

A Strands Agent that takes parsed order items and checks each against current inventory.

**System prompt** — Tell the agent:

You are an inventory management specialist for FreshFlow food distributor. You receive a list of parsed order items (already matched to SKUs with quantities) and your job is to check availability for each item against current stock levels.

Rules: For each item, use check_stock to get current levels. If the item is available in full, mark it "available." If partially available (some stock but not enough), mark it "partial" and include how much is available vs how much was requested. If out of stock (zero quantity), mark it "out_of_stock." For any item that is partial or out_of_stock, use find_substitutions to suggest alternatives based on customer preferences. Check expiration using get_expiring_items — if the only available stock expires within 2 days, note this as a warning. Flag any item where current stock after this order would fall below the reorder_point — these are procurement signals for Phase 3.

Output format: JSON object with: checked_items (array where each item includes all original fields from the order plus: availability_status, available_quantity, shortfall_quantity, expiration_warning, suggested_substitutions, triggers_reorder), procurement_signals (array of sku_ids that need reordering with current_quantity and reorder_point), summary (counts of available, partial, out_of_stock items).

**Tools available:** check_stock, get_expiring_items, find_substitutions.

**Extended thinking:** low effort. This is primarily database lookups and straightforward comparisons.

**Wrap as tool:** Wrap as @tool function called check_order_inventory that takes order_items_json (string — the JSON output from Order Intake) and customer_id (string) and returns the inventory-checked JSON string.

### 5. Sequential Processing Endpoint

Build a POST endpoint at /api/ingest/web that serves as the testing interface for this phase. It accepts a JSON body with: customer_id (required), message (required — the raw order text), channel (optional, defaults to "web").

The endpoint does the following in sequence:
1. Validates the customer_id exists in the database. If not, return 404.
2. Calls the parse_order tool (Order Intake Agent) with the raw message and customer_id. This returns structured items.
3. Calls the check_order_inventory tool (Inventory Agent) with the parsed items and customer_id. This returns availability-checked items.
4. Computes overall order confidence — the minimum confidence across all items.
5. Determines order status: if overall confidence >= 0.9 and all items available, status is "confirmed." If any item has confidence < 0.8 or is out_of_stock, status is "needs_review." Otherwise status is "confirmed" (partial availability is okay if the customer is notified).
6. Writes the order to the orders table and all line items to order_items. Stores the full agent reasoning trace (both agents' outputs) in the agent_trace jsonb column.
7. Returns the complete result: order_id, status, parsed_items with inventory status, procurement_signals, customer_insights (empty for now — Phase 4), total_amount, confidence_score.

This endpoint does NOT send SMS (Phase 3) or generate purchase orders (Phase 3) or analyze customer patterns (Phase 4). It just parses, checks inventory, and saves.

### 6. Order History Endpoints

Now that orders can be created, add write-aware endpoints:

**GET /api/orders** — List orders with filters: status (pending, confirmed, needs_review, fulfilled), channel, customer_id, date range (created_after, created_before). Paginated. Sorted by created_at descending (newest first).

**GET /api/orders/{order_id}** — Single order with all line items, agent_trace, and customer details joined in.

**PATCH /api/orders/{order_id}** — Update order status (for human review workflow — a reviewer can change needs_review to confirmed or cancelled). Only status field is updatable.

---

## Test Scenarios

These are the orders you should test against to verify both agents work correctly. Run each through POST /api/ingest/web.

**Test 1 — Simple order:** customer_id: any active customer. message: "Need 3 cases king salmon and 5 lbs jumbo shrimp for tomorrow." Expected: Two line items. King salmon matched with high confidence. Jumbo shrimp matched, quantity converted from lbs to appropriate case/unit. Both available in inventory.

**Test 2 — Correction mid-message:** message: "Hey need 2 cases halibut, 10 lbs cod, dozen oysters — actually make the halibut 3 cases." Expected: Three items. Halibut quantity is 3 (not 2). Cod and oysters parsed correctly.

**Test 3 — The usual:** Use a customer with 6 months of history. message: "the usual plus extra shrimp." Expected: Agent looks up customer's most frequent items, includes them all, adds extra shrimp (quantity inferred from their typical shrimp order, perhaps doubled).

**Test 4 — Vague request:** message: "need whatever white fish you got that's fresh, 2 flats strawberries, and some butter." Expected: White fish resolved to a specific SKU based on customer preferences or best available (halibut, cod, or sole). Strawberries and butter matched. White fish item may have lower confidence.

**Test 5 — Out of stock item:** Use an item that was seeded with zero inventory. Include it in an order. Expected: Inventory Agent marks it out_of_stock, suggests substitutions based on customer preferences.

**Test 6 — Low stock triggering procurement signal:** Order a quantity that would bring a product below its reorder_point. Expected: Item marked available (there's enough for this order) but procurement_signals includes this SKU.

**Test 7 — Formal email style:** message: "Hi team,\n\nPlease prepare the following for Wednesday delivery:\n- Atlantic salmon fillets: 5 cases\n- Jumbo shrimp (16/20 count): 30 lbs\n- Roma tomatoes: 2 flats\n- Heavy cream: 6 quarts\n- Fresh basil: 3 bunches\n\nThank you,\nChef Marco." Expected: Five items parsed correctly despite the email formatting, signature stripped.

---

## Non-Negotiable Rules

1. All agents use Strands Agent class with BedrockModel pointing to Nova 2 Lite. No other models.
2. Every tool function must have a detailed docstring — Nova reads this to decide when to use the tool.
3. Tools return JSON strings, not Python objects. Strands tools must return strings.
4. The search_products tool must use the Titan V2 embedding + pgvector similarity search from Phase 1 — not keyword matching, not LIKE queries.
5. parse_order must always call search_products for every product mention. It must never hallucinate a SKU.
6. Confidence scores must be meaningful: 0.95+ for exact matches ("king salmon" → King Salmon Fillet), 0.7-0.9 for reasonable inferences, below 0.7 for guesses.
7. "The usual" must actually look up history, not make something up.
8. Mid-message corrections must override, not accumulate (if they say "3 then actually 5," the answer is 5).
9. The full agent trace (both agents' reasoning) must be saved in the orders table agent_trace column.
10. Order status logic: confidence >= 0.9 AND all available → confirmed. Anything else → needs_review.

---

## What NOT to Build in This Phase

- No Orchestrator agent (Phase 3 — for now the endpoint calls agents sequentially)
- No Procurement Agent (Phase 3)
- No Customer Intelligence Agent (Phase 4)
- No Twilio SMS integration (Phase 3)
- No SMS sending or receiving
- No purchase order creation
- No customer alert creation
- No React dashboard (Phase 4)
- No WebSocket events
- No background task queue — process synchronously for now

---

## Acceptance Criteria

- [ ] Strands Agents SDK installed and importable
- [ ] BedrockModel connects to Nova 2 Lite successfully
- [ ] search_products tool returns semantically ranked results for "king salmon," "jumbos," "white fish," "berries"
- [ ] get_customer_history tool returns correct order history with most_frequently_ordered_items
- [ ] get_customer_preferences tool returns substitution rules and exclusions
- [ ] check_stock tool returns correct quantities, lot details, and reorder flags
- [ ] find_substitutions tool respects customer exclusions and returns same-category alternatives
- [ ] Order Intake Agent parses a simple 2-item order with correct SKU matches and quantities
- [ ] Order Intake Agent handles "the usual" by looking up customer history
- [ ] Order Intake Agent handles mid-message corrections ("actually make that 5")
- [ ] Order Intake Agent handles vague requests ("whatever white fish") using preferences and search
- [ ] Order Intake Agent handles unit conversion (20 lbs → 2 cases of 10lb)
- [ ] Order Intake Agent assigns meaningful confidence scores (high for exact, lower for vague)
- [ ] Order Intake Agent parses email-formatted orders (line items with dashes, signature text)
- [ ] Inventory Agent correctly identifies available, partial, and out_of_stock items
- [ ] Inventory Agent suggests substitutions for out_of_stock items
- [ ] Inventory Agent flags items that would go below reorder_point as procurement signals
- [ ] Inventory Agent notes expiration warnings for stock expiring within 2 days
- [ ] POST /api/ingest/web accepts a raw order and returns structured, inventory-checked result
- [ ] Orders are written to the database with correct status (confirmed vs needs_review)
- [ ] agent_trace column contains the full reasoning from both agents
- [ ] GET /api/orders returns the newly created orders
- [ ] GET /api/orders/{id} returns full detail with line items and agent trace
- [ ] PATCH /api/orders/{id} can update status from needs_review to confirmed
- [ ] All 7 test scenarios pass with expected behavior
- [ ] End-to-end processing time for a typical 4-item order is under 30 seconds

---

## How to Give This to Cursor

Save this file as `docs/PHASE_2_SPEC.md`.

Open Cursor agent chat and type:

> Read docs/PHASE_2_SPEC.md, PROJECT.md, and .cursorrules. This is Phase 2 of FreshFlow AI. Phase 1 is complete — the database, seed data, embeddings, and read-only API all work. In this phase you are building the first two Strands agents (Order Intake and Inventory) with their tools, wired sequentially through a web endpoint. Do NOT start building yet. First, create a detailed implementation plan: list every file you will create or modify, what each contains, the order you will work in, and dependencies. Present the full plan and wait for my approval before writing any code.

---

## What Comes Next

Once all acceptance criteria pass, proceed to **Phase 3: Orchestrator + Procurement + SMS**. That phase will:
- Build the Orchestrator Agent that coordinates all specialists using agents-as-tools
- Build the Procurement Agent that generates purchase orders from inventory signals
- Wire Twilio SMS integration (inbound webhook + outbound confirmation)
- Add the POST /api/ingest/sms Twilio webhook endpoint
- Add purchase order creation and storage
- By end of Phase 3, you can text a phone number, the full agent pipeline runs, and you get a confirmation SMS back
