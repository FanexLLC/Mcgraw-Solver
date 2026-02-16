"""
Database migration script for Stripe integration and new features.
Run this before deploying the updated application.

Usage:
    python server/migrate.py

Migrations:
    - Add payment_method and stripe_session_id columns to orders table
    - Add preferred_model column to keys table
    - Create email_retry_queue table for failed email delivery
    - Create active_sessions table for one-device-at-a-time enforcement
    - Create indexes for performance optimization
"""
import os
import sys
import psycopg2
from datetime import datetime


def run_migration():
    """Execute database migrations."""
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Please set DATABASE_URL to your PostgreSQL connection string")
        sys.exit(1)

    print(f"Connecting to database...")
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        conn.autocommit = True
        print("✓ Connected successfully")
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        sys.exit(1)

    try:
        print("\n=== Starting Database Migration ===\n")

        # Migration 1: Add payment_method and stripe_session_id to orders table
        print("1. Adding payment_method and stripe_session_id columns to orders table...")
        cur.execute("""
            ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method TEXT DEFAULT 'venmo';
        """)
        cur.execute("""
            ALTER TABLE orders ADD COLUMN IF NOT EXISTS stripe_session_id TEXT;
        """)
        print("   ✓ Columns added successfully")

        # Migration 2: Add preferred_model to keys table
        print("2. Adding preferred_model column to keys table...")
        cur.execute("""
            ALTER TABLE keys ADD COLUMN IF NOT EXISTS preferred_model TEXT;
        """)
        print("   ✓ Column added successfully")

        # Migration 3: Create email_retry_queue table
        print("3. Creating email_retry_queue table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_retry_queue (
                id SERIAL PRIMARY KEY,
                order_id TEXT,
                email_type TEXT,  -- 'key_email' or 'admin_notification'
                recipient TEXT,
                template_params JSONB,
                attempts INTEGER DEFAULT 0,
                last_attempt TIMESTAMP,
                created TIMESTAMP DEFAULT NOW()
            );
        """)
        print("   ✓ email_retry_queue table created")

        # Migration 4: Create active_sessions table
        print("4. Creating active_sessions table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                id SERIAL PRIMARY KEY,
                access_key TEXT NOT NULL,
                session_id TEXT UNIQUE NOT NULL,
                started_at TIMESTAMP DEFAULT NOW(),
                last_heartbeat TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (access_key) REFERENCES keys(key) ON DELETE CASCADE
            );
        """)
        print("   ✓ active_sessions table created")

        # Migration 5: Create indexes
        print("5. Creating database indexes...")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_heartbeat ON active_sessions(last_heartbeat);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_key ON active_sessions(access_key);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_stripe_session ON orders(stripe_session_id);
        """)
        print("   ✓ Indexes created successfully")

        # Verify migrations
        print("\n=== Verifying Migration ===\n")

        # Check orders table columns
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'orders'
            AND column_name IN ('payment_method', 'stripe_session_id')
            ORDER BY column_name;
        """)
        orders_columns = [row[0] for row in cur.fetchall()]
        print(f"✓ Orders table columns: {', '.join(orders_columns)}")

        # Check keys table columns
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'keys'
            AND column_name = 'preferred_model';
        """)
        keys_columns = [row[0] for row in cur.fetchall()]
        print(f"✓ Keys table columns: {', '.join(keys_columns)}")

        # Check email_retry_queue table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'email_retry_queue'
            );
        """)
        email_queue_exists = cur.fetchone()[0]
        print(f"✓ email_retry_queue table exists: {email_queue_exists}")

        # Check active_sessions table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'active_sessions'
            );
        """)
        sessions_exists = cur.fetchone()[0]
        print(f"✓ active_sessions table exists: {sessions_exists}")

        # Check indexes
        cur.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE indexname IN ('idx_sessions_heartbeat', 'idx_sessions_key', 'idx_orders_stripe_session')
            ORDER BY indexname;
        """)
        indexes = [row[0] for row in cur.fetchall()]
        print(f"✓ Indexes created: {', '.join(indexes)}")

        print("\n=== Migration Completed Successfully ===\n")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("\nNext steps:")
        print("1. Deploy updated application code to Railway")
        print("2. Configure Stripe webhook in Stripe Dashboard")
        print("3. Add new environment variables to Railway")
        print("4. Test Stripe checkout in test mode")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    print("McGraw Solver - Database Migration Script")
    print("=" * 50)
    run_migration()
