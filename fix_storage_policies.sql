-- Fix Storage Policies for byZewo
-- Run this in Supabase SQL Editor

-- First, drop the existing policies that aren't working
DROP POLICY IF EXISTS "Allow public reads" ON storage.objects;
DROP POLICY IF EXISTS "Allow authenticated uploads" ON storage.objects;
DROP POLICY IF EXISTS "Allow authenticated updates" ON storage.objects;
DROP POLICY IF EXISTS "Allow authenticated deletes" ON storage.objects;

-- Since you're using custom session auth (not Supabase Auth), 
-- we need simpler policies that allow service role access

-- Policy 1: Allow service role to do everything (for your app)
CREATE POLICY "Service role full access" ON storage.objects
FOR ALL 
TO service_role
USING (bucket_id = 'uploads')
WITH CHECK (bucket_id = 'uploads');

-- Policy 2: Allow public read access (so users can view images)
CREATE POLICY "Public read access" ON storage.objects
FOR SELECT 
TO public
USING (bucket_id = 'uploads');

-- Policy 3: Allow authenticated role full access (backup)
CREATE POLICY "Authenticated full access" ON storage.objects
FOR ALL 
TO authenticated
USING (bucket_id = 'uploads')
WITH CHECK (bucket_id = 'uploads');

-- Alternative: If the above still doesn't work, uncomment this to disable RLS entirely on storage.objects
-- ALTER TABLE storage.objects DISABLE ROW LEVEL SECURITY;