-- Add cancellation tracking columns to elc_pickups
ALTER TABLE elc_pickups ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE elc_pickups ADD COLUMN IF NOT EXISTS cancellation_reason TEXT DEFAULT NULL;
ALTER TABLE elc_pickups ADD COLUMN IF NOT EXISTS zapier_notified BOOLEAN DEFAULT NULL;
