"""Flask API server — routes and request handling."""

from __future__ import annotations
import os
import re
import time
import logging
import secrets
from collections import defaultdict
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import stripe
import jwt

from db import (
    init_db, find_key, update_key_usage, generate_key_with_expiry,
    list_keys, revoke_key, create_order, list_orders, find_order,
    update_order, PLAN_DURATIONS, _use_db, find_order_by_stripe_session,
    update_order_stripe_session, update_order_status, update_key_preference,
    add_to_email_retry_queue, create_session, update_session_heartbeat,
    end_session, get_active_session,
)
from email_service import send_key_email, send_admin_order_notification

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────

RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "120"))
RATE_WINDOW = 3600

_rate_tracker: dict[str, list[float]] = defaultdict(list)

CORS(app, origins=[
    "https://fanexllc.github.io",
    "http://localhost:*",
    "http://127.0.0.1:*",
])

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")

CLAUDE_MODELS = {"claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001",
                 "claude-sonnet-4-5", "claude-haiku-4-5"}

# ── Stripe Configuration ──────────────────────────────────────────
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_MODE = os.environ.get("STRIPE_MODE", "test")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://fanexllc.github.io")

# Map plans to Stripe Price IDs
STRIPE_PRICES = {
    "weekly": os.environ.get("STRIPE_PRICE_WEEKLY", ""),
    "monthly": os.environ.get("STRIPE_PRICE_MONTHLY", ""),
    "semester": os.environ.get("STRIPE_PRICE_SEMESTER", "")
}

# Price amounts for validation (in cents)
PRICE_AMOUNTS = {
    "weekly": 1000,    # $10.00
    "monthly": 2500,   # $25.00
    "semester": 5000   # $50.00
}

# ── AI Model Tiers ────────────────────────────────────────────────

# Plan-based model access control
PLAN_MODEL_ACCESS = {
    "weekly": ["gpt-4o-mini"],
    "monthly": ["gpt-4o-mini", "gpt-4o"],
    "semester": ["gpt-4o-mini", "gpt-4o", "claude-sonnet-4-5-20250929",
                 "claude-sonnet-4-5", "claude-haiku-4-5-20251001", "claude-haiku-4-5"],
}

# Default models for each plan
PLAN_DEFAULT_MODELS = {
    "weekly": "gpt-4o-mini",
    "monthly": "gpt-4o",
    "semester": "claude-sonnet-4-5-20250929",
}

# Model display names
MODEL_DISPLAY_NAMES = {
    "gpt-4o-mini": "GPT-4o Mini",
    "gpt-4o": "GPT-4o",
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5",
    "claude-sonnet-4-5": "Claude Sonnet 4.5",
    "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
    "claude-haiku-4-5": "Claude Haiku 4.5",
}


def get_default_model_for_plan(plan: str) -> str:
    """Get the default AI model for a given plan."""
    return PLAN_DEFAULT_MODELS.get(plan, "gpt-4o-mini")


def is_model_allowed_for_plan(model: str, plan: str) -> bool:
    """Check if a model is allowed for a given plan."""
    return model in PLAN_MODEL_ACCESS.get(plan, [])

# ── API Clients ───────────────────────────────────────────────────

_openai_client: OpenAI | None = None
_anthropic_client = None


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not set on server")
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set on server")
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


# ── Auth ──────────────────────────────────────────────────────────

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        password = request.headers.get("X-Admin-Password", "")
        if not ADMIN_PASSWORD or password != ADMIN_PASSWORD:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def notify_admin_error(error_type: str, details: str) -> None:
    """Send admin email for critical errors."""
    critical_errors = ["webhook_signature_failed", "payment_amount_mismatch", "email_retry_exhausted"]
    if error_type in critical_errors:
        try:
            admin_email = os.environ.get("ADMIN_EMAIL", "")
            if admin_email:
                # Log the error (email sending would go here in production)
                logger.error(f"CRITICAL: {error_type} - {details}")
                # Note: Full email integration can be added here if needed
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")


def _check_key_expiry(key_entry: dict) -> str | None:
    """Return error message if key is expired, else None."""
    expires_val = key_entry.get("expires")
    if not expires_val:
        return None
    if isinstance(expires_val, str):
        expiry = datetime.fromisoformat(expires_val.rstrip("Z"))
    else:
        expiry = expires_val
    if datetime.utcnow() > expiry:
        return "Access key expired. Please renew your subscription."
    return None


# ── Endpoints ─────────────────────────────────────────────────────

@app.route("/api/solve", methods=["POST"])
def solve():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    access_key = data.get("access_key", "")
    key_entry = find_key(access_key)
    if not key_entry:
        return jsonify({"error": "Invalid access key"}), 403

    expiry_error = _check_key_expiry(key_entry)
    if expiry_error:
        return jsonify({"error": expiry_error}), 403

    # Rate limiting
    now = time.time()
    window_start = now - RATE_WINDOW
    _rate_tracker[access_key] = [t for t in _rate_tracker[access_key] if t > window_start]
    if len(_rate_tracker[access_key]) >= RATE_LIMIT:
        logger.warning(f"Rate limit hit for key={access_key[:8]}...")
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
    _rate_tracker[access_key].append(now)

    update_key_usage(access_key)

    prompt = data.get("prompt", "")
    model = data.get("model")
    temperature = data.get("temperature", 0.0)

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    # AI Model Tier Enforcement
    user_plan = key_entry.get("plan", "monthly")

    # If no model specified, use user's preference or plan default
    if not model:
        model = key_entry.get("preferred_model") or get_default_model_for_plan(user_plan)

    # Check if model is allowed for user's plan
    if not is_model_allowed_for_plan(model, user_plan):
        allowed_models = PLAN_MODEL_ACCESS.get(user_plan, [])
        logger.warning(f"Model {model} not allowed for plan {user_plan}")
        return jsonify({
            "error": f"Model '{MODEL_DISPLAY_NAMES.get(model, model)}' not available on {user_plan.capitalize()} plan. Please upgrade or select an allowed model.",
            "allowed_models": allowed_models
        }), 403

    system_msg = "You are a knowledgeable academic assistant. Answer precisely and concisely."
    try:
        if model in CLAUDE_MODELS:
            ac = get_anthropic_client()
            response = ac.messages.create(
                model=model,
                max_tokens=1024,
                temperature=temperature,
                system=system_msg,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = response.content[0].text.strip()
        else:
            oai = get_openai_client()
            response = oai.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
            )
            answer = response.choices[0].message.content.strip()

        logger.info(f"Key={access_key[:8]}... | Model={model} | Answer={answer[:50]}")
        return jsonify({"answer": answer})

    except Exception as e:
        logger.error(f"API error ({model}): {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/validate", methods=["POST"])
def validate_key():
    data = request.get_json()
    if not data:
        return jsonify({"valid": False, "error": "No JSON body"}), 400

    access_key = data.get("access_key", "")
    key_entry = find_key(access_key)

    if not key_entry:
        return jsonify({"valid": False, "error": "Invalid access key"}), 403

    expiry_error = _check_key_expiry(key_entry)
    if expiry_error:
        return jsonify({"valid": False, "error": expiry_error}), 403

    logger.info(f"Key validated: {access_key[:8]}...")
    return jsonify({"valid": True})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "db": "postgres" if _use_db else "json"})


# ── Order Endpoints ───────────────────────────────────────────────

@app.route("/api/orders", methods=["POST"])
def create_order_endpoint():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    venmo_username = (data.get("venmo_username") or "").strip()
    transaction_id = (data.get("transaction_id") or "").strip()
    plan = (data.get("plan") or "").strip()
    referral = (data.get("referral") or "").strip()

    if not all([name, email, venmo_username, transaction_id, plan]):
        return jsonify({"error": "All fields are required"}), 400

    if plan not in PLAN_DURATIONS:
        return jsonify({"error": "Invalid plan. Choose 'monthly' or 'semester'"}), 400

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error": "Invalid email address"}), 400

    order = {
        "id": "order_" + secrets.token_hex(6),
        "name": name,
        "email": email,
        "venmo_username": venmo_username,
        "transaction_id": transaction_id,
        "plan": plan,
        "status": "pending",
        "created": datetime.utcnow().isoformat() + "Z",
        "approved_at": None,
        "key": None,
        "referral": referral,
    }

    create_order(order)
    send_admin_order_notification(order)

    logger.info(f"New order: {order['id']} | {name} | {plan}")
    return jsonify({"success": True, "message": "Order received! You'll get an email once payment is verified."})


@app.route("/api/orders/stripe", methods=["POST"])
def create_stripe_checkout():
    """Create Stripe Checkout Session for instant payment."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON body"}), 400

        # Validate required fields
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        plan = (data.get("plan") or "").lower()
        referral = (data.get("referral") or "").strip()

        if not name or not email:
            return jsonify({"error": "Name and email required"}), 400

        if plan not in PLAN_DURATIONS:
            return jsonify({"error": f"Invalid plan. Choose from: {list(PLAN_DURATIONS.keys())}"}), 400

        # Validate email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return jsonify({"error": "Invalid email format"}), 400

        # Create pending order first
        order = {
            "id": "order_" + secrets.token_hex(6),
            "name": name,
            "email": email,
            "plan": plan,
            "referral": referral,
            "payment_method": "stripe",
            "status": "pending",
            "created": datetime.utcnow().isoformat() + "Z",
        }
        order_id = create_order(order)

        # Create Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": STRIPE_PRICES[plan],
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{FRONTEND_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}#pricing",
            metadata={
                "order_id": order_id,
                "plan": plan,
                "mode": STRIPE_MODE
            },
            customer_email=email
        )

        # Update order with Stripe session ID
        update_order_stripe_session(order_id, session.id)

        logger.info(f"Stripe session created: {session.id} for order {order_id}")

        return jsonify({
            "session_url": session.url,
            "order_id": order_id
        })

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        return jsonify({"error": "Failed to create checkout session"}), 500
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        return jsonify({"error": "Failed to create checkout session"}), 500


@app.route("/api/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events for payment confirmation."""
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        notify_admin_error("webhook_signature_failed", str(e))
        return jsonify({"error": "Invalid signature"}), 400

    # Handle checkout.session.completed
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        # Verify mode matches (don't process test events in production)
        session_mode = session.get("livemode")
        expected_livemode = (STRIPE_MODE == "live")
        if session_mode != expected_livemode:
            logger.warning(f"Mode mismatch: session livemode={session_mode}, expected={expected_livemode}")
            return jsonify({"error": "Mode mismatch"}), 400

        # Extract order info from metadata
        order_id = session["metadata"].get("order_id")
        plan = session["metadata"].get("plan")

        if not order_id or not plan:
            logger.error(f"Missing metadata in session {session.id}")
            return jsonify({"error": "Missing metadata"}), 400

        # Find order
        order = find_order(order_id)
        if not order:
            logger.error(f"Order not found: {order_id}")
            return jsonify({"error": "Order not found"}), 404

        # Check if already approved (idempotency)
        if order["status"] == "approved":
            logger.info(f"Order {order_id} already approved, skipping")
            return jsonify({"status": "already_approved"}), 200

        # Validate payment amount matches plan
        expected_amount = PRICE_AMOUNTS[plan]
        actual_amount = session["amount_total"]
        if actual_amount != expected_amount:
            logger.error(f"Payment amount mismatch: expected {expected_amount}, got {actual_amount}")
            notify_admin_error("payment_amount_mismatch",
                             f"Order {order_id}: expected ${expected_amount/100}, got ${actual_amount/100}")
            return jsonify({"error": "Invalid payment amount"}), 400

        # Verify payment status
        if session["payment_status"] != "paid":
            logger.warning(f"Session {session.id} not paid: {session['payment_status']}")
            return jsonify({"error": "Payment not completed"}), 400

        # Generate access key
        key, key_entry = generate_key_with_expiry(order["name"], plan)

        # Update order status
        update_order_status(order_id, "approved", key)

        # Send key email (with retry on failure)
        try:
            send_key_email(order["email"], order["name"], key, plan, key_entry["expires"])
            logger.info(f"Key email sent for order {order_id}")
        except Exception as e:
            logger.error(f"Email failed for order {order_id}: {e}")
            # Add to retry queue
            add_to_email_retry_queue(
                order_id,
                "key_email",
                order["email"],
                {"key": key, "plan": plan, "name": order["name"], "expires": key_entry["expires"]}
            )

        logger.info(f"Order {order_id} auto-approved via Stripe webhook")
        return jsonify({"status": "approved"}), 200

    # Handle other event types if needed
    logger.info(f"Unhandled webhook event type: {event['type']}")
    return jsonify({"status": "unhandled_event"}), 200


@app.route("/api/config/stripe", methods=["GET"])
def get_stripe_config():
    """Provide Stripe publishable key to frontend."""
    return jsonify({
        "publishable_key": os.environ.get("STRIPE_PUBLISHABLE_KEY", ""),
        "mode": STRIPE_MODE
    })


@app.route("/api/model/preference", methods=["POST"])
def set_model_preference():
    """Save user's preferred AI model."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    access_key = data.get("access_key", "")
    preferred_model = data.get("model", "")

    if not access_key or not preferred_model:
        return jsonify({"error": "access_key and model required"}), 400

    # Validate key
    key_entry = find_key(access_key)
    if not key_entry:
        return jsonify({"error": "Invalid access key"}), 403

    # Check if model is allowed for user's plan
    user_plan = key_entry.get("plan", "monthly")
    if not is_model_allowed_for_plan(preferred_model, user_plan):
        return jsonify({
            "error": f"Model not available on your plan",
            "allowed_models": PLAN_MODEL_ACCESS.get(user_plan, [])
        }), 403

    # Save preference
    update_key_preference(access_key, preferred_model)
    logger.info(f"Model preference updated: {access_key[:8]}... -> {preferred_model}")

    return jsonify({
        "success": True,
        "preferred_model": preferred_model
    })


@app.route("/api/model/available", methods=["POST"])
def get_available_models():
    """Get list of models available for user's plan."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    access_key = data.get("access_key", "")
    if not access_key:
        return jsonify({"error": "access_key required"}), 400

    # Validate key
    key_entry = find_key(access_key)
    if not key_entry:
        return jsonify({"error": "Invalid access key"}), 403

    user_plan = key_entry.get("plan", "monthly")
    available_models = PLAN_MODEL_ACCESS.get(user_plan, [])

    return jsonify({
        "plan": user_plan,
        "available_models": available_models,
        "default_model": get_default_model_for_plan(user_plan),
        "preferred_model": key_entry.get("preferred_model"),
        "model_names": MODEL_DISPLAY_NAMES
    })


# ── Session Management Endpoints ──────────────────────────────────

@app.route("/api/session/start", methods=["POST"])
def start_session():
    """
    Start a new session for a key. If another session exists for this key,
    it will be terminated (one-device-at-a-time enforcement).
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    access_key = data.get("access_key", "")
    session_id = data.get("session_id", "")

    if not access_key or not session_id:
        return jsonify({"error": "access_key and session_id required"}), 400

    # Validate key
    key_entry = find_key(access_key)
    if not key_entry:
        return jsonify({"error": "Invalid access key"}), 403

    # Check expiry
    expiry_error = _check_key_expiry(key_entry)
    if expiry_error:
        return jsonify({"error": expiry_error}), 403

    # Create session (this will terminate any existing session)
    previous_session = create_session(access_key, session_id)

    logger.info(f"Session started: {session_id[:8]}... for key {access_key[:8]}...")

    return jsonify({
        "success": True,
        "session_id": session_id,
        "previous_session_terminated": previous_session is not None,
        "previous_session": previous_session
    })


@app.route("/api/session/heartbeat", methods=["POST"])
def session_heartbeat():
    """Update session heartbeat to keep it alive."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    session_id = data.get("session_id", "")
    if not session_id:
        return jsonify({"error": "session_id required"}), 400

    success = update_session_heartbeat(session_id)

    if not success:
        return jsonify({"error": "Session not found or expired"}), 404

    return jsonify({"success": True})


@app.route("/api/session/end", methods=["POST"])
def end_session_endpoint():
    """End a session."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    session_id = data.get("session_id", "")
    if not session_id:
        return jsonify({"error": "session_id required"}), 400

    success = end_session(session_id)

    return jsonify({"success": success})


@app.route("/api/session/status", methods=["POST"])
def session_status():
    """Check if there's an active session for a key."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    access_key = data.get("access_key", "")
    if not access_key:
        return jsonify({"error": "access_key required"}), 400

    session = get_active_session(access_key)

    if session:
        return jsonify({
            "active": True,
            "session": session
        })
    else:
        return jsonify({"active": False})


# ── Admin Endpoints ───────────────────────────────────────────────

@app.route("/api/admin/orders", methods=["GET"])
@require_admin
def list_orders_endpoint():
    status_filter = request.args.get("status")
    orders = list_orders(status_filter)
    return jsonify({"orders": orders})


@app.route("/api/admin/approve", methods=["POST"])
@require_admin
def approve_order():
    data = request.get_json()
    if not data or not data.get("order_id"):
        return jsonify({"error": "order_id required"}), 400

    order_id = data["order_id"]
    order = find_order(order_id)

    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "pending":
        return jsonify({"error": f"Order already {order['status']}"}), 400

    key, key_entry = generate_key_with_expiry(order["name"], order["plan"])
    update_order(order_id, "approved", key=key, approved_at=datetime.utcnow())

    email_sent = send_key_email(
        order["email"], order["name"], key, order["plan"], key_entry["expires"])

    logger.info(f"Approved order {order_id} | Key={key[:8]}... | Email={'sent' if email_sent else 'failed'}")
    return jsonify({
        "success": True,
        "key": key,
        "expires": key_entry["expires"],
        "email_sent": email_sent,
    })


@app.route("/api/admin/reject", methods=["POST"])
@require_admin
def reject_order():
    data = request.get_json()
    if not data or not data.get("order_id"):
        return jsonify({"error": "order_id required"}), 400

    order_id = data["order_id"]
    order = find_order(order_id)

    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "pending":
        return jsonify({"error": f"Order already {order['status']}"}), 400

    update_order(order_id, "rejected")
    logger.info(f"Rejected order {order_id}")
    return jsonify({"success": True})


@app.route("/api/admin/keys", methods=["GET"])
@require_admin
def list_keys_endpoint():
    return jsonify({"keys": list_keys()})


@app.route("/api/admin/keys", methods=["POST"])
@require_admin
def create_key():
    """Create a new access key."""
    data = request.get_json() or {}
    label = data.get("label")
    plan = data.get("plan", "monthly")
    if plan not in PLAN_DURATIONS:
        return jsonify({"error": f"Invalid plan. Choose from: {list(PLAN_DURATIONS.keys())}"}), 400
    key, entry = generate_key_with_expiry(label, plan)
    logger.info(f"Created key for '{label}' with plan '{plan}'")
    return jsonify({"key": key, **entry})


@app.route("/api/admin/revoke", methods=["POST"])
@require_admin
def revoke_key_endpoint():
    data = request.get_json()
    key_prefix = data.get("key_prefix", "") if data else ""
    if not key_prefix:
        return jsonify({"error": "key_prefix required (first 8 chars)"}), 400

    deleted = revoke_key(key_prefix)
    if deleted == 0:
        return jsonify({"error": "No matching key found"}), 404

    logger.info(f"Revoked {deleted} key(s) starting with {key_prefix}")
    return jsonify({"success": True})


@app.route("/api/admin/sync-stripe", methods=["POST"])
@require_admin
def sync_stripe_order():
    """
    Manually sync a pending Stripe order by fetching session status.
    Used when webhook fails to process.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON body"}), 400

        order_id = data.get("order_id")
        if not order_id:
            return jsonify({"error": "order_id required"}), 400

        order = find_order(order_id)
        if not order:
            return jsonify({"error": "Order not found"}), 404

        if order.get("payment_method") != "stripe":
            return jsonify({"error": "Not a Stripe order"}), 400

        stripe_session_id = order.get("stripe_session_id")
        if not stripe_session_id:
            return jsonify({"error": "No Stripe session ID"}), 400

        # Fetch session from Stripe
        session = stripe.checkout.Session.retrieve(stripe_session_id)

        # Check payment status
        if session.payment_status == "paid" and order["status"] != "approved":
            # Validate payment amount
            plan = order["plan"]
            expected_amount = PRICE_AMOUNTS.get(plan)
            if not expected_amount or session.amount_total != expected_amount:
                return jsonify({"error": "Payment amount mismatch"}), 400

            # Approve order
            key, key_entry = generate_key_with_expiry(order["name"], plan)
            update_order_status(order_id, "approved", key)

            # Send key email
            try:
                send_key_email(order["email"], order["name"], key, plan, key_entry["expires"])
            except Exception as e:
                logger.error(f"Email failed during sync: {e}")
                # Add to retry queue
                add_to_email_retry_queue(
                    order_id,
                    "key_email",
                    order["email"],
                    {"key": key, "plan": plan, "name": order["name"], "expires": key_entry["expires"]}
                )

            logger.info(f"Order {order_id} manually synced and approved")
            return jsonify({
                "success": True,
                "message": "Order approved successfully",
                "key": key
            })
        elif session.payment_status == "paid":
            return jsonify({
                "success": True,
                "message": "Order already approved",
                "status": order["status"]
            })
        else:
            return jsonify({
                "success": False,
                "message": f"Payment not completed: {session.payment_status}",
                "payment_status": session.payment_status
            })

    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error: {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"Sync error: {e}")
        return jsonify({"error": "Failed to sync order"}), 500


# ── Startup ───────────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
