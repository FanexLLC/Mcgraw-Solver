"""Email sending via EmailJS API."""

from __future__ import annotations
import os
import logging
from datetime import datetime

import requests as http_requests

logger = logging.getLogger(__name__)

EMAILJS_SERVICE_ID = os.environ.get("EMAILJS_SERVICE_ID", "")
EMAILJS_TEMPLATE_ID = os.environ.get("EMAILJS_TEMPLATE_ID", "")
EMAILJS_ADMIN_TEMPLATE_ID = os.environ.get("EMAILJS_ADMIN_TEMPLATE_ID", "")
EMAILJS_PUBLIC_KEY = os.environ.get("EMAILJS_PUBLIC_KEY", "")
EMAILJS_PRIVATE_KEY = os.environ.get("EMAILJS_PRIVATE_KEY", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
DOWNLOAD_URL = os.environ.get("DOWNLOAD_URL", "")

EMAILJS_API_URL = "https://api.emailjs.com/api/v1.0/email/send"

# Plan display names with updated pricing
PLAN_DISPLAY = {
    "weekly": "Weekly ($10)",
    "monthly": "Monthly ($25)",
    "semester": "Semester ($50)"
}


def send_key_email(email: str, name: str, key: str, plan: str, expiry_date: str) -> bool:
    """Send access key email to a customer."""
    try:
        parsed = datetime.fromisoformat(expiry_date.rstrip("Z"))
        expiry_date = parsed.strftime("%B %d, %Y")
    except (ValueError, AttributeError):
        pass

    if not all([EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, EMAILJS_PUBLIC_KEY]):
        logger.warning("EmailJS not configured, skipping email")
        return False

    try:
        resp = http_requests.post(
            EMAILJS_API_URL,
            json={
                "service_id": EMAILJS_SERVICE_ID,
                "template_id": EMAILJS_TEMPLATE_ID,
                "user_id": EMAILJS_PUBLIC_KEY,
                "accessToken": EMAILJS_PRIVATE_KEY,
                "template_params": {
                    "to_email": email,
                    "to_name": name,
                    "access_key": key,
                    "plan": PLAN_DISPLAY.get(plan, plan),
                    "expiry_date": expiry_date,
                    "download_url": DOWNLOAD_URL,
                },
            },
            timeout=30,
        )
        if resp.status_code == 200:
            logger.info(f"Email sent to {email}")
            return True
        logger.error(f"EmailJS error: {resp.status_code} {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def send_admin_order_notification(order: dict) -> bool:
    """Send admin an email when a new order is placed (Venmo orders only)."""
    # Only send notifications for Venmo orders, not Stripe orders
    if order.get("payment_method") == "stripe":
        logger.info("Skipping admin notification for Stripe order")
        return True

    if not all([EMAILJS_SERVICE_ID, EMAILJS_ADMIN_TEMPLATE_ID, EMAILJS_PUBLIC_KEY, ADMIN_EMAIL]):
        logger.warning("Admin notification not configured, skipping")
        return False

    plan_display = PLAN_DISPLAY.get(order["plan"], order["plan"])
    try:
        resp = http_requests.post(
            EMAILJS_API_URL,
            json={
                "service_id": EMAILJS_SERVICE_ID,
                "template_id": EMAILJS_ADMIN_TEMPLATE_ID,
                "user_id": EMAILJS_PUBLIC_KEY,
                "accessToken": EMAILJS_PRIVATE_KEY,
                "template_params": {
                    "to_email": ADMIN_EMAIL,
                    "customer_name": order["name"],
                    "customer_email": order["email"],
                    "venmo_username": order["venmo_username"],
                    "transaction_id": order["transaction_id"],
                    "plan": plan_display,
                    "order_id": order["id"],
                },
            },
            timeout=30,
        )
        if resp.status_code == 200:
            logger.info(f"Admin notification sent for order {order['id']}")
            return True
        logger.error(f"Admin notification EmailJS error: {resp.status_code} {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Admin notification failed: {e}")
        return False
