-- Simple Storage Test - run this in Supabase SQL Editor
-- This will show us what role/permissions we're working with

-- Check current role and permissions
SELECT current_user as current_role;
SELECT current_setting('role') as current_setting_role;

-- Check if RLS is enabled on storage.objects
SELECT schemaname, tablename, rowsecurity 
FROM pg_tables 
WHERE tablename = 'objects' AND schemaname = 'storage';

-- List existing policies on storage.objects
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies 
WHERE tablename = 'objects' AND schemaname = 'storage';

-- Check bucket configuration
SELECT id, name, public, file_size_limit, allowed_mime_types 
FROM storage.buckets 
WHERE id = 'uploads';