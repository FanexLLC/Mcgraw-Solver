"""
Session cleanup worker for removing stale sessions.
Run as Railway cron job: */5 * * * * python server/cleanup_sessions.py (every 5 minutes)

This script:
1. Finds sessions that haven't sent a heartbeat in 60 seconds
2. Deletes them from the database
3. Allows new sessions to start on those keys
"""
import os
import sys
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_stale_sessions():
    """Clean up sessions that haven't sent heartbeats."""
    try:
        import psycopg2

        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set")
            return

        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cur = conn.cursor()

        # Delete sessions with no heartbeat in last 60 seconds
        timeout_seconds = 60
        cur.execute(
            """DELETE FROM active_sessions
               WHERE last_heartbeat < NOW() - make_interval(secs => %s)
               RETURNING access_key, session_id""",
            (timeout_seconds,)
        )

        deleted_sessions = cur.fetchall()
        deleted_count = len(deleted_sessions)

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} stale session(s):")
            for access_key, session_id in deleted_sessions:
                logger.info(f"  - Key: {access_key[:8]}..., Session: {session_id[:8]}...")
        else:
            logger.info("No stale sessions found")

        # Log current active session count
        cur.execute("SELECT COUNT(*) FROM active_sessions")
        active_count = cur.fetchone()[0]
        logger.info(f"Active sessions remaining: {active_count}")

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Session cleanup job failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    logger.info("=== Session Cleanup Job Started ===")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    cleanup_stale_sessions()
    logger.info("=== Session Cleanup Job Finished ===")
