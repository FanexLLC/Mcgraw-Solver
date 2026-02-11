import os
import json
import logging
import secrets
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import requests as http_requests

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting: max requests per key per hour
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "120"))
RATE_WINDOW = 3600  # 1 hour in seconds

# In-memory rate limit tracker: {key: [timestamp, timestamp, ...]}
_rate_tracker = defaultdict(list)

# CORS — allow GitHub Pages and localhost for development
CORS(app, origins=[
    "https://fanexllc.github.io",
    "http://localhost:*",
    "http://127.0.0.1:*",
])

# Config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
DOWNLOAD_URL = os.environ.get("DOWNLOAD_URL", "")

# EmailJS config
EMAILJS_SERVICE_ID = os.environ.get("EMAILJS_SERVICE_ID", "")
EMAILJS_TEMPLATE_ID = os.environ.get("EMAILJS_TEMPLATE_ID", "")
EMAILJS_PUBLIC_KEY = os.environ.get("EMAILJS_PUBLIC_KEY", "")
EMAILJS_PRIVATE_KEY = os.environ.get("EMAILJS_PRIVATE_KEY", "")

client = None

# File paths
KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys.json")
ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")

PLAN_DURATIONS = {"monthly": 30, "semester": 120}

# --------------- Helpers ---------------


def load_keys():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            return json.load(f)
    return {"keys": []}


def save_keys(data):
    with open(KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_orders():
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE) as f:
            return json.load(f)
    return {"orders": []}


def save_orders(data):
    with open(ORDERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_client():
    global client
    if client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not set on server")
        client = OpenAI(api_key=OPENAI_API_KEY)
    return client


def generate_key_with_expiry(label, plan):
    """Generate a new access key with expiration based on plan."""
    key = secrets.token_hex(16)
    now = datetime.utcnow()
    entry = {
        "key": key,
        "label": label,
        "plan": plan,
        "created": now.isoformat() + "Z",
        "expires": (now + timedelta(days=PLAN_DURATIONS[plan])).isoformat() + "Z",
    }
    keys_data = load_keys()
    keys_data["keys"].append(entry)
    save_keys(keys_data)
    return key, entry


def send_key_email(email, name, key, plan, expiry_date):
    """Send access key email via EmailJS."""
    if not all([EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, EMAILJS_PUBLIC_KEY]):
        logger.warning("EmailJS not configured, skipping email")
        return False
    try:
        resp = http_requests.post(
            "https://api.emailjs.com/api/v1.0/email/send",
            json={
                "service_id": EMAILJS_SERVICE_ID,
                "template_id": EMAILJS_TEMPLATE_ID,
                "user_id": EMAILJS_PUBLIC_KEY,
                "accessToken": EMAILJS_PRIVATE_KEY,
                "template_params": {
                    "to_email": email,
                    "to_name": name,
                    "access_key": key,
                    "plan": "Monthly ($20)" if plan == "monthly" else "Semester ($50)",
                    "expiry_date": expiry_date,
                    "download_url": DOWNLOAD_URL,
                },
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"Email sent to {email}")
            return True
        logger.error(f"EmailJS error: {resp.status_code} {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def require_admin(f):
    """Decorator to require admin password in X-Admin-Password header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        password = request.headers.get("X-Admin-Password", "")
        if not ADMIN_PASSWORD or password != ADMIN_PASSWORD:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# --------------- Existing Endpoints ---------------


@app.route("/api/solve", methods=["POST"])
def solve():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    # Validate access key
    access_key = data.get("access_key", "")
    keys_data = load_keys()

    key_entry = next((k for k in keys_data.get("keys", []) if k["key"] == access_key), None)
    if not key_entry:
        return jsonify({"error": "Invalid access key"}), 403

    # Check expiration
    if "expires" in key_entry:
        expiry = datetime.fromisoformat(key_entry["expires"].rstrip("Z"))
        if datetime.utcnow() > expiry:
            return jsonify({"error": "Access key expired. Please renew your subscription."}), 403

    # Rate limiting
    now = time.time()
    window_start = now - RATE_WINDOW
    _rate_tracker[access_key] = [t for t in _rate_tracker[access_key] if t > window_start]
    if len(_rate_tracker[access_key]) >= RATE_LIMIT:
        logger.warning(f"Rate limit hit for key={access_key[:8]}...")
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
    _rate_tracker[access_key].append(now)

    # Track usage on the key entry
    key_entry["total_requests"] = key_entry.get("total_requests", 0) + 1
    key_entry["last_used"] = datetime.utcnow().isoformat() + "Z"
    save_keys(keys_data)

    # Extract question data
    prompt = data.get("prompt", "")
    model = data.get("model", "gpt-4o")
    temperature = data.get("temperature", 0.0)

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    # Call OpenAI
    try:
        oai = get_client()
        response = oai.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": "You are a knowledgeable academic assistant. Answer precisely and concisely."},
                {"role": "user", "content": prompt},
            ],
        )
        answer = response.choices[0].message.content.strip()
        logger.info(f"Key={access_key[:8]}... | Model={model} | Answer={answer[:50]}")
        return jsonify({"answer": answer})

    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# --------------- Order Endpoints ---------------


@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    venmo_username = (data.get("venmo_username") or "").strip()
    transaction_id = (data.get("transaction_id") or "").strip()
    plan = (data.get("plan") or "").strip()

    # Validate required fields
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
    }

    orders_data = load_orders()
    orders_data["orders"].append(order)
    save_orders(orders_data)

    logger.info(f"New order: {order['id']} | {name} | {plan}")
    return jsonify({"success": True, "message": "Order received! You'll get an email once payment is verified."})


# --------------- Admin Endpoints ---------------


@app.route("/api/admin/orders", methods=["GET"])
@require_admin
def list_orders():
    orders_data = load_orders()
    status_filter = request.args.get("status")
    orders = orders_data.get("orders", [])
    if status_filter:
        orders = [o for o in orders if o["status"] == status_filter]
    return jsonify({"orders": orders})


@app.route("/api/admin/approve", methods=["POST"])
@require_admin
def approve_order():
    data = request.get_json()
    if not data or not data.get("order_id"):
        return jsonify({"error": "order_id required"}), 400

    order_id = data["order_id"]
    orders_data = load_orders()
    order = next((o for o in orders_data["orders"] if o["id"] == order_id), None)

    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "pending":
        return jsonify({"error": f"Order already {order['status']}"}), 400

    # Generate key with expiration
    key, key_entry = generate_key_with_expiry(order["name"], order["plan"])

    # Update order
    order["status"] = "approved"
    order["approved_at"] = datetime.utcnow().isoformat() + "Z"
    order["key"] = key
    save_orders(orders_data)

    # Send email
    email_sent = send_key_email(
        order["email"],
        order["name"],
        key,
        order["plan"],
        key_entry["expires"],
    )

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
    orders_data = load_orders()
    order = next((o for o in orders_data["orders"] if o["id"] == order_id), None)

    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "pending":
        return jsonify({"error": f"Order already {order['status']}"}), 400

    order["status"] = "rejected"
    save_orders(orders_data)

    logger.info(f"Rejected order {order_id}")
    return jsonify({"success": True})


@app.route("/api/admin/keys", methods=["GET"])
@require_admin
def list_keys():
    """List all keys with usage stats."""
    keys_data = load_keys()
    summary = []
    for k in keys_data.get("keys", []):
        summary.append({
            "key": k["key"][:8] + "...",
            "label": k.get("label", ""),
            "plan": k.get("plan", "none"),
            "expires": k.get("expires"),
            "total_requests": k.get("total_requests", 0),
            "last_used": k.get("last_used"),
        })
    return jsonify({"keys": summary})


@app.route("/api/admin/revoke", methods=["POST"])
@require_admin
def revoke_key():
    """Revoke (delete) an access key."""
    data = request.get_json()
    key_prefix = data.get("key_prefix", "") if data else ""
    if not key_prefix:
        return jsonify({"error": "key_prefix required (first 8 chars)"}), 400

    keys_data = load_keys()
    original_count = len(keys_data["keys"])
    keys_data["keys"] = [k for k in keys_data["keys"] if not k["key"].startswith(key_prefix)]

    if len(keys_data["keys"]) == original_count:
        return jsonify({"error": "No matching key found"}), 404

    save_keys(keys_data)
    logger.info(f"Revoked key starting with {key_prefix}")
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
