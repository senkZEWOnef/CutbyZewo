#!/usr/bin/env python3
"""
Test script for Supabase Storage connectivity
Run this to verify your storage setup works before trying uploads in the app
"""

import os
import uuid
from supabase_client import supabase
from storage_manager import StorageManager

def test_storage_connection():
    """Test basic connection to Supabase Storage"""
    print("🧪 Testing Supabase Storage connection...")
    print(f"🔑 Using URL: {supabase.supabase_url}")
    print(f"🔑 Using Key: {supabase.supabase_key[:20]}...")
    
    try:
        # Try to list buckets
        print("📡 Attempting to list buckets...")
        buckets = supabase.storage.list_buckets()
        print(f"📊 Raw response: {buckets}")
        print(f"📊 Response type: {type(buckets)}")
        
        if isinstance(buckets, list):
            print(f"✅ Connected! Found {len(buckets)} buckets:")
            
            for bucket in buckets:
                print(f"   - {bucket.name} (id: {bucket.id}, public: {bucket.public})")
                
            # Check if our uploads bucket exists
            uploads_bucket = next((b for b in buckets if b.name == "uploads"), None)
            if uploads_bucket:
                print(f"✅ 'uploads' bucket found! Public: {uploads_bucket.public}")
                return True
            else:
                print("❌ 'uploads' bucket not found in list!")
                return False
        else:
            print(f"❌ Unexpected buckets response: {buckets}")
            return False
            
    except Exception as e:
        print(f"❌ Storage connection failed: {e}")
        print(f"❌ Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        print("👉 Check your SUPABASE_URL and SUPABASE_KEY in .env")
        return False

def test_file_upload():
    """Test uploading a dummy file directly to uploads bucket"""
    print("\n🧪 Testing direct file upload to 'uploads' bucket...")
    
    try:
        # Create a test file content
        test_content = b"Hello, this is a test file for byZewo!"
        test_path = f"test/test_file_{uuid.uuid4().hex[:8]}.txt"
        
        print(f"📤 Uploading test file to: {test_path}")
        
        # Upload directly using Supabase client
        result = supabase.storage.from_("uploads").upload(
            path=test_path,
            file=test_content,
            file_options={
                "content-type": "text/plain",
                "upsert": "true"
            }
        )
        
        print(f"📊 Upload result: {result}")
        print(f"📊 Result type: {type(result)}")
        
        # Check if upload was successful (different response formats)
        success = False
        if isinstance(result, dict) and result.get('path'):
            success = True
            print(f"✅ Upload successful! Path: {result['path']}")
        elif hasattr(result, 'path'):
            success = True
            print(f"✅ Upload successful! Path: {result.path}")
        elif result is not None:
            success = True
            print(f"✅ Upload appears successful: {result}")
        
        if success:
            # Try to get public URL
            print(f"🔗 Testing public URL generation...")
            url = supabase.storage.from_("uploads").get_public_url(test_path)
            print(f"🔗 Public URL: {url}")
            
            # Clean up test file
            print("🧹 Cleaning up test file...")
            cleanup = supabase.storage.from_("uploads").remove([test_path])
            print(f"🧹 Cleanup result: {cleanup}")
            
            return True
        else:
            print("❌ Upload failed - no valid response")
            return False
            
    except Exception as e:
        print(f"❌ Upload test failed: {e}")
        print(f"❌ Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 byZewo Storage Test")
    print("=" * 50)
    
    # Test 1: Connection (informational)
    print("📡 Testing basic connection...")
    test_storage_connection()
    
    # Test 2: The real test - can we upload files?
    print("\n" + "="*30)
    upload_ok = test_file_upload()
    
    print("\n" + "="*50)
    if upload_ok:
        print("🎉 SUCCESS! Storage is working perfectly!")
        print("✅ Files can be uploaded and retrieved")
        print("🚀 Your app should work now!")
    else:
        print("❌ FAILED! Storage upload not working")
        print("👉 Check bucket exists and policies are correct")
    
    print("=" * 50)