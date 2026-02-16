# McGraw Solver - Feature Implementation Plan (CTO APPROVED)

# user note: cron jobs need to still be completed.

## Context

This plan outlines the implementation of critical business features to improve payment processing, pricing structure, and user experience for the McGraw Solver SmartBook automation tool. The current system uses manual Venmo-only payments with admin approval, limiting growth and creating operational bottlenecks. This plan adds automated payment processing, tiered pricing with AI model differentiation, and better user feedback during automation.

**Current State:**
- Payment: Venmo-only with manual verification and approval by admin
- Pricing: 2 plans (Monthly $20/30 days, Semester $50/120 days)
- Email: EmailJS sends notifications on order submission and approval
- GUI: tkinter application with human-like delays (8-28s per question) but no visual progress feedback
- AI Model: Hardcoded to Claude Sonnet 4.5 for all users

**Goals:**
1. Add instant payment processing via Stripe alongside manual Venmo option
2. Introduce tiered pricing (Weekly/Monthly/Semester) with updated rates
3. Create AI model tiers (GPT-4o-mini for weekly, GPT-4o for monthly, Claude Sonnet for semester)
4. Improve user experience with loading indicators during automation
5. Enhance plan descriptions to communicate value proposition
6. **NEW:** Implement one-device-at-a-time session management
7. **NEW:** Add admin security enhancements

---

## Feature 1: Dual Payment System (Stripe + Venmo)

### Overview
Add Stripe as an automated payment option while keeping Venmo for users who prefer it. Stripe orders auto-approve via webhooks, Venmo orders continue manual admin approval flow.

### Edge Cases & Decisions
- **Abandoned orders**: Manual cleanup only (no auto-deletion)
- **Duplicate purchases**: Allow multiple keys per user (useful for sharing)
- **Email failures**: Implement retry mechanism for failed key emails
- **Webhook failures**: Add "Sync from Stripe" button in admin panel for manual recovery
- **Admin notifications**: Only send emails for Venmo orders (not Stripe)
- **Refunds**: No refunds policy enforced in Stripe dashboard settings
- **Payment validation**: Verify payment amount matches plan to prevent tampering
- **Cancelled sessions**: Orders remain pending, admin cleanup manual

### Implementation Steps

#### 1.1 Database Migration
**File:** `c:\Users\PC\Mcgraw-Solver\server\db.py`

**Changes:**
- Add `payment_method` column (TEXT, default 'venmo') to orders table
- Add `stripe_session_id` column (TEXT, nullable) to orders table
- **NEW:** Add `preferred_model` column to keys table
- **NEW:** Create `email_retry_queue` table for failed email retries
- **NEW:** Create `active_sessions` table for one-device-at-a-time enforcement
- Update `PLAN_DURATIONS` to add weekly plan:
  ```python
  PLAN_DURATIONS = {
      "weekly": 7,
      "monthly": 30,
      "semester": 120
  }
  ```

**New Helper Functions:**
```python
def find_order_by_stripe_session(session_id):
    """Find order by Stripe session ID."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE stripe_session_id = %s", (session_id,))
    order = cur.fetchone()
    cur.close()
    return order

def update_key_preference(access_key, preferred_model):
    """Save user's preferred AI model."""
    cur = conn.cursor()
    cur.execute("UPDATE keys SET preferred_model = %s WHERE key = %s",
                (preferred_model, access_key))
    conn.commit()
    cur.close()

def add_to_email_retry_queue(order_id, email_type, recipient, template_params):
    """Add failed email to retry queue."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO email_retry_queue (order_id, email_type, recipient, template_params, created)
        VALUES (%s, %s, %s, %s, NOW())
    """, (order_id, email_type, recipient, json.dumps(template_params)))
    conn.commit()
    cur.close()
```

**Update existing functions:**
- `create_order()`: Accept `payment_method` and `stripe_session_id` parameters
- `list_orders()` and `find_order()`: Return new fields

#### 1.2 Migration Script
**NEW FILE:** `c:\Users\PC\Mcgraw-Solver\server\migrate.py`

```python
"""
Database migration script for Stripe integration and new features.
Run this before deploying the updated application.
"""
import os
import psycopg2
from datetime import datetime

def run_migration():
    """Execute database migrations."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    migrations = [
        """
        -- Migration v1: Stripe Support and Session Management
        -- Add Stripe columns to orders
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method TEXT DEFAULT 'venmo';
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS stripe_session_id TEXT;

        -- Add model preference to keys
        ALTER TABLE keys ADD COLUMN IF NOT EXISTS preferred_model TEXT;

        -- Email retry queue for failed email delivery
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

        -- Active sessions for one-device-at-a-time enforcement
        CREATE TABLE IF NOT EXISTS active_sessions (
            id SERIAL PRIMARY KEY,
            access_key TEXT NOT NULL,
            session_id TEXT UNIQUE NOT NULL,
            started_at TIMESTAMP DEFAULT NOW(),
            last_heartbeat TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (access_key) REFERENCES keys(key) ON DELETE CASCADE
        );

        -- Index for session cleanup queries
        CREATE INDEX IF NOT EXISTS idx_sessions_heartbeat ON active_sessions(last_heartbeat);
        CREATE INDEX IF NOT EXISTS idx_sessions_key ON active_sessions(access_key);

        -- Index for Stripe session lookups
        CREATE INDEX IF NOT EXISTS idx_orders_stripe_session ON orders(stripe_session_id);
        """,
    ]

    for i, migration in enumerate(migrations):
        try:
            print(f"Running migration {i+1}...")
            cur.execute(migration)
            conn.commit()
            print(f"✓ Migration {i+1} completed at {datetime.now()}")
        except Exception as e:
            conn.rollback()
            print(f"✗ Migration {i+1} failed: {e}")
            raise

    cur.close()
    conn.close()
    print("\n✓ All migrations completed successfully!")

if __name__ == "__main__":
    run_migration()
```

**Deployment Instructions:**
1. Run locally first: `python server/migrate.py` (using production DATABASE_URL)
2. Verify all tables created successfully
3. Check existing data integrity
4. Deploy application code

#### 1.3 Stripe Price Objects Setup
**NEW SECTION:** Before implementing Stripe integration, create Price objects in Stripe Dashboard.

**Stripe Dashboard Setup:**
1. Go to Stripe Dashboard → Products → Create product
2. Create three products with prices:
   - **Weekly Plan**: $10.00 USD one-time payment
   - **Monthly Plan**: $25.00 USD one-time payment
   - **Semester Plan**: $50.00 USD one-time payment
3. Copy Price IDs (format: `price_xxxxxxxxxxxxx`)
4. Add to environment variables:
   ```bash
   STRIPE_PRICE_WEEKLY=price_xxxxxxxxxxxxx
   STRIPE_PRICE_MONTHLY=price_xxxxxxxxxxxxx
   STRIPE_PRICE_SEMESTER=price_xxxxxxxxxxxxx
   ```

**Why Price Objects?**
- Better Stripe analytics and revenue tracking
- Price changes don't require code deployment
- Proper product catalog in Stripe dashboard
- Easier to add promotions/coupons later

#### 1.4 Backend Stripe Integration
**File:** `c:\Users\PC\Mcgraw-Solver\server\requirements.txt`
- Add dependency: `stripe>=7.0.0`

**File:** `c:\Users\PC\Mcgraw-Solver\server\app.py`

**Environment Variables (add to Railway/production):**
```bash
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_WEEKLY=price_...
STRIPE_PRICE_MONTHLY=price_...
STRIPE_PRICE_SEMESTER=price_...
STRIPE_MODE=live  # or 'test' for development
FRONTEND_URL=https://fanexllc.github.io
```

**New Code:**
```python
import stripe
import os
import logging

# Initialize Stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_MODE = os.environ.get("STRIPE_MODE", "test")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# Map plans to Stripe Price IDs
STRIPE_PRICES = {
    "weekly": os.environ.get("STRIPE_PRICE_WEEKLY"),
    "monthly": os.environ.get("STRIPE_PRICE_MONTHLY"),
    "semester": os.environ.get("STRIPE_PRICE_SEMESTER")
}

# Price amounts for validation (in cents)
PRICE_AMOUNTS = {
    "weekly": 1000,    # $10.00
    "monthly": 2500,   # $25.00
    "semester": 5000   # $50.00
}

def notify_admin_error(error_type, details):
    """Send admin email for critical errors."""
    if error_type in ["webhook_signature_failed", "payment_amount_mismatch", "email_retry_exhausted"]:
        admin_email = os.environ.get("ADMIN_EMAIL")
        send_email(admin_email, f"🚨 Critical Error: {error_type}", details)
        logger.error(f"Admin notified: {error_type} - {details}")
```

**New Endpoint 1: `POST /api/orders/stripe`**
```python
@app.route("/api/orders/stripe", methods=["POST"])
def create_stripe_checkout():
    """Create Stripe Checkout Session for instant payment."""
    try:
        data = request.get_json()

        # Validate required fields
        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        plan = data.get("plan", "").lower()
        referral = data.get("referral", "").strip()

        if not name or not email:
            return jsonify({"error": "Name and email required"}), 400

        if plan not in ["weekly", "monthly", "semester"]:
            return jsonify({"error": "Invalid plan"}), 400

        # Validate email format
        import re
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return jsonify({"error": "Invalid email format"}), 400

        # Create pending order first
        order_id = create_order(
            name=name,
            email=email,
            plan=plan,
            referral=referral,
            payment_method="stripe"
        )

        # Create Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": STRIPE_PRICES[plan],
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/#pricing",
            metadata={
                "order_id": order_id,
                "plan": plan,
                "mode": STRIPE_MODE
            },
            customer_email=email
        )

        # Update order with Stripe session ID
        update_order(order_id, {"stripe_session_id": session.id})

        logger.info(f"Stripe session created: {session.id} for order {order_id}")

        return jsonify({
            "session_url": session.url,
            "order_id": order_id
        })

    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        return jsonify({"error": "Failed to create checkout session"}), 500
```

**New Endpoint 2: `POST /api/stripe/webhook`**
```python
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

        # **NEW: Validate payment amount matches plan**
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
        key = generate_key_with_expiry(order["name"], plan)

        # Update order status
        update_order_status(order_id, "approved", key)

        # Send key email (with retry on failure)
        try:
            send_key_email(order["email"], key, plan, order["name"])
            logger.info(f"Key email sent for order {order_id}")
        except Exception as e:
            logger.error(f"Email failed for order {order_id}: {e}")
            # Add to retry queue
            add_to_email_retry_queue(
                order_id,
                "key_email",
                order["email"],
                {"key": key, "plan": plan, "name": order["name"]}
            )

        logger.info(f"Order {order_id} auto-approved via Stripe webhook")
        return jsonify({"status": "approved"}), 200

    # Handle other event types if needed
    return jsonify({"status": "unhandled_event"}), 200
```

**New Endpoint 3: `GET /api/config/stripe`**
```python
@app.route("/api/config/stripe", methods=["GET"])
def get_stripe_config():
    """Provide Stripe publishable key to frontend."""
    return jsonify({
        "publishable_key": os.environ.get("STRIPE_PUBLISHABLE_KEY"),
        "mode": STRIPE_MODE
    })
```

**New Endpoint 4: `POST /api/admin/sync-stripe`**
```python
@app.route("/api/admin/sync-stripe", methods=["POST"])
@require_admin_auth  # Add admin authentication decorator
def sync_stripe_order():
    """
    Manually sync a pending Stripe order by fetching session status.
    Used when webhook fails to process.
    """
    try:
        data = request.get_json()
        order_id = data.get("order_id")

        if not order_id:
            return jsonify({"error": "order_id required"}), 400

        order = find_order(order_id)
        if not order:
            return jsonify({"error": "Order not found"}), 404

        if order["payment_method"] != "stripe":
            return jsonify({"error": "Not a Stripe order"}), 400

        if not order.get("stripe_session_id"):
            return jsonify({"error": "No Stripe session ID"}), 400

        # Fetch session from Stripe
        session = stripe.checkout.Session.retrieve(order["stripe_session_id"])

        # Check payment status
        if session.payment_status == "paid" and order["status"] != "approved":
            # Validate payment amount
            plan = order["plan"]
            expected_amount = PRICE_AMOUNTS[plan]
            if session.amount_total != expected_amount:
                return jsonify({"error": "Payment amount mismatch"}), 400

            # Approve order
            key = generate_key_with_expiry(order["name"], plan)
            update_order_status(order_id, "approved", key)
            send_key_email(order["email"], key, plan, order["name"])

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
```

**Security Measures:**
- Webhook signature verification prevents spoofed payment confirmations
- Idempotency check prevents duplicate key generation
- **NEW:** Payment amount validation prevents tampering
- **NEW:** Mode validation prevents test events in production
- Stripe session ID validation ensures payment actually completed
- Never expose secret key to frontend

#### 1.5 Email Service Updates
**File:** `c:\Users\PC\Mcgraw-Solver\server\email_service.py`

**Changes:**
```python
# **UPDATED:** New pricing
PLAN_DISPLAY = {
    "weekly": "Weekly ($10)",
    "monthly": "Monthly ($25)",
    "semester": "Semester ($50)"
}

def send_key_email(email, key, plan, name):
    """Send access key email to customer."""
    try:
        # ... existing EmailJS logic ...
        template_params = {
            "to_email": email,
            "to_name": name,
            "access_key": key,
            "plan": PLAN_DISPLAY.get(plan, plan),
            "download_url": os.environ.get("DOWNLOAD_URL")
        }
        # Send email via EmailJS
        response = send_emailjs(template_params, "key_email")
        return response
    except Exception as e:
        logger.error(f"Failed to send key email: {e}")
        raise  # Re-raise so caller can add to retry queue

def send_admin_order_notification(order):
    """Send admin notification for new Venmo orders (NOT Stripe)."""
    # **NEW:** Only send for Venmo orders
    if order.get("payment_method") == "stripe":
        logger.info("Skipping admin notification for Stripe order")
        return

    try:
        # ... existing notification logic for Venmo orders ...
        pass
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")
        raise
```

#### 1.6 Email Retry Mechanism
**NEW FILE:** `c:\Users\PC\Mcgraw-Solver\server\retry_emails.py`

```python
"""
Email retry worker for failed email deliveries.
Run as Railway cron job: 0 * * * * python server/retry_emails.py
"""
import os
import sys
import psycopg2
from datetime import datetime, timedelta
import logging

# Import email functions from main app
from email_service import send_key_email, send_admin_order_notification

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def retry_failed_emails():
    """Retry failed emails from the queue."""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        # Get emails to retry (< 24 hours old, < 5 attempts, not retried in last hour)
        cur.execute("""
            SELECT id, order_id, email_type, recipient, template_params
            FROM email_retry_queue
            WHERE attempts < 5
            AND created > NOW() - INTERVAL '24 hours'
            AND (last_attempt IS NULL OR last_attempt < NOW() - INTERVAL '1 hour')
        """)

        pending = cur.fetchall()
        logger.info(f"Found {len(pending)} emails to retry")

        for row in pending:
            queue_id, order_id, email_type, recipient, params = row

            try:
                logger.info(f"Retrying {email_type} for order {order_id}")

                # Attempt to send email
                if email_type == "key_email":
                    send_key_email(
                        recipient,
                        params["key"],
                        params["plan"],
                        params["name"]
                    )
                elif email_type == "admin_notification":
                    send_admin_order_notification(params)

                # Delete from queue on success
                cur.execute("DELETE FROM email_retry_queue WHERE id = %s", (queue_id,))
                conn.commit()
                logger.info(f"✓ Email retry successful for order {order_id}")

            except Exception as e:
                logger.error(f"✗ Email retry failed for order {order_id}: {e}")

                # Update attempt count
                cur.execute("""
                    UPDATE email_retry_queue
                    SET attempts = attempts + 1, last_attempt = NOW()
                    WHERE id = %s
                """, (queue_id,))
                conn.commit()

                # Notify admin if exhausted retries
                if row[4] >= 4:  # attempts column (will be 5 after update)
                    from app import notify_admin_error
                    notify_admin_error("email_retry_exhausted",
                                     f"Order {order_id} email failed after 5 attempts")

        # Clean up old entries (> 24 hours)
        cur.execute("DELETE FROM email_retry_queue WHERE created < NOW() - INTERVAL '24 hours'")
        deleted = cur.rowcount
        conn.commit()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired email queue entries")

        cur.close()
        conn.close()
        logger.info("Email retry worker completed successfully")

    except Exception as e:
        logger.error(f"Email retry worker failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    retry_failed_emails()
```

**Railway Cron Setup:**
1. In Railway project settings → Cron Jobs
2. Add new cron job:
   - Schedule: `0 * * * *` (every hour)
   - Command: `python server/retry_emails.py`

#### 1.7 Frontend Checkout Modal
**File:** `c:\Users\PC\Mcgraw-Solver\docs\index.html`

**Changes to pricing section:**
```html
<!-- UPDATED: New pricing for all three plans -->
<div class="pricing-card">
  <h3>Weekly</h3>
  <div class="price">
    <span class="price-strike">$12</span>
    <span class="price-current">$10</span>
    <span class="price-period">/week</span>
  </div>
  <span class="badge">Try It Out</span>
  <ul>
    <li>✓ Full access to SmartBook Solver</li>
    <li>✓ All question types supported</li>
    <li>✓ Customizable speed & accuracy</li>
    <li>✓ GPT-4o-mini AI model</li>
    <li>✓ 7 days of access</li>
    <li>✓ Perfect for trying the software</li>
  </ul>
  <button class="btn-primary" onclick="openCheckout('weekly')">Get Weekly</button>
</div>

<div class="pricing-card">
  <h3>Monthly</h3>
  <div class="price">
    <span class="price-strike">$30</span>
    <span class="price-current">$25</span>
    <span class="price-period">/month</span>
  </div>
  <span class="badge">Popular</span>
  <ul>
    <li>✓ Everything in Weekly</li>
    <li>✓ Save $15 vs weekly pricing</li>
    <li>✓ <strong>GPT-4o & GPT-4o-mini models</strong></li>
    <li>✓ 30 days of access</li>
    <li>✓ Email support</li>
    <li>✓ Best for single-term courses</li>
  </ul>
  <button class="btn-primary" onclick="openCheckout('monthly')">Get Monthly</button>
</div>

<div class="pricing-card featured">
  <h3>Semester</h3>
  <div class="price">
    <span class="price-strike">$75</span>
    <span class="price-current">$50</span>
    <span class="price-period">/semester</span>
  </div>
  <span class="badge badge-best">Best Value</span>
  <ul>
    <li>✓ Everything in Monthly</li>
    <li>✓ <strong>All AI models: Claude Sonnet 4.5, GPT-4o, GPT-4o-mini</strong></li>
    <li>✓ <strong>Premium Claude Sonnet 4.5</strong> (most accurate)</li>
    <li>✓ Save $30 vs weekly, $25 vs monthly</li>
    <li>✓ 120 days of access (~4 months)</li>
    <li>✓ Priority email support</li>
    <li>✓ Best for full semester coverage</li>
  </ul>
  <button class="btn-primary" onclick="openCheckout('semester')">Get Semester</button>
</div>
```

**Add AI Model Comparison Section:**
```html
<!-- **NEW:** AI Model Comparison - UPDATED with qualitative ratings -->
<div class="ai-model-comparison">
  <h3>AI Model Comparison</h3>
  <table>
    <thead>
      <tr>
        <th>Feature</th>
        <th>GPT-4o-mini<br/><small>(Weekly)</small></th>
        <th>GPT-4o<br/><small>(Monthly)</small></th>
        <th>Claude Sonnet 4.5<br/><small>(Semester)</small></th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Answer Accuracy</td>
        <td>Good</td>
        <td>Very Good</td>
        <td>Excellent</td>
      </tr>
      <tr>
        <td>Processing Speed</td>
        <td>Very Fast</td>
        <td>Fast</td>
        <td>Fast</td>
      </tr>
      <tr>
        <td>Complex Questions</td>
        <td>Good</td>
        <td>Very Good</td>
        <td>Excellent</td>
      </tr>
      <tr>
        <td>Available Models</td>
        <td>1 model</td>
        <td>2 models (choose)</td>
        <td>All 3 models (choose)</td>
      </tr>
    </tbody>
  </table>
  <p class="disclaimer">Performance ratings based on internal testing. Individual results may vary.</p>
</div>
```

**Add Payment Method Selector to Checkout Modal:**
```html
<div id="checkout-modal" class="modal">
  <div class="modal-content">
    <span class="close" onclick="closeCheckout()">&times;</span>
    <h2>Get Access - <span id="checkout-plan-name"></span></h2>

    <!-- **NEW:** Payment method selector -->
    <div class="payment-method-selector">
      <label class="payment-option active">
        <input type="radio" name="payment-method" value="stripe" checked onchange="togglePaymentMethod()">
        <div class="payment-option-content">
          <span class="payment-icon">💳</span>
          <div>
            <strong>Credit/Debit Card</strong>
            <span class="badge-small badge-instant">Instant Access</span>
          </div>
        </div>
      </label>
      <label class="payment-option">
        <input type="radio" name="payment-method" value="venmo" onchange="togglePaymentMethod()">
        <div class="payment-option-content">
          <span class="payment-icon">📱</span>
          <div>
            <strong>Venmo</strong>
            <span class="badge-small">Manual Approval</span>
          </div>
        </div>
      </label>
    </div>

    <!-- Stripe payment fields (shown by default) -->
    <div id="stripe-fields" style="display: block;">
      <form id="stripe-checkout-form" onsubmit="submitStripeOrder(event)">
        <input type="text" id="stripe-name" placeholder="Full Name" required>
        <input type="email" id="stripe-email" placeholder="Email Address" required>
        <input type="text" id="stripe-referral" placeholder="Referral Code (optional)">
        <button type="submit" class="btn-primary btn-large">
          Pay with Stripe →
        </button>
      </form>
    </div>

    <!-- Venmo payment fields (hidden by default) -->
    <div id="venmo-fields" style="display: none;">
      <form id="venmo-checkout-form" onsubmit="submitVenmoOrder(event)">
        <input type="text" id="venmo-name" placeholder="Full Name" required>
        <input type="email" id="venmo-email" placeholder="Email Address" required>
        <input type="text" id="venmo-username" placeholder="Venmo Username" required>
        <input type="text" id="venmo-transaction-id" placeholder="Venmo Transaction ID" required>
        <input type="text" id="venmo-referral" placeholder="Referral Code (optional)">
        <p class="venmo-instructions">
          Send <strong>$<span id="venmo-amount"></span></strong> to <strong>@YourVenmoHandle</strong>
          and enter the transaction ID above.
        </p>
        <button type="submit" class="btn-primary btn-large">
          Submit Venmo Order →
        </button>
      </form>
    </div>
  </div>
</div>
```

**Add Success Page Handler:**
```html
<!-- Add after pricing section -->
<div id="success-message" class="success-banner" style="display: none;">
  <h2>🎉 Payment Successful!</h2>
  <p>Check your email for your access key and download link.</p>
  <p>Didn't receive an email? Check your spam folder or contact support.</p>
</div>
```

**Add Refund Policy Section:**
```html
<!-- Add before footer -->
<section id="refund-policy">
  <h2>Refund Policy</h2>
  <p><strong>All sales are final.</strong> We do not offer refunds on any plan purchases. Please ensure you understand the product and features before purchasing.</p>
  <p>We recommend starting with the Weekly plan to try the software before committing to longer plans.</p>
  <p>If you experience technical issues, please contact support for assistance.</p>
</section>
```

#### 1.8 Frontend JavaScript
**File:** `c:\Users\PC\Mcgraw-Solver\docs\app.js`

**New Functions:**
```javascript
const API_URL = "https://mcgraw-solver-production.up.railway.app";
let currentPlan = "";

// Toggle between Stripe and Venmo payment forms
function togglePaymentMethod() {
  const method = document.querySelector('input[name="payment-method"]:checked').value;
  const stripeFields = document.getElementById('stripe-fields');
  const venmoFields = document.getElementById('venmo-fields');

  if (method === 'stripe') {
    stripeFields.style.display = 'block';
    venmoFields.style.display = 'none';
    document.querySelectorAll('.payment-option')[0].classList.add('active');
    document.querySelectorAll('.payment-option')[1].classList.remove('active');
  } else {
    stripeFields.style.display = 'none';
    venmoFields.style.display = 'block';
    document.querySelectorAll('.payment-option')[0].classList.remove('active');
    document.querySelectorAll('.payment-option')[1].classList.add('active');
  }
}

// Open checkout modal
function openCheckout(plan) {
  currentPlan = plan;

  // Set plan name
  const planNames = {
    'weekly': 'Weekly Plan ($10)',
    'monthly': 'Monthly Plan ($25)',
    'semester': 'Semester Plan ($50)'
  };
  document.getElementById('checkout-plan-name').textContent = planNames[plan];

  // Set Venmo amount
  const venmoAmounts = {'weekly': '10', 'monthly': '25', 'semester': '50'};
  document.getElementById('venmo-amount').textContent = venmoAmounts[plan];

  // Show modal
  document.getElementById('checkout-modal').style.display = 'flex';

  // Reset to Stripe by default
  document.querySelector('input[value="stripe"]').checked = true;
  togglePaymentMethod();
}

function closeCheckout() {
  document.getElementById('checkout-modal').style.display = 'none';
}

// Submit Stripe order and redirect to checkout
async function submitStripeOrder(e) {
  e.preventDefault();

  const name = document.getElementById('stripe-name').value.trim();
  const email = document.getElementById('stripe-email').value.trim();
  const referral = document.getElementById('stripe-referral').value.trim();

  if (!name || !email) {
    alert('Please fill in all required fields');
    return;
  }

  try {
    const response = await fetch(`${API_URL}/api/orders/stripe`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name: name,
        email: email,
        plan: currentPlan,
        referral: referral || null
      })
    });

    const data = await response.json();

    if (response.ok && data.session_url) {
      // Redirect to Stripe Checkout
      window.location.href = data.session_url;
    } else {
      alert(data.error || 'Failed to create checkout session');
    }
  } catch (error) {
    console.error('Checkout error:', error);
    alert('Network error. Please try again.');
  }
}

// Submit Venmo order (existing function, updated for new pricing)
async function submitVenmoOrder(e) {
  e.preventDefault();

  const name = document.getElementById('venmo-name').value.trim();
  const email = document.getElementById('venmo-email').value.trim();
  const venmoUsername = document.getElementById('venmo-username').value.trim();
  const transactionId = document.getElementById('venmo-transaction-id').value.trim();
  const referral = document.getElementById('venmo-referral').value.trim();

  if (!name || !email || !venmoUsername || !transactionId) {
    alert('Please fill in all required fields');
    return;
  }

  try {
    const response = await fetch(`${API_URL}/api/orders`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name: name,
        email: email,
        plan: currentPlan,
        venmo_username: venmoUsername,
        transaction_id: transactionId,
        referral: referral || null,
        payment_method: 'venmo'
      })
    });

    const data = await response.json();

    if (response.ok) {
      closeCheckout();
      alert('Order submitted! You will receive an email once approved (usually within 24 hours).');
    } else {
      alert(data.error || 'Failed to submit order');
    }
  } catch (error) {
    console.error('Order error:', error);
    alert('Network error. Please try again.');
  }
}

// Handle Stripe success redirect
function handleStripeSuccess() {
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has('session_id')) {
    document.getElementById('success-message').style.display = 'block';
    // Scroll to success message
    document.getElementById('success-message').scrollIntoView({ behavior: 'smooth' });
    // Clear URL params
    window.history.replaceState({}, document.title, window.location.pathname);
  }
}

// Run on page load
document.addEventListener('DOMContentLoaded', function() {
  handleStripeSuccess();
});
```

#### 1.9 Admin Panel Updates
**File:** `c:\Users\PC\Mcgraw-Solver\docs\admin.html`

**Changes:**
```html
<!-- Add payment method column to pending orders table -->
<table id="pending-orders">
  <thead>
    <tr>
      <th>Name</th>
      <th>Email</th>
      <th>Plan</th>
      <th>Payment Method</th> <!-- NEW -->
      <th>Transaction ID</th>
      <th>Date</th>
      <th>Actions</th>
    </tr>
  </thead>
  <tbody>
    <!-- Populated by JavaScript -->
  </tbody>
</table>

<!-- Add payment method column to order history -->
<table id="order-history">
  <thead>
    <tr>
      <th>Name</th>
      <th>Email</th>
      <th>Plan</th>
      <th>Payment Method</th> <!-- NEW -->
      <th>Status</th>
      <th>Key</th>
      <th>Date</th>
    </tr>
  </thead>
  <tbody>
    <!-- Populated by JavaScript -->
  </tbody>
</table>
```

**File:** `c:\Users\PC\Mcgraw-Solver\docs\admin.js`

```javascript
// Update renderPendingOrders to show payment method
function renderPendingOrders(orders) {
  const tbody = document.querySelector('#pending-orders tbody');
  tbody.innerHTML = '';

  orders.forEach(order => {
    const row = document.createElement('tr');

    // Payment method badge
    let paymentBadge = '';
    if (order.payment_method === 'stripe') {
      paymentBadge = '<span class="badge badge-stripe">Stripe ✓</span>';
    } else {
      paymentBadge = '<span class="badge badge-venmo">Venmo</span>';
    }

    // Actions - different for Stripe vs Venmo
    let actions = '';
    if (order.payment_method === 'stripe') {
      // Stripe orders are auto-approved, but show sync button in case webhook failed
      if (order.status === 'pending') {
        actions = `
          <button onclick="syncStripeOrder('${order.id}')" class="btn-sync">
            🔄 Sync from Stripe
          </button>
        `;
      } else {
        actions = '<span class="text-success">Auto-approved ✓</span>';
      }
    } else {
      // Venmo orders need manual approval
      actions = `
        <button onclick="approveOrder('${order.id}')" class="btn-approve">Approve</button>
        <button onclick="rejectOrder('${order.id}')" class="btn-reject">Reject</button>
      `;
    }

    row.innerHTML = `
      <td>${order.name}</td>
      <td>${order.email}</td>
      <td>${order.plan}</td>
      <td>${paymentBadge}</td>
      <td>${order.transaction_id || 'N/A'}</td>
      <td>${new Date(order.created_at).toLocaleString()}</td>
      <td>${actions}</td>
    `;

    tbody.appendChild(row);
  });
}

// **NEW:** Sync Stripe order manually
async function syncStripeOrder(orderId) {
  if (!confirm('Fetch payment status from Stripe for this order?')) return;

  try {
    const response = await fetch(`${API_URL}/api/admin/sync-stripe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Basic ' + btoa(adminPassword)  // Add auth
      },
      body: JSON.stringify({ order_id: orderId })
    });

    const data = await response.json();

    if (response.ok && data.success) {
      alert(data.message);
      loadPendingOrders();  // Refresh table
    } else {
      alert(data.message || 'Failed to sync order');
    }
  } catch (error) {
    console.error('Sync error:', error);
    alert('Network error. Please try again.');
  }
}

// Update renderOrderHistory to show payment method
function renderOrderHistory(orders) {
  const tbody = document.querySelector('#order-history tbody');
  tbody.innerHTML = '';

  orders.forEach(order => {
    const row = document.createElement('tr');

    let paymentBadge = '';
    if (order.payment_method === 'stripe') {
      paymentBadge = '<span class="badge badge-stripe">Stripe ✓</span>';
    } else {
      paymentBadge = '<span class="badge badge-venmo">Venmo</span>';
    }

    let statusBadge = '';
    if (order.status === 'approved') {
      statusBadge = '<span class="badge badge-success">Approved</span>';
    } else if (order.status === 'rejected') {
      statusBadge = '<span class="badge badge-danger">Rejected</span>';
    } else {
      statusBadge = '<span class="badge badge-warning">Pending</span>';
    }

    row.innerHTML = `
      <td>${order.name}</td>
      <td>${order.email}</td>
      <td>${order.plan}</td>
      <td>${paymentBadge}</td>
      <td>${statusBadge}</td>
      <td><code>${order.key || 'N/A'}</code></td>
      <td>${new Date(order.created_at).toLocaleString()}</td>
    `;

    tbody.appendChild(row);
  });
}
```

**Add CSS for badges:**
```css
.badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.badge-stripe {
  background: #635bff;
  color: white;
}

.badge-venmo {
  background: #3d95ce;
  color: white;
}

.badge-success {
  background: #28a745;
  color: white;
}

.badge-danger {
  background: #dc3545;
  color: white;
}

.btn-sync {
  background: #635bff;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}

.btn-sync:hover {
  background: #5048e5;
}
```

#### 1.10 Stripe Dashboard Configuration
**Post-deployment steps:**

1. **Create Webhook Endpoint:**
   - Go to Stripe Dashboard → Developers → Webhooks
   - Click "Add endpoint"
   - URL: `https://mcgraw-solver-production.up.railway.app/api/stripe/webhook`
   - Listen to events: Select `checkout.session.completed`
   - Click "Add endpoint"
   - Copy webhook signing secret to Railway environment variables as `STRIPE_WEBHOOK_SECRET`

2. **Test Webhook Locally:**
   ```bash
   stripe listen --forward-to localhost:8080/api/stripe/webhook
   stripe trigger checkout.session.completed
   ```

3. **Disable Automatic Refunds:**
   - Go to Settings → Payments → Refunds
   - Disable "Allow customers to request refunds"
   - Set default refund policy to "Contact support"

4. **Configure Payment Methods:**
   - Settings → Payment methods
   - Enable: Card payments (Visa, Mastercard, Amex, Discover)
   - Optional: Enable Apple Pay, Google Pay for better conversion

---

## Feature 2: Enhanced Plan Descriptions & AI Model Tiers

### Overview
Improve plan descriptions to clearly communicate value differences. Implement AI model access tiers where Weekly plans use GPT-4o-mini, Monthly plans get GPT-4o and GPT-4o-mini (user chooses), and Semester plan gets all models including premium Claude Sonnet 4.5 (user chooses).

### Edge Cases & Decisions
- **Model selection**: Both monthly and semester users see dropdown to choose their model
- **Model preference**: Saved server-side per key, syncs across devices
- **Model identifiers**: Use 'gpt-4o' and 'gpt-4o-mini' (OpenAI routes to latest version), 'claude-sonnet-4-5-20250929' for Claude
- **Key expiration**: Check on every question with grace period only for active sessions
- **Unauthorized model access**: Show error message in GUI with "Upgrade Plan" button

### Implementation Steps

#### 2.1 Website Plan Descriptions
**Already covered in section 1.7** - See updated pricing cards and AI model comparison table with qualitative ratings (Good/Very Good/Excellent) instead of specific percentages.

#### 2.2 Server-Side AI Model Enforcement
**File:** `c:\Users\PC\Mcgraw-Solver\server\app.py`

**Add helper function:**
```python
def get_allowed_models(plan):
    """Return list of allowed AI models based on plan tier."""
    if plan == "semester":
        return ["claude-sonnet-4-5-20250929", "gpt-4o", "gpt-4o-mini"]  # All models
    elif plan == "monthly":
        return ["gpt-4o", "gpt-4o-mini"]  # GPT-4o and mini
    else:  # weekly
        return ["gpt-4o-mini"]  # Only mini
```

**Update key validation endpoint:**
```python
@app.route("/api/keys/validate", methods=["POST"])
def validate_key():
    """Validate access key and return plan info."""
    data = request.get_json()
    access_key = data.get("access_key", "").strip()

    if not access_key:
        return jsonify({"valid": False, "error": "Access key required"}), 400

    key_data = find_key(access_key)

    if not key_data:
        return jsonify({"valid": False, "error": "Invalid access key"}), 403

    # Check expiration (no grace period for login, only for active sessions)
    if key_data.get("expires"):
        expiry = datetime.fromisoformat(key_data["expires"].rstrip("Z"))
        if datetime.utcnow() > expiry:
            return jsonify({"valid": False, "error": "Access key expired"}), 403

    plan = key_data["plan"]
    allowed_models = get_allowed_models(plan)

    return jsonify({
        "valid": True,
        "plan": plan,
        "allowed_models": allowed_models,
        "preferred_model": key_data.get("preferred_model") or allowed_models[0],  # Default to first allowed
        "expires": key_data["expires"],
        "name": key_data["name"]
    })
```

**Add model preference endpoint:**
```python
@app.route("/api/keys/preference", methods=["POST"])
def save_model_preference():
    """Save user's preferred AI model for their key."""
    data = request.get_json()
    access_key = data.get("access_key")
    preferred_model = data.get("preferred_model")

    if not access_key or not preferred_model:
        return jsonify({"error": "access_key and preferred_model required"}), 400

    key_data = find_key(access_key)
    if not key_data:
        return jsonify({"error": "Invalid key"}), 403

    # Verify model is allowed for this plan
    allowed_models = get_allowed_models(key_data["plan"])
    if preferred_model not in allowed_models:
        return jsonify({
            "error": "Model not allowed for your plan",
            "allowed_models": allowed_models
        }), 403

    # Save preference to database
    update_key_preference(access_key, preferred_model)

    logger.info(f"Model preference updated: {access_key} → {preferred_model}")

    return jsonify({"success": True})
```

**Update solve endpoint with model enforcement and grace period:**
```python
@app.route("/api/solve", methods=["POST"])
def solve_question():
    """Process question with AI model (with tier enforcement)."""
    data = request.get_json()
    access_key = data.get("access_key")
    requested_model = data.get("model")
    session_start_time = data.get("session_start_time")  # **NEW:** For grace period

    if not access_key:
        return jsonify({"error": "Access key required"}), 403

    key_data = find_key(access_key)
    if not key_data:
        return jsonify({"error": "Invalid access key"}), 403

    # **NEW:** Grace period logic - only for active sessions
    if key_data.get("expires"):
        expiry = datetime.fromisoformat(key_data["expires"].rstrip("Z"))
        grace_period = timedelta(hours=5)

        # If session started before key expired, give grace period
        if session_start_time:
            session_start = datetime.fromisoformat(session_start_time)

            # Key was valid when session started - allow grace period
            if session_start < expiry:
                if datetime.utcnow() > expiry + grace_period:
                    return jsonify({
                        "error": "Grace period expired",
                        "message": "Your session grace period has ended. Please purchase a new plan."
                    }), 403
            # Key was already expired when session started - no grace period
            elif datetime.utcnow() > expiry:
                return jsonify({
                    "error": "Access key expired",
                    "message": "Your access key has expired. Please purchase a new plan."
                }), 403
        else:
            # No session start time provided - no grace period
            if datetime.utcnow() > expiry:
                return jsonify({
                    "error": "Access key expired",
                    "message": "Your access key has expired. Please purchase a new plan."
                }), 403

    # Determine allowed models based on plan
    allowed_models = get_allowed_models(key_data["plan"])

    # If user requests a model they don't have access to, return error
    if requested_model and requested_model not in allowed_models:
        return jsonify({
            "error": "model_not_allowed",
            "message": f"Your {key_data['plan']} plan does not include access to {requested_model}",
            "allowed_models": allowed_models,
            "upgrade_url": f"{FRONTEND_URL}/#pricing"
        }), 403

    # Use requested model or user's preference or first allowed model
    model = requested_model or key_data.get("preferred_model") or allowed_models[0]

    # ... rest of solve logic with selected model ...

    try:
        # Call appropriate AI API based on model
        if model.startswith("claude"):
            answer = call_claude_api(question_data, model)
        elif model.startswith("gpt"):
            answer = call_openai_api(question_data, model)
        else:
            return jsonify({"error": "Unknown model"}), 400

        return jsonify({"answer": answer, "model_used": model})

    except Exception as e:
        logger.error(f"Solve error: {e}")
        return jsonify({"error": "Failed to process question"}), 500
```

#### 2.3 Client-Side AI Model Selection
**File:** `c:\Users\PC\Mcgraw-Solver\config.py`

**Changes:**
```python
# **REMOVE:** Hardcoded model
# GPT_MODEL = "claude-sonnet-4-5-20250929"  # DELETE THIS

# **ADD:** Model determination function
def get_default_model_for_plan(plan):
    """Return the default AI model to use based on subscription plan."""
    if plan == "semester":
        return "claude-sonnet-4-5-20250929"  # Premium model
    elif plan == "monthly":
        return "gpt-4o"  # Monthly gets GPT-4o by default
    else:  # weekly
        return "gpt-4o-mini"  # Weekly gets mini

# **ADD:** User-friendly model names for GUI display
MODEL_DISPLAY_NAMES = {
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5 (Premium)",
    "gpt-4o": "GPT-4o (Advanced)",
    "gpt-4o-mini": "GPT-4o-mini (Fast)"
}
```

**File:** `c:\Users\PC\Mcgraw-Solver\gui.py`

**Add to login/validation handler:**
```python
def _validate_key(self):
    """Validate access key with server."""
    access_key = self.key_entry.get().strip()

    if not access_key:
        self._show_error("Please enter an access key")
        return

    try:
        response = requests.post(f"{API_URL}/api/keys/validate",
                               json={"access_key": access_key})

        if response.status_code == 200:
            data = response.json()
            if data["valid"]:
                # Store key info
                self._access_key = access_key
                self._validated_plan = data["plan"]
                self._allowed_models = data["allowed_models"]
                self._preferred_model = data["preferred_model"]
                self._key_expires = data["expires"]

                # Show solver page
                self._show_solver_page()
            else:
                self._show_error(data.get("error", "Invalid key"))
        else:
            error_data = response.json()
            self._show_error(error_data.get("error", "Validation failed"))

    except Exception as e:
        logger.error(f"Key validation error: {e}")
        self._show_error("Network error. Please check your connection.")
```

**Add model selector to solver page (if multiple models available):**
```python
def _show_solver_page(self):
    """Display the main solver interface."""
    # ... existing solver page setup ...

    # **NEW:** Model selector (only if user has multiple models)
    if len(self._allowed_models) > 1:
        model_frame = tk.Frame(controls_frame, bg=_C["bg_card"])
        model_frame.pack(fill="x", pady=10)

        model_label = tk.Label(model_frame, text="AI Model:",
                              fg=_C["text"], bg=_C["bg_card"],
                              font=(_FONT, 11, "bold"))
        model_label.pack(side="left", padx=(0, 10))

        # Create user-friendly model options
        from config import MODEL_DISPLAY_NAMES
        model_options = [MODEL_DISPLAY_NAMES.get(m, m) for m in self._allowed_models]

        self.model_var = tk.StringVar(value=MODEL_DISPLAY_NAMES.get(self._preferred_model, self._preferred_model))
        self.model_dropdown = ttk.Combobox(model_frame,
                                          textvariable=self.model_var,
                                          values=model_options,
                                          state="readonly",
                                          width=30)
        self.model_dropdown.pack(side="left")
        self.model_dropdown.bind("<<ComboboxSelected>>", self._on_model_changed)

        # Info label
        model_info = tk.Label(model_frame, text="ℹ️ Choose your preferred AI model",
                             fg=_C["text_dim"], bg=_C["bg_card"],
                             font=(_FONT, 9))
        model_info.pack(side="left", padx=(10, 0))
    else:
        # Single model - just show which one
        from config import MODEL_DISPLAY_NAMES
        model_name = MODEL_DISPLAY_NAMES.get(self._allowed_models[0], self._allowed_models[0])
        model_label = tk.Label(controls_frame,
                              text=f"AI Model: {model_name}",
                              fg=_C["text"], bg=_C["bg_card"],
                              font=(_FONT, 10))
        model_label.pack(pady=5)

    # ... rest of solver page ...

def _on_model_changed(self, event=None):
    """Handle model selection change - save preference to server."""
    if not hasattr(self, 'model_var'):
        return

    # Get selected display name and convert back to model ID
    from config import MODEL_DISPLAY_NAMES
    selected_display = self.model_var.get()

    # Reverse lookup to get model ID
    model_id = None
    for mid, display_name in MODEL_DISPLAY_NAMES.items():
        if display_name == selected_display:
            model_id = mid
            break

    if not model_id or model_id not in self._allowed_models:
        return

    # Save preference to server
    try:
        response = requests.post(f"{API_URL}/api/keys/preference",
                               json={
                                   "access_key": self._access_key,
                                   "preferred_model": model_id
                               })

        if response.status_code == 200:
            self._preferred_model = model_id
            logger.info(f"Model preference saved: {model_id}")
            self._add_log(f"AI model changed to {selected_display}")
        else:
            logger.error(f"Failed to save model preference: {response.text}")

    except Exception as e:
        logger.error(f"Error saving model preference: {e}")

def _handle_model_error(self, error_data):
    """Show error dialog when model access denied."""
    message = error_data.get("message", "Model not available for your plan")
    upgrade_url = error_data.get("upgrade_url")
    allowed_models = error_data.get("allowed_models", [])

    # Create error dialog
    dialog = tk.Toplevel(self.root)
    dialog.title("Upgrade Required")
    dialog.geometry("400x250")
    dialog.configure(bg=_C["bg_card"])
    dialog.resizable(False, False)

    # Center dialog
    dialog.transient(self.root)
    dialog.grab_set()

    # Error icon and message
    icon_label = tk.Label(dialog, text="🔒", font=(_FONT, 48),
                         bg=_C["bg_card"], fg=_C["yellow"])
    icon_label.pack(pady=20)

    msg_label = tk.Label(dialog, text=message, font=(_FONT, 11),
                        bg=_C["bg_card"], fg=_C["text"],
                        wraplength=350, justify="center")
    msg_label.pack(pady=10)

    if allowed_models:
        from config import MODEL_DISPLAY_NAMES
        allowed_names = [MODEL_DISPLAY_NAMES.get(m, m) for m in allowed_models]
        allowed_text = "Available models:\n" + "\n".join(f"• {name}" for name in allowed_names)

        allowed_label = tk.Label(dialog, text=allowed_text, font=(_FONT, 9),
                                bg=_C["bg_card"], fg=_C["text_dim"],
                                justify="left")
        allowed_label.pack(pady=10)

    # Buttons frame
    btn_frame = tk.Frame(dialog, bg=_C["bg_card"])
    btn_frame.pack(pady=20)

    # Upgrade button
    if upgrade_url:
        upgrade_btn = tk.Button(btn_frame, text="Upgrade Plan",
                               command=lambda: (webbrowser.open(upgrade_url), dialog.destroy()),
                               bg=_C["cyan"], fg=_C["bg"],
                               font=(_FONT, 10, "bold"),
                               cursor="hand2", relief="flat",
                               padx=20, pady=10)
        upgrade_btn.pack(side="left", padx=5)

    # Close button
    close_btn = tk.Button(btn_frame, text="Close",
                         command=dialog.destroy,
                         bg=_C["bg_input"], fg=_C["text"],
                         font=(_FONT, 10),
                         cursor="hand2", relief="flat",
                         padx=20, pady=10)
    close_btn.pack(side="left", padx=5)
```

**File:** `c:\Users\PC\Mcgraw-Solver\main.py` (SolverApp class)

**Changes:**
```python
class SolverApp:
    def __init__(self, access_key, plan, preferred_model, allowed_models):
        """Initialize solver with plan and model info."""
        self.access_key = access_key
        self.plan = plan
        self.preferred_model = preferred_model
        self.allowed_models = allowed_models
        self.session_start_time = datetime.utcnow().isoformat()  # **NEW:** For grace period
        # ... rest of init ...

    def _handle_question(self, question_data):
        """Process a single question."""
        # ... existing code ...

        # Get current model selection from GUI (or use preference)
        current_model = self.gui.get_selected_model() if self.gui else self.preferred_model

        # Call solver API with model
        try:
            response = requests.post(f"{API_URL}/api/solve", json={
                "access_key": self.access_key,
                "model": current_model,
                "session_start_time": self.session_start_time,  # **NEW:** For grace period
                "question": question_data
            })

            if response.status_code == 200:
                data = response.json()
                answer = data["answer"]
                # ... process answer ...
            elif response.status_code == 403:
                error_data = response.json()
                if error_data.get("error") == "model_not_allowed":
                    # Show upgrade dialog
                    if self.gui:
                        self.gui.root.after(0, lambda: self.gui._handle_model_error(error_data))
                    return
                else:
                    # Handle expiration error
                    self._add_log(f"Error: {error_data.get('message', 'Access denied')}")
                    self.stop()
            else:
                self._add_log(f"Error: {response.status_code}")

        except Exception as e:
            logger.error(f"Solve request error: {e}")
            self._add_log(f"Network error: {e}")
```

---

## Feature 3: Loading Indicator in GUI

### Overview
Add visual progress feedback during automation delays so users know the bot is actively working. Uses generic messages to avoid revealing automation mechanics.

### Edge Cases & Decisions
- **Progress messages**: Generic ("Processing question...", "Preparing next question...") instead of specific timing/word counts
- **Stop/pause behavior**: Progress bar resets when user clicks stop or pause
- **Performance**: Updates every 100ms for smooth animation

### Implementation Steps

#### 3.1 Progress Bar Component
**File:** `c:\Users\PC\Mcgraw-Solver\gui.py`

**Add to solver page (after stats cards, before log section):**
```python
# Progress section
progress_frame = tk.Frame(self._solver_frame, bg=_C["bg_card"],
                         highlightbackground=_C["border"], highlightthickness=1)
progress_frame.pack(fill="x", padx=20, pady=(0, 10))

# Progress label - **UPDATED:** Generic messages only
self.progress_label = tk.Label(progress_frame, text="Ready",
                               fg=_C["text"], bg=_C["bg_card"],
                               font=(_FONT, 11))
self.progress_label.pack(pady=(10, 5))

# Progress bar
self.progress_var = tk.DoubleVar(value=0.0)
self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var,
                                    maximum=100.0, mode='determinate',
                                    length=400)
self.progress_bar.pack(pady=(5, 10), padx=20)

# **UPDATED:** No specific time remaining shown
self.progress_status = tk.Label(progress_frame, text="",
                               fg=_C["text_dim"], bg=_C["bg_card"],
                               font=(_FONT, 9))
self.progress_status.pack(pady=(0, 10))
```

**Add progress update methods:**
```python
def start_progress(self, message):
    """Start a progress animation with generic message."""
    self.progress_label.config(text=message)
    self.progress_status.config(text="⏳ Working...")
    self.progress_var.set(0)
    self._progress_active = True

def update_progress(self, percent):
    """Update progress bar percentage (0-100)."""
    if hasattr(self, '_progress_active') and self._progress_active:
        self.progress_var.set(min(100, max(0, percent)))

def complete_progress(self):
    """Mark progress as complete."""
    self.progress_var.set(100)
    self.progress_status.config(text="✓ Complete")
    self._progress_active = False

    # Reset after 1 second
    self.root.after(1000, lambda: self.progress_label.config(text="Ready"))
    self.root.after(1000, lambda: self.progress_status.config(text=""))
    self.root.after(1000, lambda: self.progress_var.set(0))

def clear_progress(self):
    """Clear progress bar and reset to ready state."""
    self.progress_var.set(0)
    self.progress_label.config(text="Ready")
    self.progress_status.config(text="")
    self._progress_active = False
```

**Style the progress bar:**
```python
# Add to __init__ method, after root configuration
style = ttk.Style()
style.theme_use('clam')
style.configure("TProgressbar",
                troughcolor=_C["bg_input"],
                background=_C["cyan"],
                bordercolor=_C["border"],
                lightcolor=_C["cyan"],
                darkcolor=_C["cyan"],
                thickness=20)
```

#### 3.2 Integration with Delay Functions
**File:** `c:\Users\PC\Mcgraw-Solver\human.py`

**Modify delay functions to accept callback:**
```python
import time
import random
import logging

logger = logging.getLogger(__name__)

def random_delay(min_s, max_s, progress_callback=None):
    """
    Random delay between questions with optional progress callback.
    **UPDATED:** Generic message only, no specific timing revealed.
    """
    delay = random.uniform(min_s, max_s)

    if progress_callback:
        progress_callback("Preparing next question...")

    logger.info(f"[delay] waiting {delay:.1f}s")

    # Simulate progress over delay period
    if progress_callback:
        steps = int(delay * 10)  # Update 10 times per second
        for i in range(steps):
            time.sleep(0.1)
            # Update progress percentage (callback can handle this)
        else:
            time.sleep(delay)

    return delay

def reading_delay(text, progress_callback=None):
    """
    Simulate reading time based on word count with optional progress callback.
    **UPDATED:** Generic message only, no word count revealed.
    """
    words = len(text.split())
    base_wpm = config.READING_WPM
    variance = config.READING_WPM_VARIANCE
    wpm = random.uniform(base_wpm - variance, base_wpm + variance)
    delay = max(1.0, min(15.0, (words / wpm) * 60))

    if progress_callback:
        progress_callback("Processing question...")

    logger.info(f"[reading] {words} words, {delay:.1f}s at {wpm:.0f} wpm")
    time.sleep(delay)

    return delay

def typing_delay(text, progress_callback=None):
    """
    Simulate typing time with optional progress callback.
    **UPDATED:** Generic message.
    """
    chars = len(text)
    delay = chars / config.TYPING_SPEED
    delay = max(0.3, min(3.0, delay))

    if progress_callback:
        progress_callback("Submitting answer...")

    logger.info(f"[typing] {chars} chars, {delay:.1f}s")
    time.sleep(delay)

    return delay
```

#### 3.3 Main Loop Integration
**File:** `c:\Users\PC\Mcgraw-Solver\main.py`

**Add progress callbacks to delay points:**
```python
def _handle_question(self, question_data):
    """Process a single question with progress feedback."""
    # ... existing code ...

    # **UPDATED:** Reading delay with generic progress
    self._update_gui_progress("Processing question...")
    human.reading_delay(
        question_data.question,
        progress_callback=lambda msg: self._update_gui_progress(msg)
    )

    # ... AI processing ...

    # **UPDATED:** Typing delay
    self._update_gui_progress("Submitting answer...")
    human.typing_delay(
        selected_answer,
        progress_callback=lambda msg: self._update_gui_progress(msg)
    )

    # ... submit answer ...

    # **UPDATED:** Main delay between questions
    self._update_gui_progress("Preparing next question...")
    human.random_delay(
        config.MIN_DELAY,
        config.MAX_DELAY,
        progress_callback=lambda msg: self._update_gui_progress(msg)
    )

    # Mark question complete
    if self.gui:
        self.gui.root.after(0, lambda: self.gui.complete_progress())

def _update_gui_progress(self, message):
    """Thread-safe GUI progress update."""
    if self.gui:
        self.gui.root.after(0, lambda: self.gui.start_progress(message))
```

---

## Feature 4: Session Management (One-Device-at-a-Time)

**NEW FEATURE** - Enforce one active session per access key to prevent unlimited sharing.

### Implementation Steps

#### 4.1 Database Schema
**Already added in migration script (section 1.2):**
- `active_sessions` table with `access_key`, `session_id`, `started_at`, `last_heartbeat`
- Indexes for performance

#### 4.2 Server-Side Session Management
**File:** `c:\Users\PC\Mcgraw-Solver\server\db.py`

**Add session management functions:**
```python
def create_session(access_key, session_id):
    """Create a new active session and invalidate any existing sessions."""
    cur = conn.cursor()

    # Delete any existing sessions for this key
    cur.execute("DELETE FROM active_sessions WHERE access_key = %s", (access_key,))

    # Create new session
    cur.execute("""
        INSERT INTO active_sessions (access_key, session_id, started_at, last_heartbeat)
        VALUES (%s, %s, NOW(), NOW())
    """, (access_key, session_id))

    conn.commit()
    cur.close()
    logger.info(f"Session created: {session_id} for key {access_key}")

def update_session_heartbeat(session_id):
    """Update session heartbeat to keep it alive."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE active_sessions
        SET last_heartbeat = NOW()
        WHERE session_id = %s
    """, (session_id,))
    conn.commit()
    cur.close()

def get_active_session(access_key):
    """Get active session for a key (if not expired)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT session_id, started_at, last_heartbeat
        FROM active_sessions
        WHERE access_key = %s
        AND last_heartbeat > NOW() - INTERVAL '60 seconds'
    """, (access_key,))
    session = cur.fetchone()
    cur.close()
    return session

def delete_session(session_id):
    """Delete a session."""
    cur = conn.cursor()
    cur.execute("DELETE FROM active_sessions WHERE session_id = %s", (session_id,))
    conn.commit()
    cur.close()

def cleanup_expired_sessions():
    """Clean up sessions with no heartbeat for > 60 seconds."""
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM active_sessions
        WHERE last_heartbeat < NOW() - INTERVAL '60 seconds'
    """)
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    if deleted > 0:
        logger.info(f"Cleaned up {deleted} expired sessions")
    return deleted
```

**File:** `c:\Users\PC\Mcgraw-Solver\server\app.py`

**Add session endpoints:**
```python
import uuid

@app.route("/api/session/start", methods=["POST"])
def start_session():
    """Start a new session for an access key."""
    data = request.get_json()
    access_key = data.get("access_key")

    if not access_key:
        return jsonify({"error": "access_key required"}), 400

    # Verify key is valid
    key_data = find_key(access_key)
    if not key_data:
        return jsonify({"error": "Invalid key"}), 403

    # Check for existing active session
    existing_session = get_active_session(access_key)

    # Generate new session ID
    session_id = str(uuid.uuid4())

    # Create session (will disconnect any existing session)
    create_session(access_key, session_id)

    disconnected_other = existing_session is not None

    return jsonify({
        "session_id": session_id,
        "disconnected_other_session": disconnected_other
    })

@app.route("/api/session/heartbeat", methods=["POST"])
def session_heartbeat():
    """Update session heartbeat to keep it alive."""
    data = request.get_json()
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "session_id required"}), 400

    try:
        update_session_heartbeat(session_id)
        return jsonify({"success": True})
    except:
        return jsonify({"error": "Session not found"}), 404

@app.route("/api/session/end", methods=["POST"])
def end_session():
    """End a session."""
    data = request.get_json()
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "session_id required"}), 400

    delete_session(session_id)
    return jsonify({"success": True})

# Add cleanup cron (run every 5 minutes)
# This can be a separate Railway cron or use APScheduler
```

**Create session cleanup cron:**
**NEW FILE:** `c:\Users\PC\Mcgraw-Solver\server\cleanup_sessions.py`
```python
"""
Session cleanup worker - removes expired sessions.
Run as Railway cron: */5 * * * * python server/cleanup_sessions.py
"""
import os
import sys
from db import cleanup_expired_sessions

if __name__ == "__main__":
    try:
        cleanup_expired_sessions()
    except Exception as e:
        print(f"Session cleanup error: {e}")
        sys.exit(1)
```

#### 4.3 Client-Side Session Management
**File:** `c:\Users\PC\Mcgraw-Solver\main.py`

**Add session handling:**
```python
class SolverApp:
    def __init__(self, access_key, plan, preferred_model, allowed_models):
        # ... existing init ...
        self.session_id = None
        self.heartbeat_thread = None

    def start_solving(self):
        """Start the solving process with session management."""
        # Start session with server
        try:
            response = requests.post(f"{API_URL}/api/session/start",
                                   json={"access_key": self.access_key})

            if response.status_code == 200:
                data = response.json()
                self.session_id = data["session_id"]

                if data.get("disconnected_other_session"):
                    self._add_log("⚠️ Previous session on another device was disconnected")

                # Start heartbeat thread
                self._start_heartbeat()

                # Start solving
                self._run_solver()
            else:
                self._add_log("Failed to start session")
                return

        except Exception as e:
            logger.error(f"Session start error: {e}")
            self._add_log(f"Network error: {e}")

    def _start_heartbeat(self):
        """Start heartbeat thread to keep session alive."""
        def heartbeat_loop():
            while self.is_running and self.session_id:
                try:
                    requests.post(f"{API_URL}/api/session/heartbeat",
                                json={"session_id": self.session_id},
                                timeout=5)
                    time.sleep(30)  # Send heartbeat every 30 seconds
                except:
                    pass

        self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

    def stop(self):
        """Stop solving and end session."""
        self.is_running = False

        # End session
        if self.session_id:
            try:
                requests.post(f"{API_URL}/api/session/end",
                            json={"session_id": self.session_id},
                            timeout=5)
            except:
                pass

            self.session_id = None

        # ... existing stop logic ...
```

---

## Feature 5: Admin Security Enhancement

**NEW SECTION** - Strengthen admin authentication beyond basic password.

### Implementation Steps

**File:** `c:\Users\PC\Mcgraw-Solver\server\app.py`

**Add JWT-based admin authentication:**
```python
import jwt
from functools import wraps
from datetime import datetime, timedelta

JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-secret-key")  # Add to Railway env vars
JWT_ALGORITHM = "HS256"

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    """Admin login endpoint - returns JWT token."""
    data = request.get_json()
    password = data.get("password")

    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

    if password == ADMIN_PASSWORD:
        # Generate JWT token
        token = jwt.encode({
            "admin": True,
            "exp": datetime.utcnow() + timedelta(hours=24)
        }, JWT_SECRET, algorithm=JWT_ALGORITHM)

        return jsonify({"token": token})
    else:
        return jsonify({"error": "Invalid password"}), 401

def require_admin_auth(f):
    """Decorator to require JWT authentication for admin endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")

        if not token:
            return jsonify({"error": "No token provided"}), 401

        # Remove 'Bearer ' prefix if present
        if token.startswith("Bearer "):
            token = token[7:]

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if not payload.get("admin"):
                return jsonify({"error": "Not authorized"}), 403
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)

    return decorated

# Update all admin endpoints to use decorator:
# @app.route("/api/admin/orders", methods=["GET"])
# @require_admin_auth
# def get_admin_orders():
#     ...
```

**Add PyJWT to requirements:**
```
# server/requirements.txt
PyJWT>=2.8.0
```

**Update admin panel to use JWT:**
**File:** `c:\Users\PC\Mcgraw-Solver\docs\admin.js`
```javascript
let adminToken = null;

async function login() {
  const password = document.getElementById('admin-password').value;

  const response = await fetch(`${API_URL}/api/admin/login`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({password})
  });

  if (response.ok) {
    const data = await response.json();
    adminToken = data.token;
    localStorage.setItem('adminToken', adminToken);
    showAdminPanel();
  } else {
    alert('Invalid password');
  }
}

// Update all admin API calls to include token:
async function loadPendingOrders() {
  const response = await fetch(`${API_URL}/api/admin/orders`, {
    headers: {
      'Authorization': `Bearer ${adminToken}`
    }
  });
  // ...
}
```

---

## Environment Variables Checklist

```bash
# Existing (already configured)
DATABASE_URL=postgresql://...
ADMIN_PASSWORD=...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
EMAILJS_SERVICE_ID=...
EMAILJS_TEMPLATE_ID=...
EMAILJS_ADMIN_TEMPLATE_ID=...
EMAILJS_PUBLIC_KEY=...
EMAILJS_PRIVATE_KEY=...
ADMIN_EMAIL=...
DOWNLOAD_URL=...
RATE_LIMIT=120

# **NEW** (need to add)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_WEEKLY=price_...
STRIPE_PRICE_MONTHLY=price_...
STRIPE_PRICE_SEMESTER=price_...
STRIPE_MODE=live  # or 'test' for development
FRONTEND_URL=https://fanexllc.github.io
JWT_SECRET=<generate-random-secret>  # For admin JWT tokens
```

**Generate JWT secret:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Implementation Order

### Phase 1: Database & Environment Setup ⏱️ 2-3 hours
1. Create Stripe Price objects in Stripe Dashboard
2. Add all new environment variables to Railway
3. Run `python server/migrate.py` to create new tables
4. Verify database migration successful
5. **Checkpoint:** Database ready with new schema

### Phase 2: Stripe Backend Integration ⏱️ 4-5 hours
1. Add `stripe>=7.0.0` and `PyJWT>=2.8.0` to requirements.txt
2. Update `app.py`: Add all Stripe endpoints, webhook handler, payment validation
3. Update `email_service.py`: New pricing, Venmo-only admin notifications
4. Create `retry_emails.py` cron script
5. Create `cleanup_sessions.py` cron script
6. Deploy backend changes to Railway
7. Configure Stripe webhook in Stripe Dashboard
8. Set up Railway cron jobs
9. **Checkpoint:** Test Stripe checkout in test mode

### Phase 3: Frontend Updates ⏱️ 3-4 hours
1. Update `index.html`: New pricing cards, payment selector, AI comparison table, refund policy
2. Update `app.js`: Stripe checkout functions, success handler
3. Update `admin.html` & `admin.js`: Payment method columns, Sync button, JWT auth
4. Deploy frontend to GitHub Pages
5. **Checkpoint:** Test full Stripe checkout flow (test mode)

### Phase 4: AI Model Tiers ⏱️ 3-4 hours
1. Update `config.py`: Add get_default_model_for_plan(), MODEL_DISPLAY_NAMES
2. Update `app.py`: Model enforcement, preference endpoint, grace period logic
3. Update `gui.py`: Model dropdown, preference saving, upgrade error dialog
4. Update `main.py`: Session start time, model selection, error handling
5. **Checkpoint:** Test model enforcement (weekly=mini, monthly=4o, semester=claude)

### Phase 5: Loading Indicator ⏱️ 2-3 hours
1. Update `gui.py`: Progress bar component, generic messages
2. Update `human.py`: Add progress callbacks to delay functions
3. Update `main.py`: Integrate progress callbacks
4. **Checkpoint:** Test progress bar during automation

### Phase 6: Session Management ⏱️ 2-3 hours
1. Update `db.py`: Add session management functions
2. Update `app.py`: Add session endpoints
3. Update `main.py`: Session start, heartbeat, cleanup
4. **Checkpoint:** Test one-device-at-a-time enforcement

### Phase 7: Testing & Launch ⏱️ 3-4 hours
1. Run all test cases (see testing section below)
2. Switch Stripe from test mode to live mode
3. Update STRIPE_MODE environment variable
4. Test one live transaction (small amount)
5. Monitor logs for errors
6. **Launch:** Announce new features to users

**Total Estimated Time:** 19-26 hours

---

## Testing Checklist

### Stripe Integration
- [ ] Create test Stripe checkout session (weekly plan)
- [ ] Complete payment with test card 4242 4242 4242 4242
- [ ] Verify webhook receives checkout.session.completed
- [ ] Verify payment amount validation works
- [ ] Verify order auto-approved in database
- [ ] Verify key generated and stored
- [ ] Verify email sent with key
- [ ] Verify admin panel shows "Stripe" badge
- [ ] Test duplicate webhook (should be idempotent)
- [ ] Test invalid webhook signature (should reject)
- [ ] Test wrong payment amount (should reject)
- [ ] Test "Sync from Stripe" button for failed webhook

### Venmo Regression
- [ ] Submit Venmo order at new prices ($10/$25/$50)
- [ ] Verify admin receives notification email (Stripe orders should NOT trigger admin email)
- [ ] Verify admin can approve manually
- [ ] Verify customer receives key email after approval

### AI Model Tiers
- [ ] Weekly key: Can only use GPT-4o-mini, blocked from others
- [ ] Monthly key: Can choose GPT-4o or mini (dropdown shows 2 options)
- [ ] Semester key: Can choose all 3 models (dropdown shows 3 options)
- [ ] Model preference persists after logout/login
- [ ] Server rejects unauthorized model requests
- [ ] Upgrade error dialog appears when blocked

### Session Management
- [ ] Start session on device A
- [ ] Start session on device B with same key
- [ ] Verify device A is disconnected
- [ ] Heartbeat keeps session alive
- [ ] Session expires after 60s of no heartbeat
- [ ] Stop button ends session cleanly

### Grace Period
- [ ] Start session before key expires
- [ ] Key expires mid-session
- [ ] Verify can continue for 5 hours
- [ ] Verify blocked after 5-hour grace period
- [ ] New session with expired key blocked immediately

### Loading Indicator
- [ ] Progress bar appears during delays
- [ ] Messages are generic (no specific timing)
- [ ] Progress completes smoothly
- [ ] Stop button resets progress

### Email Retry
- [ ] Simulate email failure
- [ ] Verify added to retry queue
- [ ] Wait 1 hour, verify retry attempt
- [ ] Verify admin notified after 5 failed attempts

### Admin Security
- [ ] Admin login returns JWT token
- [ ] Admin endpoints reject requests without token
- [ ] Admin endpoints reject expired tokens
- [ ] Token expires after 24 hours

---

## Rollback Plan

### If Critical Issues Arise

**Database:**
- Migrations are additive (ADD COLUMN IF NOT EXISTS)
- Can safely rollback code without breaking existing data
- New columns will be ignored by old code

**Stripe:**
- Disable Stripe option in frontend (hide payment selector)
- Venmo continues working normally
- Can disable webhook in Stripe dashboard

**AI Model Tiers:**
- Revert to hardcoded Claude model in config.py
- Remove model enforcement from /api/solve
- All users get same model as before

**Session Management:**
- Remove session checks from client
- Server endpoints can remain (won't be called)
- Unlimited concurrent sessions allowed (like before)

**Command to rollback Railway deployment:**
```bash
railway rollback <previous-deployment-id>
```

---

## Success Metrics

Track these KPIs post-launch:

- **Stripe Adoption Rate:** % of new orders using Stripe vs Venmo
- **Weekly Plan Uptake:** Number of weekly plan purchases (new revenue stream)
- **Premium Plan Conversion:** % of users choosing semester plan (highest margin)
- **Manual Admin Time:** Reduction in manual approval time (target: 80% reduction)
- **Support Tickets:** Reduction in "is it working?" questions (target: 50% reduction)
- **Email Delivery:** % of emails delivered on first attempt (target: >95%)
- **Session Conflicts:** Number of multi-device lockouts (monitor for legitimate use cases)

---

## Post-Launch Monitoring

**Week 1:**
- Monitor Stripe webhook delivery (check Railway logs)
- Monitor email retry queue (should be mostly empty)
- Check for Stripe payment amount mismatches (should be zero)
- Monitor session conflicts (adjust timeout if needed)

**Week 2-4:**
- Analyze plan distribution (weekly vs monthly vs semester)
- Review admin panel usage of "Sync from Stripe" button
- Check model preference distribution
- Review support tickets for confusion points

**Month 2:**
- Calculate revenue vs old pricing model
- Analyze refund requests (should be minimal)
- Review email deliverability rates
- Consider A/B testing plan descriptions

---

## Notes & Considerations

1. **Stripe Test Mode:** Use test keys during development. Switch to live keys only after thorough testing.
2. **Webhook Reliability:** Stripe webhooks are critical. Ensure server returns 200 quickly (<5s) or Stripe will retry.
3. **Email Deliverability:** Monitor EmailJS quota. Consider migrating to SendGrid/Mailgun as volume grows.
4. **AI Model Costs:** Claude Sonnet is more expensive than GPT-4o. Monitor API costs and ensure semester plan pricing covers costs.
5. **Loading Indicator:** Use generic messages to avoid revealing automation mechanics.
6. **Session Management:** 60s timeout is aggressive. Monitor for legitimate multi-device users (e.g., desktop + laptop).
7. **Payment Method Marketing:** Promote Stripe as "instant access" to drive adoption.
8. **Security:** Never commit API keys. Use environment variables. Verify webhook signatures.
9. **Model Comparison:** Using qualitative ratings (Good/Very Good/Excellent) avoids accuracy claims.
10. **Grace Period:** Only for active sessions prevents abuse of grace period by restarting app.

---

**CTO APPROVAL:** ✅ APPROVED - Ready for implementation with all modifications incorporated

**Next Steps:**
1. Review updated plan with team
2. Set up Stripe account and create Price objects
3. Begin Phase 1 implementation
4. Schedule deployment for low-traffic window

---

**Document Version:** 2.0 (CTO Approved)
**Last Updated:** 2026-02-15
**Estimated Completion:** 19-26 hours across 7 phases
