-- Add status column to jobs table for workflow management
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft';

-- Add check constraint to ensure valid status values
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check 
    CHECK (status IN ('draft', 'quoted', 'in_progress', 'completed', 'cancelled'));

-- Update existing jobs without status to 'draft'
UPDATE jobs SET status = 'draft' WHERE status IS NULL;

-- Update jobs with final_price to 'quoted' status
UPDATE jobs SET status = 'quoted' WHERE final_price IS NOT NULL AND status = 'draft';