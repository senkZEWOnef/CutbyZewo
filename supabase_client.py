# supabase_client.py

from supabase import create_client, Client

# Supabase project credentials
SUPABASE_URL = "https://ldtyymvdmlipwtmhnwhx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkdHl5bXZkbWxpcHd0bWhud2h4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTExMzM1ODksImV4cCI6MjA2NjcwOTU4OX0.hTJQ0fsjoEpIymgGHl0t2F5mz-QZfyCSmOOEmjt0u6M"

# Create Supabase client instance
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
