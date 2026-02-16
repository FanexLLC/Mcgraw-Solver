"""
Cron job runner for Railway.
Runs scheduled tasks using APScheduler.

This service should be deployed as a separate Railway service.
"""
import os
import logging
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_email_retry():
    """Run email retry job (hourly)"""
    logger.info("Starting email retry job...")
    try:
        from retry_emails import retry_failed_emails
        retry_failed_emails()
    except Exception as e:
        logger.error(f"Email retry job failed: {e}")

def run_session_cleanup():
    """Run session cleanup job (every 5 minutes)"""
    logger.info("Starting session cleanup job...")
    try:
        from cleanup_sessions import cleanup_stale_sessions
        cleanup_stale_sessions()
    except Exception as e:
        logger.error(f"Session cleanup job failed: {e}")

if __name__ == "__main__":
    scheduler = BlockingScheduler()

    # Email retry: DISABLED for now (can re-enable later if needed)
    # scheduler.add_job(run_email_retry, 'cron', minute=0)

    # Session cleanup: Run every 5 minutes
    scheduler.add_job(run_session_cleanup, 'cron', minute='*/5')

    logger.info("Cron scheduler started")
    logger.info("- Email retry: DISABLED")
    logger.info("- Session cleanup: Every 5 minutes")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Cron scheduler stopped")
