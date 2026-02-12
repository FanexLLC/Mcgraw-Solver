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
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# EmailJS config
EMAILJS_SERVICE_ID = os.environ.get("EMAILJS_SERVICE_ID", "")
EMAILJS_TEMPLATE_ID = os.environ.get("EMAILJS_TEMPLATE_ID", "")
EMAILJS_ADMIN_TEMPLATE_ID = os.environ.get("EMAILJS_ADMIN_TEMPLATE_ID", "")
EMAILJS_PUBLIC_KEY = os.environ.get("EMAILJS_PUBLIC_KEY", "")
EMAILJS_PRIVATE_KEY = os.environ.get("EMAILJS_PRIVATE_KEY", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

client = None

# File paths (fallback for local dev without DATABASE_URL)
KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys.json")
ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")

PLAN_DURATIONS = {"monthly": 30, "semester": 120}

# --------------- Database ---------------

_use_db = bool(DATABASE_URL)


def get_db():
    """Get a PostgreSQL connection."""
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def init_db():
    """Create tables if they don't exist, seed from keys.json."""
    if not _use_db:
        logger.info("No DATABASE_URL set, using JSON files")
        return

    import psycopg2
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            label TEXT,
            plan TEXT,
            created TIMESTAMP,
            expires TIMESTAMP,
            total_requests INTEGER DEFAULT 0,
            last_used TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT,
            venmo_username TEXT,
            transaction_id TEXT,
            plan TEXT,
            status TEXT DEFAULT 'pending',
            created TIMESTAMP,
            approved_at TIMESTAMP,
            key TEXT
        )
    """)

    # Seed from keys.json if DB is empty
    cur.execute("SELECT COUNT(*) FROM keys")
    count = cur.fetchone()[0]
    if count == 0 and os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE) as f:
                data = json.load(f)
            for k in data.get("keys", []):
                created = None
                expires = None
                if k.get("created"):
                    created = datetime.fromisoformat(k["created"].rstrip("Z"))
                if k.get("expires"):
                    expires = datetime.fromisoformat(k["expires"].rstrip("Z"))
                cur.execute(
                    "INSERT INTO keys (key, label, plan, created, expires, total_requests) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (key) DO NOTHING",
                    (k["key"], k.get("label"), k.get("plan"), created, expires,
                     k.get("total_requests", 0))
                )
            logger.info(f"Seeded {len(data.get('keys', []))} keys from keys.json")
        except Exception as e:
            logger.error(f"Failed to seed keys: {e}")

    # Seed from orders.json if DB is empty
    cur.execute("SELECT COUNT(*) FROM orders")
    count = cur.fetchone()[0]
    if count == 0 and os.path.exists(ORDERS_FILE):
        try:
            with open(ORDERS_FILE) as f:
                data = json.load(f)
            for o in data.get("orders", []):
                created = None
                approved_at = None
                if o.get("created"):
                    created = datetime.fromisoformat(o["created"].rstrip("Z"))
                if o.get("approved_at"):
                    approved_at = datetime.fromisoformat(o["approved_at"].rstrip("Z"))
                cur.execute(
                    "INSERT INTO orders (id, name, email, venmo_username, transaction_id, "
                    "plan, status, created, approved_at, key) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                    (o["id"], o.get("name"), o.get("email"), o.get("venmo_username"),
                     o.get("transaction_id"), o.get("plan"), o.get("status", "pending"),
                     created, approved_at, o.get("key"))
                )
            logger.info(f"Seeded {len(data.get('orders', []))} orders from orders.json")
        except Exception as e:
            logger.error(f"Failed to seed orders: {e}")

    cur.close()
    conn.close()
    logger.info("Database initialized")


# --------------- JSON Fallback Helpers (local dev) ---------------


def _load_keys_json():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            return json.load(f)
    return {"keys": []}


def _save_keys_json(data):
    with open(KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _load_orders_json():
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE) as f:
            return json.load(f)
    return {"orders": []}


def _save_orders_json(data):
    with open(ORDERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# --------------- Key Operations ---------------


def db_find_key(access_key):
    """Find a key entry. Returns dict or None."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT key, label, plan, created, expires, total_requests, last_used "
                     "FROM keys WHERE key = %s", (access_key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {
            "key": row[0], "label": row[1], "plan": row[2],
            "created": row[3].isoformat() + "Z" if row[3] else None,
            "expires": row[4].isoformat() + "Z" if row[4] else None,
            "total_requests": row[5] or 0, "last_used": row[6],
        }
    else:
        keys_data = _load_keys_json()
        return next((k for k in keys_data.get("keys", []) if k["key"] == access_key), None)


def db_update_key_usage(access_key):
    """Increment total_requests and update last_used."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE keys SET total_requests = total_requests + 1, last_used = %s WHERE key = %s",
            (datetime.utcnow(), access_key))
        cur.close()
        conn.close()
    else:
        keys_data = _load_keys_json()
        for k in keys_data.get("keys", []):
            if k["key"] == access_key:
                k["total_requests"] = k.get("total_requests", 0) + 1
                k["last_used"] = datetime.utcnow().isoformat() + "Z"
                break
        _save_keys_json(keys_data)


def db_create_key(key, label, plan, created, expires):
    """Insert a new key."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO keys (key, label, plan, created, expires) VALUES (%s, %s, %s, %s, %s)",
            (key, label, plan, created, expires))
        cur.close()
        conn.close()
    else:
        keys_data = _load_keys_json()
        keys_data["keys"].append({
            "key": key, "label": label, "plan": plan,
            "created": created.isoformat() + "Z",
            "expires": expires.isoformat() + "Z",
        })
        _save_keys_json(keys_data)


def db_list_keys():
    """List all keys with usage stats."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT key, label, plan, expires, total_requests, last_used FROM keys")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{
            "key": r[0][:8] + "...", "label": r[1] or "", "plan": r[2] or "none",
            "expires": r[3].isoformat() + "Z" if r[3] else None,
            "total_requests": r[4] or 0,
            "last_used": r[5].isoformat() + "Z" if r[5] else None,
        } for r in rows]
    else:
        keys_data = _load_keys_json()
        return [{
            "key": k["key"][:8] + "...", "label": k.get("label", ""),
            "plan": k.get("plan", "none"), "expires": k.get("expires"),
            "total_requests": k.get("total_requests", 0),
            "last_used": k.get("last_used"),
        } for k in keys_data.get("keys", [])]


def db_revoke_key(key_prefix):
    """Delete keys matching prefix. Returns number deleted."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM keys WHERE key LIKE %s", (key_prefix + "%",))
        deleted = cur.rowcount
        cur.close()
        conn.close()
        return deleted
    else:
        keys_data = _load_keys_json()
        original = len(keys_data["keys"])
        keys_data["keys"] = [k for k in keys_data["keys"]
                              if not k["key"].startswith(key_prefix)]
        _save_keys_json(keys_data)
        return original - len(keys_data["keys"])


# --------------- Order Operations ---------------


def db_create_order(order):
    """Insert a new order."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (id, name, email, venmo_username, transaction_id, plan, status, created) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (order["id"], order["name"], order["email"], order["venmo_username"],
             order["transaction_id"], order["plan"], order["status"],
             datetime.fromisoformat(order["created"].rstrip("Z"))))
        cur.close()
        conn.close()
    else:
        orders_data = _load_orders_json()
        orders_data["orders"].append(order)
        _save_orders_json(orders_data)


def db_list_orders(status_filter=None):
    """List orders, optionally filtered by status."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        if status_filter:
            cur.execute(
                "SELECT id, name, email, venmo_username, transaction_id, plan, status, "
                "created, approved_at, key FROM orders WHERE status = %s ORDER BY created DESC",
                (status_filter,))
        else:
            cur.execute(
                "SELECT id, name, email, venmo_username, transaction_id, plan, status, "
                "created, approved_at, key FROM orders ORDER BY created DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{
            "id": r[0], "name": r[1], "email": r[2], "venmo_username": r[3],
            "transaction_id": r[4], "plan": r[5], "status": r[6],
            "created": r[7].isoformat() + "Z" if r[7] else None,
            "approved_at": r[8].isoformat() + "Z" if r[8] else None,
            "key": r[9],
        } for r in rows]
    else:
        orders_data = _load_orders_json()
        orders = orders_data.get("orders", [])
        if status_filter:
            orders = [o for o in orders if o["status"] == status_filter]
        return orders


def db_find_order(order_id):
    """Find an order by ID."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, email, venmo_username, transaction_id, plan, status, "
            "created, approved_at, key FROM orders WHERE id = %s", (order_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0], "name": row[1], "email": row[2], "venmo_username": row[3],
            "transaction_id": row[4], "plan": row[5], "status": row[6],
            "created": row[7].isoformat() + "Z" if row[7] else None,
            "approved_at": row[8].isoformat() + "Z" if row[8] else None,
            "key": row[9],
        }
    else:
        orders_data = _load_orders_json()
        return next((o for o in orders_data["orders"] if o["id"] == order_id), None)


def db_update_order(order_id, status, key=None, approved_at=None):
    """Update an order's status."""
    if _use_db:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE orders SET status = %s, key = %s, approved_at = %s WHERE id = %s",
            (status, key, approved_at, order_id))
        cur.close()
        conn.close()
    else:
        orders_data = _load_orders_json()
        for o in orders_data["orders"]:
            if o["id"] == order_id:
                o["status"] = status
                if key:
                    o["key"] = key
                if approved_at:
                    o["approved_at"] = approved_at.isoformat() + "Z"
                break
        _save_orders_json(orders_data)


# --------------- Other Helpers ---------------


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
    expires = now + timedelta(days=PLAN_DURATIONS[plan])
    db_create_key(key, label, plan, now, expires)
    return key, {"key": key, "expires": expires.isoformat() + "Z"}


def send_key_email(email, name, key, plan, expiry_date):
    """Send access key email via EmailJS."""
    # Format expiry date as "June 11, 2026" instead of raw ISO
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


def send_admin_order_notification(order):
    """Send admin an email when a new order is placed."""
    if not all([EMAILJS_SERVICE_ID, EMAILJS_ADMIN_TEMPLATE_ID, EMAILJS_PUBLIC_KEY, ADMIN_EMAIL]):
        logger.warning("Admin notification not configured, skipping")
        return False
    plan_display = "Monthly ($20)" if order["plan"] == "monthly" else "Semester ($50)"
    try:
        resp = http_requests.post(
            "https://api.emailjs.com/api/v1.0/email/send",
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


def require_admin(f):
    """Decorator to require admin password in X-Admin-Password header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        password = request.headers.get("X-Admin-Password", "")
        if not ADMIN_PASSWORD or password != ADMIN_PASSWORD:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# --------------- Endpoints ---------------


@app.route("/api/solve", methods=["POST"])
def solve():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    # Validate access key
    access_key = data.get("access_key", "")
    key_entry = db_find_key(access_key)
    if not key_entry:
        return jsonify({"error": "Invalid access key"}), 403

    # Check expiration
    if key_entry.get("expires"):
        expiry_str = key_entry["expires"]
        if isinstance(expiry_str, str):
            expiry = datetime.fromisoformat(expiry_str.rstrip("Z"))
        else:
            expiry = expiry_str
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

    # Track usage
    db_update_key_usage(access_key)

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


@app.route("/api/validate", methods=["POST"])
def validate_key():
    data = request.get_json()
    if not data:
        return jsonify({"valid": False, "error": "No JSON body"}), 400

    access_key = data.get("access_key", "")
    key_entry = db_find_key(access_key)

    if not key_entry:
        return jsonify({"valid": False, "error": "Invalid access key"}), 403

    # Check expiration
    if key_entry.get("expires"):
        expiry_str = key_entry["expires"]
        if isinstance(expiry_str, str):
            expiry = datetime.fromisoformat(expiry_str.rstrip("Z"))
        else:
            expiry = expiry_str
        if datetime.utcnow() > expiry:
            return jsonify({"valid": False, "error": "Access key expired. Please renew your subscription."}), 403

    logger.info(f"Key validated: {access_key[:8]}...")
    return jsonify({"valid": True})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "db": "postgres" if _use_db else "json"})


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

    db_create_order(order)

    # Notify admin about the new order
    send_admin_order_notification(order)

    logger.info(f"New order: {order['id']} | {name} | {plan}")
    return jsonify({"success": True, "message": "Order received! You'll get an email once payment is verified."})


# --------------- Admin Endpoints ---------------


@app.route("/api/admin/orders", methods=["GET"])
@require_admin
def list_orders():
    status_filter = request.args.get("status")
    orders = db_list_orders(status_filter)
    return jsonify({"orders": orders})


@app.route("/api/admin/approve", methods=["POST"])
@require_admin
def approve_order():
    data = request.get_json()
    if not data or not data.get("order_id"):
        return jsonify({"error": "order_id required"}), 400

    order_id = data["order_id"]
    order = db_find_order(order_id)

    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "pending":
        return jsonify({"error": f"Order already {order['status']}"}), 400

    # Generate key with expiration
    key, key_entry = generate_key_with_expiry(order["name"], order["plan"])

    # Update order
    db_update_order(order_id, "approved", key=key, approved_at=datetime.utcnow())

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
    order = db_find_order(order_id)

    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order["status"] != "pending":
        return jsonify({"error": f"Order already {order['status']}"}), 400

    db_update_order(order_id, "rejected")

    logger.info(f"Rejected order {order_id}")
    return jsonify({"success": True})


@app.route("/api/admin/keys", methods=["GET"])
@require_admin
def list_keys():
    """List all keys with usage stats."""
    return jsonify({"keys": db_list_keys()})


@app.route("/api/admin/revoke", methods=["POST"])
@require_admin
def revoke_key():
    """Revoke (delete) an access key."""
    data = request.get_json()
    key_prefix = data.get("key_prefix", "") if data else ""
    if not key_prefix:
        return jsonify({"error": "key_prefix required (first 8 chars)"}), 400

    deleted = db_revoke_key(key_prefix)
    if deleted == 0:
        return jsonify({"error": "No matching key found"}), 404

    logger.info(f"Revoked {deleted} key(s) starting with {key_prefix}")
    return jsonify({"success": True})


# --------------- Startup ---------------

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
