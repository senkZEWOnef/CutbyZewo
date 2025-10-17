import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()  # Load from .env

NEON_CONNECTION_STRING = os.getenv("NEON_CONNECTION_STRING")

print(f"🔧 Neon Connection String present: {bool(NEON_CONNECTION_STRING)}")
if NEON_CONNECTION_STRING:
    print(f"🔧 Connection string starts with: {NEON_CONNECTION_STRING[:20]}...")

if not NEON_CONNECTION_STRING:
    print("❌ Missing Neon connection string!")
    raise Exception("Missing Neon connection string")

print("✅ Testing Neon connection...")

try:
    # Test connection
    conn = psycopg2.connect(NEON_CONNECTION_STRING)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT version();")
    version = cursor.fetchone()
    print(f"✅ Connected to PostgreSQL: {version['version']}")
    cursor.close()
    conn.close()
    print("✅ Neon client configured successfully")
except Exception as e:
    print(f"❌ Failed to connect to Neon: {e}")
    raise

def get_db_connection():
    """Get a new database connection"""
    return psycopg2.connect(NEON_CONNECTION_STRING)

def execute_query(query, params=None, fetch=False):
    """Execute a query and optionally fetch results"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(query, params)
        if fetch:
            result = cursor.fetchall()
            conn.commit()
            return result
        else:
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def execute_single(query, params=None):
    """Execute a query and fetch a single result"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(query, params)
        result = cursor.fetchone()
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()