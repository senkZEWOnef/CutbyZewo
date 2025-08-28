-- Create table for detailed estimate line items
CREATE TABLE IF NOT EXISTS estimate_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id UUID NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
    item_type VARCHAR(50) NOT NULL, -- 'material', 'hardware', 'labor'
    name VARCHAR(255) NOT NULL, -- 'Plywood 3/4"', 'European Hinges', 'Installation Labor'
    description TEXT, -- Additional details
    quantity DECIMAL(10,2) NOT NULL DEFAULT 1,
    unit VARCHAR(20), -- 'sheets', 'pieces', 'hours', 'sq ft'
    unit_price DECIMAL(10,2) NOT NULL,
    total_price DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Add RLS (Row Level Security)
ALTER TABLE estimate_items ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see estimate items for their own estimates
CREATE POLICY "Users can view their own estimate items" ON estimate_items
    FOR SELECT USING (
        estimate_id IN (
            SELECT e.id FROM estimates e
            JOIN jobs j ON e.job_id = j.id
            WHERE j.user_id = auth.uid()
        )
    );

-- Policy: Users can insert estimate items for their own estimates
CREATE POLICY "Users can insert estimate items for their own estimates" ON estimate_items
    FOR INSERT WITH CHECK (
        estimate_id IN (
            SELECT e.id FROM estimates e
            JOIN jobs j ON e.job_id = j.id
            WHERE j.user_id = auth.uid()
        )
    );

-- Policy: Users can update their own estimate items
CREATE POLICY "Users can update their own estimate items" ON estimate_items
    FOR UPDATE USING (
        estimate_id IN (
            SELECT e.id FROM estimates e
            JOIN jobs j ON e.job_id = j.id
            WHERE j.user_id = auth.uid()
        )
    );

-- Policy: Users can delete their own estimate items
CREATE POLICY "Users can delete their own estimate items" ON estimate_items
    FOR DELETE USING (
        estimate_id IN (
            SELECT e.id FROM estimates e
            JOIN jobs j ON e.job_id = j.id
            WHERE j.user_id = auth.uid()
        )
    );

-- Add index for better performance
CREATE INDEX IF NOT EXISTS idx_estimate_items_estimate_id ON estimate_items(estimate_id);

-- Update existing estimates table to add more fields
ALTER TABLE estimates ADD COLUMN IF NOT EXISTS name VARCHAR(255);
ALTER TABLE estimates ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE estimates ADD COLUMN IF NOT EXISTS labor_rate DECIMAL(10,2) DEFAULT 50.00;
ALTER TABLE estimates ADD COLUMN IF NOT EXISTS markup_percentage DECIMAL(5,2) DEFAULT 20.00;