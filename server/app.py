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

from db import (
    init_db, find_key, update_key_usage, generate_key_with_expiry,
    list_keys, revoke_key, create_order, list_orders, find_order,
    update_order, PLAN_DURATIONS, _use_db,
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

CLAUDE_MODELS = {"claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001",
                 "claude-sonnet-4-5", "claude-haiku-4-5"}

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
    model = data.get("model", "gpt-4o")
    temperature = data.get("temperature", 0.0)

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

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


# ── Startup ───────────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
