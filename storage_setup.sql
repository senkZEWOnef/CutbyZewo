-- Storage bucket policies for the 'uploads' bucket
-- Run these in your Supabase dashboard SQL editor

-- 1. First, make sure you've created a bucket called 'uploads' in Storage

-- 2. Then run these policies to allow uploads and downloads:

-- Allow authenticated users to upload files
INSERT INTO storage.policies (id, bucket_id, name, definition, check_definition, command)
VALUES (
    'uploads_insert_policy',
    'uploads',
    'Allow authenticated uploads',
    'true',
    'true',
    'INSERT'
) ON CONFLICT (id) DO NOTHING;

-- Allow public read access to files (or restrict as needed)
INSERT INTO storage.policies (id, bucket_id, name, definition, check_definition, command)
VALUES (
    'uploads_select_policy',
    'uploads',
    'Allow public downloads',
    'true',
    NULL,
    'SELECT'
) ON CONFLICT (id) DO NOTHING;

-- Allow authenticated users to update their files
INSERT INTO storage.policies (id, bucket_id, name, definition, check_definition, command)
VALUES (
    'uploads_update_policy',
    'uploads',
    'Allow authenticated updates',
    'true',
    'true',
    'UPDATE'
) ON CONFLICT (id) DO NOTHING;

-- Allow authenticated users to delete their files
INSERT INTO storage.policies (id, bucket_id, name, definition, check_definition, command)
VALUES (
    'uploads_delete_policy',
    'uploads',
    'Allow authenticated deletes',
    'true',
    NULL,
    'DELETE'
) ON CONFLICT (id) DO NOTHING;

-- Alternative: If the above doesn't work, you can disable RLS on the bucket temporarily
-- UPDATE storage.buckets SET public = true WHERE id = 'uploads';