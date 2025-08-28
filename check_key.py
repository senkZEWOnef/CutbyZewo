#!/usr/bin/env python3
"""
Check what Supabase key we're using
"""

import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print("🔍 Environment Variables Check")
print("=" * 50)
print(f"SUPABASE_URL: {SUPABASE_URL}")
print(f"SUPABASE_KEY: {SUPABASE_KEY[:50]}..." if SUPABASE_KEY else "SUPABASE_KEY: None")

if SUPABASE_KEY:
    # Decode the JWT to see what role it has
    import jwt
    try:
        # Decode without verification to see the payload
        decoded = jwt.decode(SUPABASE_KEY, options={"verify_signature": False})
        print(f"\nJWT Payload:")
        print(f"Role: {decoded.get('role', 'Not found')}")
        print(f"ISS: {decoded.get('iss', 'Not found')}")
        print(f"IAT: {decoded.get('iat', 'Not found')}")
        
        if decoded.get('role') == 'service_role':
            print("✅ Using SERVICE_ROLE key - should work!")
        elif decoded.get('role') == 'anon':
            print("❌ Using ANON key - this won't work for uploads!")
            print("👉 You need to use the SERVICE_ROLE key for uploads")
        else:
            print(f"❓ Unknown role: {decoded.get('role')}")
            
    except Exception as e:
        print(f"❌ Could not decode JWT: {e}")
        print("👉 Check if SUPABASE_KEY is valid")
else:
    print("❌ No SUPABASE_KEY found in environment!")
    print("👉 Check your .env file")