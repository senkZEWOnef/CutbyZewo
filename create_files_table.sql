-- Create files table to track uploaded files
CREATE TABLE IF NOT EXISTS files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    file_type TEXT,
    file_size INTEGER,
    subfolder TEXT, -- e.g., 'accessories', 'main', etc.
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE
);

-- Add RLS policies (Note: Since we're using custom session auth, we'll allow all operations for authenticated users)
ALTER TABLE files ENABLE ROW LEVEL SECURITY;

-- Policy: Allow all operations for now - we handle security in the app layer
CREATE POLICY "Allow all operations on files" ON files
    FOR ALL USING (true) WITH CHECK (true);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_files_job_id ON files(job_id);
CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id);
CREATE INDEX IF NOT EXISTS idx_files_uploaded_at ON files(uploaded_at);