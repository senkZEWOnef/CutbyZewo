import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()  # Load from .env

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print(f"🔧 Supabase URL: {SUPABASE_URL}")
print(f"🔧 Supabase Key present: {bool(SUPABASE_KEY)}")
if SUPABASE_KEY:
    print(f"🔧 Key starts with: {SUPABASE_KEY[:20]}...")
    print(f"🔧 Key length: {len(SUPABASE_KEY)}")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Missing Supabase credentials!")
    raise Exception("Missing Supabase credentials")

print("✅ Creating Supabase client...")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✅ Supabase client created successfully")
