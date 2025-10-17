#!/usr/bin/env python3
"""
Export all data from Supabase for migration to Neon
"""
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# Re-enable Supabase for data export
SUPABASE_URL = "https://ldtyymvdmlipwtmhnwhx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxkdHl5bXZkbWxpcHd0bWhud2h4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MTEzMzU4OSwiZXhwIjoyMDY2NzA5NTg5fQ.CHb1ypLkoNafaxq5QGSxUkpct2_K-Ww_o65tGI84BRg"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def export_table(table_name):
    """Export all data from a table"""
    print(f"📤 Exporting {table_name}...")
    try:
        response = supabase.table(table_name).select("*").execute()
        data = response.data
        print(f"   ✅ Exported {len(data)} records from {table_name}")
        return data
    except Exception as e:
        print(f"   ❌ Error exporting {table_name}: {e}")
        return []

def main():
    """Export all data from Supabase"""
    print("🚀 Starting Supabase data export...")
    
    # Tables to export (in dependency order)
    tables = [
        'users',
        'jobs', 
        'parts',
        'deadlines',
        'estimates',
        'estimate_items',
        'files',
        'stocks'
    ]
    
    export_data = {}
    
    for table in tables:
        export_data[table] = export_table(table)
    
    # Save to JSON file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"supabase_export_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(export_data, f, indent=2, default=str)
    
    print(f"✅ Data export completed: {filename}")
    
    # Print summary
    print("\n📊 Export Summary:")
    total_records = 0
    for table, data in export_data.items():
        count = len(data)
        total_records += count
        print(f"   {table}: {count} records")
    print(f"   Total: {total_records} records")

if __name__ == "__main__":
    main()