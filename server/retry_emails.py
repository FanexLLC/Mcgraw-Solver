"""
Email retry worker for failed email deliveries.
Run as Railway cron job: 0 * * * * python server/retry_emails.py (hourly)

This script:
1. Finds emails that failed to send and are due for retry
2. Attempts to resend them
3. Tracks retry attempts
4. Notifies admin after 5 failed attempts
"""
import os
import sys
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def retry_failed_emails():
    """Retry failed emails from the queue."""
    try:
        import psycopg2
        from email_service import send_key_email, PLAN_DISPLAY, ADMIN_EMAIL

        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set")
            return

        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cur = conn.cursor()

        # Get emails to retry (< 24 hours old, < 5 attempts, not retried in last hour)
        cur.execute("""
            SELECT id, order_id, email_type, recipient, template_params, attempts
            FROM email_retry_queue
            WHERE attempts < 5
            AND created > NOW() - INTERVAL '24 hours'
            AND (last_attempt IS NULL OR last_attempt < NOW() - INTERVAL '1 hour')
        """)

        pending = cur.fetchall()
        logger.info(f"Found {len(pending)} emails to retry")

        for row in pending:
            queue_id, order_id, email_type, recipient, params_json, attempts = row

            try:
                params = json.loads(params_json) if isinstance(params_json, str) else params_json
                logger.info(f"Retrying {email_type} for order {order_id} (attempt {attempts + 1})")

                # Attempt to send email
                if email_type == "key_email":
                    send_key_email(
                        recipient,
                        params["name"],
                        params["key"],
                        params["plan"],
                        params["expires"]
                    )
                else:
                    logger.warning(f"Unknown email type: {email_type}")
                    continue

                # Delete from queue on success
                cur.execute("DELETE FROM email_retry_queue WHERE id = %s", (queue_id,))
                logger.info(f"✓ Email sent successfully for order {order_id}")

            except Exception as e:
                logger.error(f"✗ Retry failed for order {order_id}: {e}")

                # Update attempts
                new_attempts = attempts + 1
                cur.execute(
                    "UPDATE email_retry_queue SET attempts = %s, last_attempt = NOW() WHERE id = %s",
                    (new_attempts, queue_id)
                )

                # If this was the 5th attempt, notify admin
                if new_attempts >= 5:
                    logger.error(f"Email failed 5 times for order {order_id}, giving up")
                    # Could send admin notification here if needed
                    try:
                        # Log critical error
                        logger.critical(f"ADMIN ALERT: Email delivery failed after 5 attempts for order {order_id}")
                    except Exception as notify_error:
                        logger.error(f"Failed to notify admin: {notify_error}")

        cur.close()
        conn.close()
        logger.info("Email retry job completed")

    except Exception as e:
        logger.error(f"Email retry job failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    logger.info("=== Email Retry Job Started ===")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    retry_failed_emails()
    logger.info("=== Email Retry Job Finished ===")
