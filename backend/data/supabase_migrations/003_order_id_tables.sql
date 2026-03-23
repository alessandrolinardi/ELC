-- Order ID Management tables
-- Run this in the Supabase SQL Editor

-- brands table
CREATE TABLE IF NOT EXISTS brands (
    name TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed initial brands
INSERT INTO brands (name) VALUES ('SBX'), ('DOUGLAS')
ON CONFLICT (name) DO NOTHING;

-- processed_orders table with 90-day TTL
CREATE TABLE IF NOT EXISTS processed_orders (
    order_number TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    brand TEXT,
    campaign TEXT,
    po_number TEXT,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX IF NOT EXISTS idx_processed_orders_expires
    ON processed_orders (expires_at);

CREATE INDEX IF NOT EXISTS idx_processed_orders_campaign
    ON processed_orders (campaign);
