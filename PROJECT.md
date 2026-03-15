# FreshFlow AI — PROJECT.md

## What This Is
AI-powered operations platform for food distributors. Multi-agent system using Amazon Nova 2 Lite + Strands Agents SDK. Orders come in via SMS/email/web → AI agents parse, check inventory, generate purchase orders, track customer patterns → confirmation sent back.

**Hackathon:** Amazon Nova (deadline March 16)
**Job pitch:** Anchr (NYC, just raised $5.8M for same problem)
**Competitors building this:** Choco ($1B+ orders/year, "Autopilot" agent), Pepper ($50M Series C, 500+ distributors), Anchr (pre-seed)

---

## Reference Repos — Study These First

### Strands Agents Multi-Agent Patterns (CRITICAL)
- **Multi-agent food order system:** `github.com/aws-samples/sample-multi-agent-collaboration-with-strands` — Burger restaurant with orchestrator + specialist agents (burger_cook, fry_cook, front_counter). Uses EventBridge + SQS + Lambda. Study the orchestration pattern.
- **Agents-as-tools example:** `github.com/strands-agents/docs/blob/main/docs/examples/python/multi_agent_example/multi_agent_example.md` — Shows how to wrap agents as @tool for orchestrator delegation. THIS IS OUR PATTERN.
- **Finance swarm agent:** `github.com/strands-agents/samples/tree/main/02-samples` → finance-assistant-swarm-agent. Multi-agent equity research with specialized agents. Study the swarm coordination.
- **Strands samples repo:** `github.com/strands-agents/samples` — Restaurant assistant, multi-agent collaboration, Nova Sonic integration examples.
- **Strands getting started course:** `github.com/aws-samples/sample-getting-started-with-strands-agents-course` — 4-course progression from basics to multi-agent to production deployment.

### Strands SDK Core
- **Python SDK:** `github.com/strands-agents/sdk-python` — Main SDK. Read the README thoroughly.
- **Tools package:** `pypi.org/project/strands-agents-tools/` — Pre-built tools (http_request, shell, file_read, memory, etc.)
- **Nova integration:** `strandsagents.com/latest/documentation/docs/user-guide/concepts/model-providers/amazon-nova/`

### Multi-Agent Architecture Blog Posts (READ THESE)
- **Collaboration patterns:** `aws.amazon.com/blogs/machine-learning/multi-agent-collaboration-patterns-with-strands-agents-and-amazon-nova/` — Agents-as-Tools, Swarms, Graphs, Workflows with code examples
- **Technical deep dive:** `aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/`
- **Strands 1.0 announcement:** `aws.amazon.com/blogs/opensource/introducing-strands-agents-1-0-production-ready-multi-agent-orchestration-made-simple/`

---

## Tech Stack

| Layer | Choice | Install |
|-------|--------|---------|
| AI Model | Amazon Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`) | Via Bedrock API |
| Agent Framework | Strands Agents SDK 1.0 | `pip install strands-agents strands-agents-tools` |
| Embeddings | Amazon Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`) | Via Bedrock API |
| API | FastAPI | `pip install fastapi uvicorn` |
| Database | PostgreSQL + pgvector | `pip install asyncpg sqlalchemy pgvector` |
| SMS | Twilio | `pip install twilio` |
| Frontend | React + Tailwind + Vite | `npm create vite@latest dashboard -- --template react` |
| Deployment | AWS (Fargate or EC2) | CDK or manual |

---

## Running in Docker

Use Docker Compose for local development. **Run all commands (Python, pip, tests, seeds, scripts) inside the backend container**, not on the host:

```bash
# Start stack
docker compose up -d

# Run commands inside backend container
docker compose exec backend python -c "import backend.main; print('OK')"
docker compose exec backend python -m backend.db.embed_catalog
docker compose exec backend pytest  # if you have tests

# Rebuild after code changes
docker compose up --build -d
```

API: http://localhost:8001 (backend port 8000 mapped to 8001).

---

## Twilio + ngrok (SMS ingest)

To receive orders via SMS and send confirmations:

1. **Twilio account:** Sign up at twilio.com, buy a phone number.
2. **Environment variables:** In `.env` (or Docker env) set:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_PHONE_NUMBER` (your Twilio number, E.164)
3. **Production:** Set your Twilio number’s webhook URL to `https://{your-server}/api/ingest/sms` (HTTP POST).
4. **Local development:** Expose the backend with ngrok, then point Twilio to the ngrok URL:
   - Run `ngrok http 8001` (or the port where the API is reachable).
   - In Twilio Console → Phone Numbers → your number → Messaging: set "A message comes in" Webhook to `https://xxxx.ngrok.io/api/ingest/sms`.

If Twilio credentials are missing, `POST /api/ingest/sms` returns 503; web ingest and the rest of the app still work.

---

## Project Structure

```
freshflow/
├── PROJECT.md                    # This file
├── .cursorrules                  # Cursor AI rules
├── README.md                     # Hackathon submission readme
│
├── backend/
│   ├── main.py                   # FastAPI app entry point
│   ├── config.py                 # AWS credentials, Twilio config, DB config
│   ├── requirements.txt
│   │
│   ├── api/
│   │   ├── ingest.py             # POST /api/ingest/sms, /api/ingest/email, /api/ingest/web
│   │   ├── orders.py             # GET /api/orders, GET /api/orders/{id}
│   │   ├── inventory.py          # GET /api/inventory
│   │   ├── customers.py          # GET /api/customers
│   │   ├── purchase_orders.py    # GET /api/purchase-orders
│   │   └── dashboard.py          # GET /api/dashboard/stats (aggregated)
│   │
│   ├── agents/
│   │   ├── orchestrator.py       # Supervisor agent — delegates to specialists
│   │   ├── order_intake.py       # Parses raw text → structured line items
│   │   ├── inventory_agent.py    # Checks stock, flags conflicts, suggests substitutions
│   │   ├── procurement.py        # Generates purchase orders from demand signals
│   │   └── customer_intel.py     # Monitors patterns, flags churn, surfaces upsells
│   │
│   ├── tools/                    # @tool functions the agents call
│   │   ├── product_search.py     # Semantic search via Titan Embeddings + pgvector
│   │   ├── customer_lookup.py    # Get customer profile, preferences, history
│   │   ├── inventory_check.py    # Query current stock levels
│   │   ├── supplier_lookup.py    # Get supplier catalog, pricing, lead times
│   │   ├── order_writer.py       # Write confirmed order to DB
│   │   ├── po_writer.py          # Write purchase order to DB
│   │   └── sms_sender.py         # Send confirmation via Twilio
│   │
│   ├── db/
│   │   ├── schema.sql            # PostgreSQL schema
│   │   ├── seed_products.py      # Generate synthetic product catalog
│   │   ├── seed_customers.py     # Generate synthetic customer profiles
│   │   ├── seed_inventory.py     # Generate synthetic inventory snapshot
│   │   ├── seed_suppliers.py     # Generate synthetic supplier data
│   │   ├── seed_orders.py        # Generate 6 months of historical orders
│   │   └── embed_catalog.py      # Embed product catalog with Titan V2, store in pgvector
│   │
│   └── services/
│       ├── twilio_service.py     # Twilio SMS send/receive
│       └── bedrock_service.py    # Nova + Titan Embeddings client wrapper
│
├── dashboard/                    # React frontend
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── OrderFeed.jsx         # Real-time order stream
│   │   │   ├── AgentActivityLog.jsx  # Shows what each agent is doing
│   │   │   ├── InventoryPanel.jsx    # Stock levels with alerts
│   │   │   ├── CustomerAlerts.jsx    # Churn risk, upsell opportunities
│   │   │   ├── PurchaseOrders.jsx    # Generated POs
│   │   │   └── OrderDetail.jsx       # Single order breakdown with confidence scores
│   │   └── hooks/
│   │       └── useWebSocket.js       # Real-time updates via WebSocket
│   └── ...
│
└── demo/
    ├── sample_orders.json        # 100 sample raw orders for testing
    ├── demo_script.md            # 3-minute demo script
    └── architecture_diagram.png  # For submission
```

---

## Database Schema

```sql
-- Products (the catalog)
CREATE TABLE products (
    sku_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    aliases TEXT[],                    -- ['king salmon', 'chinook', 'spring salmon']
    category VARCHAR(50),             -- 'Seafood'
    subcategory VARCHAR(50),          -- 'Fresh Fish'
    unit_of_measure VARCHAR(20),      -- 'case', 'lb', 'each'
    case_size DECIMAL,                -- 10 (lbs per case)
    unit_price DECIMAL(10,2),         -- sell price
    cost_price DECIMAL(10,2),         -- cost from supplier
    shelf_life_days INTEGER,
    storage_type VARCHAR(20),         -- 'frozen', 'refrigerated', 'ambient'
    supplier_id VARCHAR(20),
    status VARCHAR(20) DEFAULT 'active',
    embedding VECTOR(1024)            -- Titan V2 embedding for semantic search
);

-- Customers
CREATE TABLE customers (
    customer_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(200),
    type VARCHAR(50),                 -- 'fine_dining', 'casual', 'institutional', 'grocery'
    phone VARCHAR(20),
    email VARCHAR(200),
    delivery_days TEXT[],             -- ['Mon', 'Wed', 'Fri']
    payment_terms VARCHAR(20),        -- 'NET30', 'COD'
    credit_limit DECIMAL(10,2),
    avg_order_value DECIMAL(10,2),
    account_health VARCHAR(20),       -- 'active', 'at_risk', 'churning'
    days_since_last_order INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Customer preferences
CREATE TABLE customer_preferences (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(20) REFERENCES customers(customer_id),
    preference_type VARCHAR(50),      -- 'substitution', 'exclusion', 'preference'
    description TEXT,                 -- 'if no halibut, substitute cod, never tilapia'
    product_sku VARCHAR(20),
    substitute_sku VARCHAR(20)
);

-- Inventory
CREATE TABLE inventory (
    id SERIAL PRIMARY KEY,
    sku_id VARCHAR(20) REFERENCES products(sku_id),
    quantity DECIMAL(10,2),
    reorder_point DECIMAL(10,2),
    reorder_quantity DECIMAL(10,2),
    lot_number VARCHAR(50),
    received_date DATE,
    expiration_date DATE,
    warehouse_zone VARCHAR(20),       -- 'frozen', 'refrigerated', 'ambient'
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Suppliers
CREATE TABLE suppliers (
    supplier_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(200),
    lead_time_days INTEGER,
    min_order_value DECIMAL(10,2),
    reliability_score DECIMAL(3,2),   -- 0.0 to 1.0
    phone VARCHAR(20),
    email VARCHAR(200)
);

-- Supplier product catalog (which supplier sells what at what price)
CREATE TABLE supplier_products (
    id SERIAL PRIMARY KEY,
    supplier_id VARCHAR(20) REFERENCES suppliers(supplier_id),
    sku_id VARCHAR(20) REFERENCES products(sku_id),
    supplier_price DECIMAL(10,2),
    min_order_qty DECIMAL(10,2),
    available BOOLEAN DEFAULT true
);

-- Orders (incoming customer orders)
CREATE TABLE orders (
    order_id VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(20) REFERENCES customers(customer_id),
    channel VARCHAR(20),              -- 'sms', 'email', 'web', 'voice'
    raw_message TEXT,                 -- Original unprocessed text
    status VARCHAR(20),               -- 'pending', 'confirmed', 'needs_review', 'fulfilled'
    confidence_score DECIMAL(3,2),    -- Overall confidence from Order Intake Agent
    total_amount DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW(),
    confirmed_at TIMESTAMP,
    agent_trace JSONB                 -- Full agent reasoning trace for observability
);

-- Order line items
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(20) REFERENCES orders(order_id),
    sku_id VARCHAR(20) REFERENCES products(sku_id),
    raw_text VARCHAR(200),            -- What the customer actually said
    quantity DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    line_total DECIMAL(10,2),
    match_confidence DECIMAL(3,2),    -- How confident was the SKU match
    status VARCHAR(20),               -- 'available', 'partial', 'out_of_stock', 'substituted'
    substituted_from VARCHAR(20),     -- Original SKU if this was a substitution
    notes TEXT
);

-- Purchase orders (outbound to suppliers)
CREATE TABLE purchase_orders (
    po_id VARCHAR(20) PRIMARY KEY,
    supplier_id VARCHAR(20) REFERENCES suppliers(supplier_id),
    status VARCHAR(20),               -- 'draft', 'sent', 'confirmed', 'received'
    total_amount DECIMAL(10,2),
    triggered_by VARCHAR(20),         -- order_id that triggered this PO
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE po_items (
    id SERIAL PRIMARY KEY,
    po_id VARCHAR(20) REFERENCES purchase_orders(po_id),
    sku_id VARCHAR(20) REFERENCES products(sku_id),
    quantity DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    line_total DECIMAL(10,2)
);

-- Customer intelligence alerts
CREATE TABLE customer_alerts (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(20) REFERENCES customers(customer_id),
    alert_type VARCHAR(50),           -- 'churn_risk', 'upsell', 'anomaly', 'milestone'
    description TEXT,
    severity VARCHAR(20),             -- 'low', 'medium', 'high'
    acknowledged BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## How Agents Connect — The Wiring

This is the core architecture. We use the **agents-as-tools** pattern from Strands.

### Pattern: Each specialist agent is a @tool the Orchestrator calls

```python
# backend/agents/order_intake.py
from strands import Agent, tool
from strands.models import BedrockModel
from backend.tools.product_search import search_products
from backend.tools.customer_lookup import get_customer_history, get_customer_preferences

model = BedrockModel(
    model_id="us.amazon.nova-2-lite-v1:0",
    streaming=True,
    additional_request_fields={
        "reasoningConfig": {
            "type": "enabled",
            "maxReasoningEffort": "medium"  # Medium for order parsing
        }
    }
)

order_intake_agent = Agent(
    model=model,
    system_prompt="""You are an order parsing specialist for a seafood and produce
    food distributor. You receive raw order text from restaurant customers and
    convert it to structured line items.

    RULES:
    - Match product mentions to SKUs using the search_products tool
    - Handle slang: 'king' = king salmon, 'jumbos' = jumbo shrimp
    - Handle corrections: 'actually make that 5' overrides previous quantity
    - Handle 'the usual' by checking customer order history
    - Handle vague requests ('whatever white fish') using customer preferences + inventory
    - Convert natural units to SKU units (20 lbs = 2 cases if case_size=10lb)
    - Return JSON with line_items array, each having: sku_id, name, quantity, unit, 
      unit_price, line_total, confidence (0-1), raw_text (what customer said)
    - If confidence < 0.8 on any item, flag it as needs_review
    """,
    tools=[search_products, get_customer_history, get_customer_preferences]
)

# Wrap as a tool for the orchestrator
@tool
def parse_order(raw_text: str, customer_id: str) -> str:
    """Parse a raw order text into structured line items.
    
    Args:
        raw_text: The raw order message from the customer
        customer_id: The customer's ID for looking up history/preferences
    
    Returns:
        JSON string with parsed order items and confidence scores
    """
    prompt = f"""Parse this order from customer {customer_id}:

    "{raw_text}"

    Use search_products to match each item. Check customer history for 'the usual'.
    Return structured JSON."""
    
    result = order_intake_agent(prompt)
    return str(result)
```

```python
# backend/agents/inventory_agent.py
from strands import Agent, tool
from strands.models import BedrockModel
from backend.tools.inventory_check import check_stock, get_expiring_items

model = BedrockModel(
    model_id="us.amazon.nova-2-lite-v1:0",
    streaming=True,
    additional_request_fields={
        "reasoningConfig": {
            "type": "enabled",
            "maxReasoningEffort": "low"  # Low - mostly lookups
        }
    }
)

inventory_agent = Agent(
    model=model,
    system_prompt="""You are an inventory management specialist for a food distributor.
    Given a list of order line items, check stock availability for each.
    
    RULES:
    - Check current quantity vs requested quantity
    - Factor in committed (unshipped) orders
    - Check expiration dates — use FIFO (oldest first)
    - If insufficient: check customer preferences for substitutions
    - Flag items below reorder_point for procurement
    - Return each item with status: available, partial, out_of_stock, substitution_available
    """,
    tools=[check_stock, get_expiring_items]
)

@tool
def check_order_inventory(order_items_json: str) -> str:
    """Check inventory availability for all items in a parsed order.
    
    Args:
        order_items_json: JSON string of parsed order items from Order Intake Agent
    
    Returns:
        JSON with availability status per item and procurement signals
    """
    result = inventory_agent(f"Check inventory for these items: {order_items_json}")
    return str(result)
```

```python
# backend/agents/procurement.py
from strands import Agent, tool
from strands.models import BedrockModel
from backend.tools.supplier_lookup import get_suppliers, get_supplier_pricing

model = BedrockModel(
    model_id="us.amazon.nova-2-lite-v1:0",
    streaming=True,
    additional_request_fields={
        "reasoningConfig": {
            "type": "enabled",
            "maxReasoningEffort": "high"  # High - multi-variable optimization
        }
    }
)

procurement_agent = Agent(
    model=model,
    system_prompt="""You are a procurement optimization specialist for a food distributor.
    When inventory is low or demand exceeds stock, generate optimal purchase orders.
    
    RULES:
    - Compare suppliers on: price, lead time, min order qty, reliability score
    - Don't over-order perishables (check shelf_life_days)
    - Consolidate items per supplier to meet minimum order values
    - Factor in projected demand from order patterns (not just current shortfall)
    - Return structured PO with: supplier_id, items, quantities, total, expected_delivery
    """,
    tools=[get_suppliers, get_supplier_pricing]
)

@tool
def generate_purchase_orders(inventory_gaps_json: str) -> str:
    """Generate optimal purchase orders for inventory shortfalls.
    
    Args:
        inventory_gaps_json: JSON with items that need replenishment from Inventory Agent
    
    Returns:
        JSON with purchase orders per supplier
    """
    result = procurement_agent(f"Generate purchase orders for: {inventory_gaps_json}")
    return str(result)
```

```python
# backend/agents/customer_intel.py
from strands import Agent, tool
from strands.models import BedrockModel
from backend.tools.customer_lookup import get_customer_history, get_similar_customers

model = BedrockModel(
    model_id="us.amazon.nova-2-lite-v1:0",
    streaming=True,
    additional_request_fields={
        "reasoningConfig": {
            "type": "enabled",
            "maxReasoningEffort": "medium"
        }
    }
)

customer_intel_agent = Agent(
    model=model,
    system_prompt="""You are a customer intelligence analyst for a food distributor.
    After each order, analyze the customer's patterns and generate insights.
    
    RULES:
    - Compare this order to their historical average (value, frequency, product mix)
    - Flag churn risk if: order frequency declining, value declining, missing regular items
    - Flag upsell if: similar customers order items this one doesn't
    - Flag anomaly if: order is significantly different from pattern
    - Return insights as alerts with type, description, severity
    """,
    tools=[get_customer_history, get_similar_customers]
)

@tool
def analyze_customer_order(customer_id: str, order_json: str) -> str:
    """Analyze a customer's order for patterns, churn risk, and upsell opportunities.
    
    Args:
        customer_id: The customer ID
        order_json: The confirmed order details
    
    Returns:
        JSON with customer intelligence alerts
    """
    result = customer_intel_agent(
        f"Analyze order from customer {customer_id}: {order_json}"
    )
    return str(result)
```

### The Orchestrator — Ties Everything Together

```python
# backend/agents/orchestrator.py
from strands import Agent
from strands.models import BedrockModel
from backend.agents.order_intake import parse_order
from backend.agents.inventory_agent import check_order_inventory
from backend.agents.procurement import generate_purchase_orders
from backend.agents.customer_intel import analyze_customer_order
from backend.tools.order_writer import save_order
from backend.tools.sms_sender import send_sms

model = BedrockModel(
    model_id="us.amazon.nova-2-lite-v1:0",
    streaming=True,
    additional_request_fields={
        "reasoningConfig": {
            "type": "enabled",
            "maxReasoningEffort": "medium"
        }
    }
)

orchestrator = Agent(
    model=model,
    system_prompt="""You are the operations manager for FreshFlow, a seafood and 
    produce food distributor. You coordinate order processing using specialist agents.

    WORKFLOW — follow this sequence for every incoming order:
    
    1. PARSE: Call parse_order with the raw message and customer_id to get structured items
    2. INVENTORY: Call check_order_inventory with the parsed items to verify availability
    3. DECIDE: 
       - If all items available with confidence > 0.9: auto-confirm (status: confirmed)
       - If any item has confidence < 0.8 or is out of stock: flag for review (status: needs_review)
    4. PROCURE: If inventory agent flagged any items as low/out, call generate_purchase_orders
    5. INSIGHTS: Call analyze_customer_order to log customer patterns
    6. CONFIRM: Call save_order to persist, then send_sms with confirmation to customer
    
    Always return a summary JSON with: order_id, status, items, total, alerts, procurement_triggered
    """,
    tools=[
        parse_order,
        check_order_inventory, 
        generate_purchase_orders,
        analyze_customer_order,
        save_order,
        send_sms
    ]
)

async def process_order(raw_message: str, customer_id: str, channel: str, sender: str):
    """Main entry point — called by the ingestion API"""
    prompt = f"""Process this incoming order:
    
    Customer: {customer_id}
    Channel: {channel}
    Message: "{raw_message}"
    Reply to: {sender}
    
    Follow the workflow: parse → check inventory → decide → procure if needed → analyze → confirm"""
    
    result = orchestrator(prompt)
    return result
```

### The Ingestion API — Where Orders Enter

```python
# backend/api/ingest.py
from fastapi import APIRouter, Request
from twilio.twiml.messaging_response import MessagingResponse
from backend.agents.orchestrator import process_order
from backend.services.customer_resolver import resolve_customer_by_phone

router = APIRouter()

@router.post("/api/ingest/sms")
async def ingest_sms(request: Request):
    """Twilio webhook — receives incoming SMS orders"""
    form = await request.form()
    sender_phone = form.get("From")
    message_body = form.get("Body")
    
    # Resolve customer from phone number
    customer = await resolve_customer_by_phone(sender_phone)
    if not customer:
        # Unknown sender — log and skip
        resp = MessagingResponse()
        resp.message("Hi! We don't recognize this number. Please contact your sales rep.")
        return str(resp)
    
    # Process order asynchronously (don't block Twilio webhook)
    import asyncio
    asyncio.create_task(
        process_order(
            raw_message=message_body,
            customer_id=customer.customer_id,
            channel="sms",
            sender=sender_phone
        )
    )
    
    # Immediate acknowledgment
    resp = MessagingResponse()
    resp.message(f"Got it, {customer.name}! Processing your order now...")
    return str(resp)

@router.post("/api/ingest/web")
async def ingest_web(payload: dict):
    """Web form submission — for demo and email simulation"""
    result = await process_order(
        raw_message=payload["message"],
        customer_id=payload["customer_id"],
        channel=payload.get("channel", "web"),
        sender=payload.get("sender", "web")
    )
    return {"status": "processing", "result": result}
```

---

## Embedding Pipeline (Product Catalog Search)

```python
# backend/db/embed_catalog.py
import boto3, json
from pgvector.sqlalchemy import Vector

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

def embed_text(text: str, dimensions: int = 1024) -> list:
    """Embed text using Amazon Titan Text Embeddings V2"""
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({
            "inputText": text,
            "dimensions": dimensions,
            "normalize": True
        })
    )
    return json.loads(response['body'].read())['embedding']

def embed_product_catalog():
    """Embed all products and store vectors in pgvector"""
    products = db.query("SELECT * FROM products")
    for product in products:
        # Combine name + aliases + category for rich embedding
        embed_text_input = f"{product.name} {' '.join(product.aliases)} {product.category} {product.subcategory}"
        vector = embed_text(embed_text_input)
        db.execute(
            "UPDATE products SET embedding = %s WHERE sku_id = %s",
            [vector, product.sku_id]
        )

# The tool the Order Intake Agent uses:
# backend/tools/product_search.py
@tool
def search_products(query: str, top_k: int = 5) -> str:
    """Semantic search against product catalog using embeddings.
    
    Args:
        query: Natural language product description (e.g., 'king salmon' or 'white fish')
        top_k: Number of results to return
    
    Returns:
        JSON array of matching products with similarity scores
    """
    query_vector = embed_text(query)
    results = db.execute("""
        SELECT sku_id, name, aliases, category, unit_of_measure, case_size, 
               unit_price, shelf_life_days, storage_type,
               1 - (embedding <=> %s::vector) as similarity
        FROM products
        WHERE status = 'active'
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, [query_vector, query_vector, top_k])
    return json.dumps([dict(r) for r in results])
```

---

## Sample Orders (for testing and demo)

```json
[
  {
    "id": "sample_001",
    "complexity": "simple",
    "channel": "sms",
    "customer_id": "CUST-012",
    "raw_text": "Need 3 cases king salmon and 5 lbs jumbo shrimp for tomorrow"
  },
  {
    "id": "sample_002", 
    "complexity": "corrections",
    "channel": "sms",
    "customer_id": "CUST-008",
    "raw_text": "Hey need 2 cases halibut, 10 lbs cod, dozen oysters — actually make the halibut 3 cases. Thx"
  },
  {
    "id": "sample_003",
    "complexity": "the_usual",
    "channel": "sms",
    "customer_id": "CUST-003",
    "raw_text": "the usual plus extra shrimp"
  },
  {
    "id": "sample_004",
    "complexity": "vague",
    "channel": "sms", 
    "customer_id": "CUST-021",
    "raw_text": "need whatever white fish you got that's fresh, 2 flats strawberries, and some butter"
  },
  {
    "id": "sample_005",
    "complexity": "email_formal",
    "channel": "email",
    "customer_id": "CUST-045",
    "raw_text": "Hi team,\n\nPlease prepare the following for Wednesday delivery:\n- Atlantic salmon fillets: 5 cases\n- Jumbo shrimp (16/20 count): 30 lbs\n- Roma tomatoes: 2 flats\n- Heavy cream: 6 quarts\n- Fresh basil: 3 bunches\n\nThank you,\nChef Marco\nBella Vista Restaurant"
  }
]
```

---

## Build Plan — 6 Days

### Day 1: Foundation
- **P1-P2:** DB schema + seed scripts (products, customers, inventory, suppliers, 6mo history)
- **P3-P4:** FastAPI scaffold + Twilio SMS webhook + ingestion API
- **P5:** Strands + Nova setup. First agent (Order Intake) with basic prompt, test with hardcoded input

### Day 2: Core Agents
- **P1-P2:** Product catalog embedding pipeline (Titan V2 + pgvector). Build search_products tool. Generate 100 sample orders.
- **P3-P4:** Order Intake Agent full build: all tools wired, handle corrections, 'the usual', vague requests
- **P5:** Inventory Agent: stock checking, expiry FIFO, substitution logic

### Day 3: Advanced Agents + Wiring
- **P1-P2:** Procurement Agent: supplier evaluation, PO generation, cost optimization
- **P3-P4:** Customer Intel Agent + Orchestrator wiring (agents-as-tools pattern)
- **P5:** End-to-end test: SMS in → all agents → confirmation out. Debug the full chain.

### Day 4: Dashboard
- **P1-P2:** React dashboard: real-time order feed (WebSocket), agent activity log
- **P3-P4:** Dashboard: inventory status, customer alerts, PO view, order detail with confidence scores
- **P5:** Integration testing. Edge cases. Confidence thresholds (auto-confirm vs needs-review)

### Day 5: Polish
- **P1-P2:** Dashboard polish. Architecture diagram. Loading states.
- **P3-P4:** Edge case handling. Error recovery. Demo data tuning.
- **P5:** Demo script rehearsal. Record backup video.

### Day 6: Ship
- **P1-P2:** Final demo rehearsal. Backup video recording.
- **P3-P4:** README, docs, submission materials.
- **P5:** Deploy to AWS. Final end-to-end test.

---

## Demo Script (3 minutes)

**0:00-0:30 — The Crisis**
"Food distribution is a trillion-dollar industry running on text messages and spreadsheets. Choco processes over $1B in orders. Pepper just raised $50M. Anchr raised $5.8M yesterday. This market is on fire. We built a working multi-agent prototype in one week, powered entirely by Amazon Nova."

**0:30-2:15 — Live Demo**
Text the FreshFlow number: "Hey need for tomorrow: 3 cases king salmon, 20 lbs jumbo shrimp, 2 flats strawberries, and whatever white fish you got. Thx"

Dashboard shows in real-time:
1. SMS received → customer identified → Order Intake Agent parses 4 items
2. 'whatever white fish' resolved to halibut (customer preference + current stock)
3. Inventory Agent: salmon ✓, shrimp ⚠️ (low, only 15 lbs), strawberries ✓, halibut ✓
4. Procurement Agent triggers: PO to Pacific Seafood for 5 cases jumbo shrimp
5. Customer Intel: order value 15% above 3-month average (positive signal)
6. Confirmation SMS sent back with order summary and shrimp availability note

**2:15-3:00 — Architecture + Impact**
"Five Nova-powered agents. One text message. Order parsed, inventory checked, purchase order generated, customer insight logged — all in seconds. This is what AI agents are for."
