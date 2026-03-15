-- FreshFlow Phase 1: Database schema (runs on Postgres first startup)
CREATE EXTENSION IF NOT EXISTS vector;

-- Suppliers (no dependencies)
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(200),
    lead_time_days INTEGER,
    min_order_value DECIMAL(10,2),
    reliability_score DECIMAL(3,2),
    phone VARCHAR(20),
    email VARCHAR(200)
);

-- Products (depends on suppliers)
CREATE TABLE IF NOT EXISTS products (
    sku_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    aliases TEXT[],
    category VARCHAR(50),
    subcategory VARCHAR(50),
    unit_of_measure VARCHAR(20),
    case_size DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    cost_price DECIMAL(10,2),
    shelf_life_days INTEGER,
    storage_type VARCHAR(20),
    supplier_id VARCHAR(20) REFERENCES suppliers(supplier_id),
    status VARCHAR(20) DEFAULT 'active',
    embedding vector(1024)
);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_subcategory ON products(subcategory);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
CREATE INDEX IF NOT EXISTS idx_products_embedding ON products USING hnsw (embedding vector_cosine_ops);

-- Customers
CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(200),
    type VARCHAR(50),
    phone VARCHAR(20) UNIQUE,
    email VARCHAR(200),
    delivery_days TEXT[],
    payment_terms VARCHAR(20),
    credit_limit DECIMAL(10,2),
    avg_order_value DECIMAL(10,2),
    account_health VARCHAR(20),
    days_since_last_order INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);

-- Customer preferences (depends on customers)
CREATE TABLE IF NOT EXISTS customer_preferences (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(20) REFERENCES customers(customer_id),
    preference_type VARCHAR(50),
    description TEXT,
    product_sku VARCHAR(20),
    substitute_sku VARCHAR(20)
);
CREATE INDEX IF NOT EXISTS idx_customer_preferences_customer_id ON customer_preferences(customer_id);

-- Inventory (depends on products)
CREATE TABLE IF NOT EXISTS inventory (
    id SERIAL PRIMARY KEY,
    sku_id VARCHAR(20) REFERENCES products(sku_id),
    quantity DECIMAL(10,2),
    reorder_point DECIMAL(10,2),
    reorder_quantity DECIMAL(10,2),
    lot_number VARCHAR(50),
    received_date DATE,
    expiration_date DATE,
    warehouse_zone VARCHAR(20),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inventory_sku_id ON inventory(sku_id);
CREATE INDEX IF NOT EXISTS idx_inventory_warehouse_zone ON inventory(warehouse_zone);

-- Supplier products (depends on suppliers, products)
CREATE TABLE IF NOT EXISTS supplier_products (
    id SERIAL PRIMARY KEY,
    supplier_id VARCHAR(20) REFERENCES suppliers(supplier_id),
    sku_id VARCHAR(20) REFERENCES products(sku_id),
    supplier_price DECIMAL(10,2),
    min_order_qty DECIMAL(10,2),
    available BOOLEAN DEFAULT true
);
CREATE INDEX IF NOT EXISTS idx_supplier_products_supplier_id ON supplier_products(supplier_id);
CREATE INDEX IF NOT EXISTS idx_supplier_products_sku_id ON supplier_products(sku_id);

-- Orders (depends on customers)
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(20) REFERENCES customers(customer_id),
    channel VARCHAR(20),
    raw_message TEXT,
    status VARCHAR(20),
    confidence_score DECIMAL(3,2),
    total_amount DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW(),
    confirmed_at TIMESTAMP,
    agent_trace JSONB
);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);

-- Order items (depends on orders, products)
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(20) REFERENCES orders(order_id),
    sku_id VARCHAR(20) REFERENCES products(sku_id),
    raw_text VARCHAR(200),
    quantity DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    line_total DECIMAL(10,2),
    match_confidence DECIMAL(3,2),
    status VARCHAR(20),
    substituted_from VARCHAR(20),
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- Purchase orders (depends on suppliers)
CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id VARCHAR(20) PRIMARY KEY,
    supplier_id VARCHAR(20) REFERENCES suppliers(supplier_id),
    status VARCHAR(20),
    total_amount DECIMAL(10,2),
    triggered_by VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- PO items (depends on purchase_orders, products)
CREATE TABLE IF NOT EXISTS po_items (
    id SERIAL PRIMARY KEY,
    po_id VARCHAR(20) REFERENCES purchase_orders(po_id),
    sku_id VARCHAR(20) REFERENCES products(sku_id),
    quantity DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    line_total DECIMAL(10,2)
);

-- Customer alerts (depends on customers)
CREATE TABLE IF NOT EXISTS customer_alerts (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(20) REFERENCES customers(customer_id),
    alert_type VARCHAR(50),
    description TEXT,
    severity VARCHAR(20),
    acknowledged BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);
