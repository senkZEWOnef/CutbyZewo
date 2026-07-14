import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, execute_values
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

# Reused across requests instead of opening a fresh TCP+TLS connection per
# query — that was adding ~0.5s per query and made large jobs (100+ parts)
# time out mid-request before cut sheets ever got generated.
_pool = psycopg2.pool.ThreadedConnectionPool(1, 10, NEON_CONNECTION_STRING)

def get_db_connection():
    """Borrow a connection from the pool"""
    return _pool.getconn()

def _release(conn, discard=False):
    if discard:
        # Neon can drop idle connections (e.g. compute auto-suspend); don't
        # hand a dead connection back to the pool.
        _pool.putconn(conn, close=True)
    else:
        _pool.putconn(conn)

def _execute_once(query, params, fetch, fetch_one):
    conn = get_db_connection()
    stale = False
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(query, params)
            if fetch_one:
                result = cursor.fetchone()
            elif fetch:
                result = cursor.fetchall()
            else:
                result = cursor.rowcount
            conn.commit()
            return result
        finally:
            cursor.close()
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        # Connection was stale (e.g. Neon suspended the compute) — discard
        # it so it isn't handed back to the pool, then let the caller retry.
        stale = True
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn, discard=stale)

def _run(query, params, fetch, fetch_one):
    try:
        return _execute_once(query, params, fetch, fetch_one)
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        return _execute_once(query, params, fetch, fetch_one)

def execute_query(query, params=None, fetch=False):
    """Execute a query and optionally fetch results"""
    return _run(query, params, fetch, fetch_one=False)

def execute_single(query, params=None):
    """Execute a query and fetch a single result"""
    return _run(query, params, fetch=True, fetch_one=True)

def _execute_batch_once(query_template, rows):
    conn = get_db_connection()
    stale = False
    try:
        cursor = conn.cursor()
        try:
            execute_values(cursor, query_template, rows)
            conn.commit()
            return cursor.rowcount
        finally:
            cursor.close()
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        stale = True
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn, discard=stale)

def execute_batch_insert(query_template, rows):
    """Insert many rows in one round trip. query_template looks like
    'INSERT INTO t (a, b) VALUES %s' — psycopg2 expands %s per row of `rows`."""
    if not rows:
        return 0
    try:
        return _execute_batch_once(query_template, rows)
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        return _execute_batch_once(query_template, rows)