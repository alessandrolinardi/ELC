-- Add dedicated phone column to addresses table
-- Previously phone was mixed into the 'reference' field
ALTER TABLE addresses ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT '';
