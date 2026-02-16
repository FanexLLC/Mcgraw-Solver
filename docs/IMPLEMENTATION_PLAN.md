# McGraw Solver - Feature Implementation Plan

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
- **Refunds**: No refunds policy (state clearly on website)

### Implementation Steps

#### 1.1 Database Migration
**File:** `c:\Users\PC\Mcgraw-Solver\server\db.py`

**Changes:**
- Add `payment_method` column (TEXT, default 'venmo') to orders table
- Add `stripe_session_id` column (TEXT, nullable) to orders table
- Update `PLAN_DURATIONS` to add weekly plan:
  ```python
  PLAN_DURATIONS = {
      "weekly": 7,
      "monthly": 30,
      "semester": 120
  }
  ```
- Add migration SQL:
  ```sql
  ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method TEXT DEFAULT 'venmo';
  ALTER TABLE orders ADD COLUMN IF NOT EXISTS stripe_session_id TEXT;
  ```
- Update `create_order()` to accept `payment_method` and `stripe_session_id` parameters
- Add helper function `find_order_by_stripe_session(session_id)` for webhook lookups
- Update `list_orders()` and `find_order()` to return new fields

#### 1.2 Backend Stripe Integration
**File:** `c:\Users\PC\Mcgraw-Solver\server\requirements.txt`
- Add dependency: `stripe>=7.0.0`

**File:** `c:\Users\PC\Mcgraw-Solver\server\app.py`

**Environment Variables (add to Railway/production):**
```bash
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
FRONTEND_URL=https://fanexllc.github.io
```

**New Code:**
- Import stripe SDK and initialize with `STRIPE_SECRET_KEY`
- Define `STRIPE_PRICES` constant:
  ```python
  STRIPE_PRICES = {
      "weekly": 1000,    # $10.00
      "monthly": 2500,   # $25.00
      "semester": 5000   # $50.00
  }
  ```

**New Endpoint 1: `POST /api/orders/stripe`**
- Purpose: Create Stripe Checkout Session
- Validates: name, email, plan (required); referral (optional)
- Creates pending order with `payment_method='stripe'`
- Creates Stripe Checkout Session with:
  - Line item: Plan name and price from `STRIPE_PRICES`
  - Metadata: `order_id`, `plan`
  - Success URL: `{FRONTEND_URL}/success?session_id={CHECKOUT_SESSION_ID}`
  - Cancel URL: `{FRONTEND_URL}/`
- Returns: `{"session_url": "https://checkout.stripe.com/..."}`

**New Endpoint 2: `POST /api/stripe/webhook`**
- Purpose: Handle Stripe webhook events (auto-approve orders)
- Verifies webhook signature using `stripe.Webhook.construct_event()`
- Handles `checkout.session.completed` event:
  1. Extract `order_id` from session metadata
  2. Find order by `order_id`
  3. Check if already approved (idempotency)
  4. Generate access key via `generate_key_with_expiry(name, plan)`
  5. Update order: status='approved', key=generated_key, approved_at=now
  6. Send key email via `send_key_email()`
  7. Return 200 OK (critical for Stripe retry logic)
- Returns 400 for invalid signatures, 500 for errors (triggers Stripe retry)

**New Endpoint 3: `GET /api/config/stripe`**
- Purpose: Provide Stripe publishable key to frontend
- No authentication required (public endpoint)
- Returns: `{"publishable_key": STRIPE_PUBLISHABLE_KEY}`

**Security Measures:**
- Webhook signature verification prevents spoofed payment confirmations
- Idempotency check prevents duplicate key generation
- Stripe session ID validation ensures payment actually completed
- Never expose secret key to frontend

#### 1.3 Email Service Updates
**File:** `c:\Users\PC\Mcgraw-Solver\server\email_service.py`

**Changes:**
- Update price display logic in `send_key_email()`:
  ```python
  PLAN_DISPLAY = {
      "weekly": "Weekly ($10)",
      "monthly": "Monthly ($25)",
      "semester": "Semester ($50)"
  }
  ```
- Add `payment_method` parameter to differentiate email templates (optional enhancement)
- Update `send_admin_order_notification()` to show payment method (only send for Venmo orders to reduce admin email volume)
- Add email retry mechanism: Store failed email attempts in database, retry hourly for 24 hours
- Create `email_retry_queue` table:
  ```sql
  CREATE TABLE IF NOT EXISTS email_retry_queue (
      id SERIAL PRIMARY KEY,
      order_id TEXT,
      email_type TEXT,  -- 'key_email' or 'admin_notification'
      recipient TEXT,
      template_params JSON,
      attempts INTEGER DEFAULT 0,
      last_attempt TIMESTAMP,
      created TIMESTAMP
  )
  ```

#### 1.4 Frontend Checkout Modal
**File:** `c:\Users\PC\Mcgraw-Solver\docs\index.html`

**Changes to pricing section:**
- Update existing monthly price: ~~$25~~ → **$20** becomes ~~$30~~ → **$25**
- Update existing semester price: ~~$75~~ → **$50** stays at **$50**
- Add new weekly plan card:
  ```html
  <div class="pricing-card">
    <h3>Weekly</h3>
    <div class="price">
      <span class="price-strike">$12</span>
      <span class="price-current">$10</span>
      <span class="price-period">/week</span>
    </div>
    <span class="badge">Try It Out</span>
    <ul>
      <li>Full access to SmartBook Solver</li>
      <li>All question types supported</li>
      <li>Speed & accuracy controls</li>
      <li>7 days of access</li>
    </ul>
    <button onclick="openCheckout('weekly')">Get Weekly</button>
  </div>
  ```

**Changes to checkout modal:**
- Add payment method selector at top of modal:
  ```html
  <div class="payment-method-selector">
    <label class="payment-option active">
      <input type="radio" name="payment-method" value="stripe" checked>
      <span>💳 Credit/Debit Card</span>
      <span class="badge-small">Instant Access</span>
    </label>
    <label class="payment-option">
      <input type="radio" name="payment-method" value="venmo">
      <span>📱 Venmo</span>
      <span class="badge-small">Manual Approval</span>
    </label>
  </div>
  ```

- Create two conditional form sections:
  - **Stripe fields** (shown by default): Name, Email, Referral, "Pay with Stripe" button
  - **Venmo fields** (hidden by default): All existing fields including Venmo username, Transaction ID

- Add success page for Stripe redirects (detect `?session_id=xxx` query param)

#### 1.5 Frontend JavaScript
**File:** `c:\Users\PC\Mcgraw-Solver\docs\app.js`

**New Functions:**
```javascript
// Toggle between Stripe and Venmo form fields
function togglePaymentMethod() {
  const method = document.querySelector('input[name="payment-method"]:checked').value;
  document.getElementById('stripe-fields').style.display = method === 'stripe' ? 'block' : 'none';
  document.getElementById('venmo-fields').style.display = method === 'venmo' ? 'block' : 'none';
}

// Submit Stripe order and redirect to checkout
async function submitStripeOrder(e) {
  e.preventDefault();
  const name = document.getElementById('checkout-name').value.trim();
  const email = document.getElementById('checkout-email').value.trim();
  const referral = document.getElementById('checkout-referral').value.trim();
  const plan = currentPlan; // Set by openCheckout()

  // Validate fields
  if (!name || !email) {
    showError('Please fill in all required fields');
    return;
  }

  // Create checkout session
  const response = await fetch(`${API_URL}/api/orders/stripe`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, email, plan, referral})
  });

  const data = await response.json();
  if (data.session_url) {
    window.location.href = data.session_url; // Redirect to Stripe
  } else {
    showError('Failed to create checkout session');
  }
}

// Handle success page (detect Stripe redirect)
function handleStripeSuccess() {
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has('session_id')) {
    showSuccessMessage('Payment successful! Check your email for your access key and download link.');
  }
}
```

**Updated Functions:**
- `openCheckout(plan)`: Accept weekly/monthly/semester, set default payment method to 'stripe'
- Page load: Call `handleStripeSuccess()` to detect Stripe redirects

#### 1.6 Admin Panel Updates
**File:** `c:\Users\PC\Mcgraw-Solver\docs\admin.html`

**Changes:**
- Add "Payment Method" column to pending orders table
- Add "Payment Method" column to order history table
- Display payment method as badges:
  ```html
  <span class="badge badge-stripe">Stripe ✓</span>
  <span class="badge badge-venmo">Venmo</span>
  ```
- For Stripe orders in pending table: Show "Auto-approved" instead of approve/reject buttons (they're already approved via webhook)
- Add "Sync from Stripe" button for pending Stripe orders (in case webhook failed)
  - Fetches payment status from Stripe API
  - Auto-approves if payment was successful
  - Shows error if payment failed or doesn't exist
- Update table fetch to display new fields

#### 1.7 Stripe Dashboard Configuration
**Post-deployment steps:**
1. Go to Stripe Dashboard → Developers → Webhooks
2. Add endpoint: `https://mcgraw-solver-production.up.railway.app/api/stripe/webhook`
3. Select event: `checkout.session.completed`
4. Copy webhook signing secret to `STRIPE_WEBHOOK_SECRET` environment variable
5. Test with Stripe CLI locally: `stripe listen --forward-to localhost:8080/api/stripe/webhook`

---

## Feature 2: Enhanced Plan Descriptions & AI Model Tiers

### Overview
Improve plan descriptions to clearly communicate value differences. Implement AI model access tiers where Weekly plans use GPT-4o-mini, Monthly plans get GPT-4o-mini and GPT-4o, and Semester plan gets all models including premium Claude Sonnet 4.5.

### Edge Cases & Decisions
- **Existing keys**: Auto-upgrade based on plan tier (monthly → GPT-4o, semester → Claude)
- **Unauthorized model access**: Show error message in GUI with "Upgrade Plan" button linking to website
- **Model selection**: Add dropdown in GUI for semester users to choose model (Claude/GPT-4o/mini)
- **Model preference**: Save user's selected model server-side per key (syncs across devices)
- **Model identifiers**: Use 'gpt-4o' and 'gpt-4o-mini' (OpenAI routes to latest version)
- **Key expiration**: Check on every question with 5-hour grace period after expiration

### Implementation Steps

#### 2.1 Website Plan Descriptions
**File:** `c:\Users\PC\Mcgraw-Solver\docs\index.html`

**Enhanced feature lists:**

**Weekly Plan ($10/week):**
- ✓ Full access to SmartBook Solver
- ✓ All question types supported (MCQ, Ordering, Matching, Fill-in, Multi-part)
- ✓ Customizable speed & accuracy settings
- ✓ GPT-4o-mini AI model
- ✓ 7 days of access
- ✓ Perfect for trying out the software

**Monthly Plan ($25/month):**
- ✓ Everything in Weekly
- ✓ Save $15 vs. weekly
- ✓ **GPT-4o and GPT-4o-mini AI models**
- ✓ 30 days of access
- ✓ Email support
- ✓ Best for single-term courses

**Semester Plan ($50/semester) [BEST VALUE]:**
- ✓ Everything in Monthly
- ✓ **All AI models: Claude Sonnet 4.5, GPT-4o, GPT-4o-mini**
- ✓ **Premium Claude Sonnet 4.5** (most accurate, fastest)
- ✓ Save $30 vs. weekly, $25 vs. buying monthly twice
- ✓ 120 days of access (~4 months)
- ✓ Priority email support
- ✓ Best for full semester coverage
- ✓ Most popular choice

**Add comparison section:**
```html
<div class="ai-model-comparison">
  <h3>AI Model Comparison</h3>
  <table>
    <tr>
      <th>Feature</th>
      <th>GPT-4o-mini<br/>(Weekly)</th>
      <th>GPT-4o<br/>(Monthly)</th>
      <th>Claude Sonnet 4.5<br/>(Semester)</th>
    </tr>
    <tr>
      <td>Answer Accuracy</td>
      <td>~85-90%</td>
      <td>~90-95%</td>
      <td>~95-98%</td>
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
      <td>GPT-4o-mini</td>
      <td>GPT-4o, GPT-4o-mini</td>
      <td>All models</td>
    </tr>
  </table>
</div>
```

#### 2.2 Server-Side AI Model Enforcement
**File:** `c:\Users\PC\Mcgraw-Solver\server\app.py`

**Changes to `/api/solve` endpoint (the endpoint that processes questions):**

Add logic to restrict AI model based on plan tier:
```python
@app.route("/api/solve", methods=["POST"])
def solve_question():
    # ... existing key validation code ...

    key_data = find_key(access_key)

    # Check expiration with 5-hour grace period
    if key_data.get("expires"):
        expiry = datetime.fromisoformat(key_data["expires"].rstrip("Z"))
        grace_period = timedelta(hours=5)
        if datetime.utcnow() > expiry + grace_period:
            return jsonify({"error": "Access key expired"}), 403

    requested_model = data.get("model", "")

    # Determine allowed models based on plan
    allowed_models = get_allowed_models(key_data["plan"])

    # If user requests a model they don't have access to, return error
    if requested_model not in allowed_models:
        return jsonify({
            "error": "model_not_allowed",
            "message": f"Your {key_data['plan']} plan does not include access to {requested_model}",
            "allowed_models": allowed_models,
            "upgrade_url": f"{FRONTEND_URL}/#pricing"
        }), 403

    model = requested_model

    # ... rest of solve logic ...

def get_allowed_models(plan):
    """Return list of allowed AI models based on plan tier."""
    if plan == "semester":
        return ["claude-sonnet-4-5-20250929", "gpt-4o", "gpt-4o-mini"]  # All models
    elif plan == "monthly":
        return ["gpt-4o", "gpt-4o-mini"]  # GPT-4o and mini
    else:  # weekly
        return ["gpt-4o-mini"]  # Only mini
```

#### 2.3 Client-Side AI Model Selection
**File:** `c:\Users\PC\Mcgraw-Solver\config.py`

**Changes:**
- Remove hardcoded `GPT_MODEL = "claude-sonnet-4-5-20250929"`
- Add function to determine model based on plan:
  ```python
  def get_model_for_plan(plan):
      """Return the AI model to use based on subscription plan."""
      if plan == "semester":
          return "claude-sonnet-4-5-20250929"  # Premium model
      elif plan == "monthly":
          return "gpt-4o"  # Monthly gets GPT-4o
      else:  # weekly
          return "gpt-4o-mini"  # Weekly gets mini
  ```

**File:** `c:\Users\PC\Mcgraw-Solver\gui.py`

**Changes:**
- When validating access key (login page), retrieve the plan and allowed models from key validation response
- Store plan in `self._validated_plan` attribute and allowed models in `self._allowed_models`
- Add model selector dropdown to solver page (only show if user has multiple model options):
  ```python
  # Add to solver page controls section
  if len(self._allowed_models) > 1:
      self.model_label = tk.Label(controls_frame, text="AI Model:", ...)
      self.model_var = tk.StringVar(value=self._allowed_models[0])
      self.model_dropdown = ttk.Combobox(controls_frame,
                                          textvariable=self.model_var,
                                          values=self._allowed_models,
                                          state="readonly")
      # Save preference to server when changed
      self.model_dropdown.bind("<<ComboboxSelected>>", self._on_model_changed)
  ```
- Add error handling for unauthorized model access:
  ```python
  def _handle_model_error(self, error_data):
      """Show error dialog with upgrade option when model access denied."""
      message = error_data.get("message", "Model not available")
      upgrade_url = error_data.get("upgrade_url")

      dialog = tk.Toplevel(self.root)
      dialog.title("Upgrade Required")
      # ... show message and "Upgrade Plan" button that opens upgrade_url in browser
  ```
- Pass selected model to solver when starting

**File:** `c:\Users\PC\Mcgraw-Solver\main.py` (SolverApp class)

**Changes:**
- Accept plan parameter in constructor or start method
- Use `config.get_model_for_plan(plan)` to set the AI model
- Send correct model in API requests to `/api/solve`

**API Changes:**
The key validation endpoint `/api/keys/validate` should return the plan and allowed models:
```python
@app.route("/api/keys/validate", methods=["POST"])
def validate_key():
    # ... existing validation ...
    plan = key_data["plan"]
    return jsonify({
        "valid": True,
        "plan": plan,
        "allowed_models": get_allowed_models(plan),
        "preferred_model": key_data.get("preferred_model"),  # User's saved preference
        "expires": key_data["expires"],
        # ... other fields ...
    })
```

**New endpoint for saving model preference:**
```python
@app.route("/api/keys/preference", methods=["POST"])
def save_model_preference():
    """Save user's preferred AI model for their key."""
    data = request.get_json()
    access_key = data.get("access_key")
    preferred_model = data.get("preferred_model")

    key_data = find_key(access_key)
    if not key_data:
        return jsonify({"error": "Invalid key"}), 403

    # Verify model is allowed for this plan
    if preferred_model not in get_allowed_models(key_data["plan"]):
        return jsonify({"error": "Model not allowed for your plan"}), 403

    # Save preference to database
    update_key_preference(access_key, preferred_model)
    return jsonify({"success": True})
```

**Database schema update for keys table:**
```sql
ALTER TABLE keys ADD COLUMN IF NOT EXISTS preferred_model TEXT;
```

---

## Feature 3: Loading Indicator in GUI

### Overview
Add visual progress feedback during automation delays so users know the bot is actively working. The software uses human-like delays (8-28 seconds per question) which currently appear as freezing.

### Edge Cases & Decisions
- **Progress detail level**: Show specific phase (e.g., "Reading question (45 words)...", "Waiting 3.2s before next question")
- **Stop/pause behavior**: Progress bar resets when user clicks stop or pause
- **Performance**: Key validation adds ~1-5ms per question (negligible compared to AI response time)

### Implementation Steps

#### 3.1 Progress Bar Component
**File:** `c:\Users\PC\Mcgraw-Solver\gui.py`

**Add to solver page (after stats cards, before log section):**
```python
# Progress section (lines ~420-445)
progress_frame = tk.Frame(self._solver_frame, bg=_C["bg_card"],
                          highlightbackground=_C["border"], highlightthickness=1)
progress_frame.pack(fill="x", padx=20, pady=(0, 10))

# Progress label
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

# Time remaining label
self.time_remaining_label = tk.Label(progress_frame, text="",
                                      fg=_C["text_dim"], bg=_C["bg_card"],
                                      font=(_FONT, 9))
self.time_remaining_label.pack(pady=(0, 10))
```

**Add progress update methods:**
```python
def start_progress(self, message, duration_seconds):
    """Start a progress animation for a delay period."""
    self.progress_label.config(text=message)
    self.progress_var.set(0)
    self._progress_duration = duration_seconds
    self._progress_start_time = time.time()
    self._update_progress()

def _update_progress(self):
    """Update progress bar based on elapsed time."""
    if not hasattr(self, '_progress_start_time'):
        return

    elapsed = time.time() - self._progress_start_time
    progress_pct = min(100.0, (elapsed / self._progress_duration) * 100)
    self.progress_var.set(progress_pct)

    remaining = max(0, self._progress_duration - elapsed)
    self.time_remaining_label.config(text=f"{remaining:.1f}s remaining")

    if progress_pct < 100:
        self.root.after(100, self._update_progress)  # Update every 100ms
    else:
        self.time_remaining_label.config(text="")

def clear_progress(self):
    """Clear progress bar and reset to ready state."""
    self.progress_var.set(0)
    self.progress_label.config(text="Ready")
    self.time_remaining_label.config(text="")
```

#### 3.2 Integration with Delay Functions
**File:** `c:\Users\PC\Mcgraw-Solver\human.py`

**Modify delay functions to accept callback:**
```python
def random_delay(min_s, max_s, progress_callback=None):
    """Random delay between questions with optional progress callback."""
    delay = random.uniform(min_s, max_s)

    if progress_callback:
        progress_callback(f"Waiting {delay:.1f}s before next question", delay)

    logger.info(f"[delay] waiting {delay:.1f}s")
    time.sleep(delay)
    return delay

def reading_delay(text, progress_callback=None):
    """Simulate reading time based on word count with optional progress callback."""
    words = len(text.split())
    base_wpm = config.READING_WPM
    variance = config.READING_WPM_VARIANCE
    wpm = random.uniform(base_wpm - variance, base_wpm + variance)
    delay = max(1.0, min(15.0, (words / wpm) * 60))

    if progress_callback:
        progress_callback(f"Reading question ({words} words)...", delay)

    logger.info(f"[reading] {words} words, {delay:.1f}s at {wpm:.0f} wpm")
    time.sleep(delay)
    return delay
```

#### 3.3 Main Loop Integration
**File:** `c:\Users\PC\Mcgraw-Solver\main.py`

**In `_handle_question()` method, add progress callbacks:**
```python
def _handle_question(self, question_data):
    # ... existing code ...

    # Reading delay with progress
    human.reading_delay(
        question_data.question,
        progress_callback=lambda msg, dur: self._update_gui_progress(msg, dur)
    )

    # ... answer selection logic ...

    # Main delay with progress
    human.random_delay(
        config.MIN_DELAY,
        config.MAX_DELAY,
        progress_callback=lambda msg, dur: self._update_gui_progress(msg, dur)
    )

def _update_gui_progress(self, message, duration):
    """Thread-safe GUI progress update."""
    if self.gui:
        self.gui.root.after(0, lambda: self.gui.start_progress(message, duration))
```

**Key delay points to add progress feedback:**
1. Line 172: Reading delay (1-15 seconds) - "Reading question..."
2. Line 204: Main delay between questions (2-5 seconds) - "Waiting before next question..."
3. Line 192: Post-answer delay (0.5-1.5s) - "Submitting answer..."
4. Line 199: Resource review delay (1-2s) - "Reviewing resources..."

#### 3.4 Visual Design
**File:** `c:\Users\PC\Mcgraw-Solver\gui.py`

**Style the progress bar to match theme:**
```python
# Add to __init__ method, after root configuration
style = ttk.Style()
style.theme_use('clam')
style.configure("TProgressbar",
                troughcolor=_C["bg_input"],
                background=_C["cyan"],
                bordercolor=_C["border"],
                lightcolor=_C["cyan"],
                darkcolor=_C["cyan"])
```

---

## Feature 4: Venmo Automation Research (Future Task)

### Documentation
Add to project README or internal docs:

**Venmo Auto-Approval Research**
- **Status:** Not currently possible
- **Reason:** Venmo has no official API or webhook system for transaction notifications
- **Workarounds Considered:**
  - Web scraping Venmo transaction history (violates ToS, unreliable)
  - Email parsing of Venmo notification emails (fragile, spam risk)
  - Manual CSV export and upload (defeats automation purpose)
- **Recommendation:** Keep manual approval for Venmo, promote Stripe as instant-access option
- **Future:** Monitor Venmo's API roadmap for official business integrations

---

## Additional Features & Enhancements

### Referral System
- **Current implementation**: Just record-keeping
- Store referral code in database for future analysis
- No automated rewards or tracking dashboards in initial release
- Future enhancement: Add referral analytics to admin panel

### No Refunds Policy
- Add clear "No Refunds" policy to website pricing page and checkout flow
- Stripe dashboard set to "no automatic refunds"
- Admin can manually process refunds in exceptional cases (must also manually revoke key)

### Website Updates
- Add pricing page section with refund policy
- Add Terms of Service mentioning no refunds
- Update FAQ with common questions about model tiers and access

---

## Critical Files Summary

### Database & Backend
- **[c:\Users\PC\Mcgraw-Solver\server\db.py](c:\Users\PC\Mcgraw-Solver\server\db.py)** - Add payment_method and stripe_session_id to orders; add preferred_model to keys; update PLAN_DURATIONS with weekly=7; add email_retry_queue table; add find_order_by_stripe_session() and update_key_preference()
- **[c:\Users\PC\Mcgraw-Solver\server\app.py](c:\Users\PC\Mcgraw-Solver\server\app.py)** - Add 3 Stripe endpoints; add /api/keys/preference endpoint; add /api/admin/sync-stripe endpoint; implement webhook handler with signature verification; add AI model tier enforcement with 5-hour grace period; update /api/solve to return model error with upgrade URL
- **[c:\Users\PC\Mcgraw-Solver\server\email_service.py](c:\Users\PC\Mcgraw-Solver\server\email_service.py)** - Update PLAN_DISPLAY with new prices; handle weekly plan; add retry mechanism with email_retry_queue
- **[c:\Users\PC\Mcgraw-Solver\server\requirements.txt](c:\Users\PC\Mcgraw-Solver\server\requirements.txt)** - Add stripe>=7.0.0

### Frontend
- **[c:\Users\PC\Mcgraw-Solver\docs\index.html](c:\Users\PC\Mcgraw-Solver\docs\index.html)** - Add weekly plan card; update prices; add payment method selector to checkout modal; enhance plan descriptions; add AI model comparison table; add refund policy section; add terms of service
- **[c:\Users\PC\Mcgraw-Solver\docs\app.js](c:\Users\PC\Mcgraw-Solver\docs\app.js)** - Add togglePaymentMethod(); add submitStripeOrder(); add handleStripeSuccess(); update openCheckout()
- **[c:\Users\PC\Mcgraw-Solver\docs\admin.html](c:\Users\PC\Mcgraw-Solver\docs\admin.html)** - Add payment method column; add badges for Stripe/Venmo; add "Sync from Stripe" button with handler

### Client Application
- **[c:\Users\PC\Mcgraw-Solver\config.py](c:\Users\PC\Mcgraw-Solver\config.py)** - Add get_model_for_plan() function; remove hardcoded GPT_MODEL
- **[c:\Users\PC\Mcgraw-Solver\gui.py](c:\Users\PC\Mcgraw-Solver\gui.py)** - Add progress bar component; add model selector dropdown (for semester users); add upgrade error dialog; add start_progress(), _update_progress(), clear_progress(), _on_model_changed(), _handle_model_error() methods; store validated plan and allowed models; style progress bar; save model preference to server
- **[c:\Users\PC\Mcgraw-Solver\main.py](c:\Users\PC\Mcgraw-Solver\main.py)** - Add progress callbacks to delay points; use selected model from GUI; handle model_not_allowed errors
- **[c:\Users\PC\Mcgraw-Solver\human.py](c:\Users\PC\Mcgraw-Solver\human.py)** - Add progress_callback parameter to random_delay() and reading_delay()

---

## Implementation Order

### Phase 1: Database & Pricing Foundation
1. Update `db.py`: Add columns, update PLAN_DURATIONS, add migration SQL
2. Update `email_service.py`: Update PLAN_DISPLAY with new prices
3. Deploy database migration to production
4. **Checkpoint:** Verify migration succeeded, existing orders intact

### Phase 2: Stripe Backend Integration
1. Add `stripe>=7.0.0` to `requirements.txt`
2. Update `app.py`: Add Stripe endpoints, webhook handler, security checks
3. Add environment variables to Railway: STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET, FRONTEND_URL
4. Deploy backend changes
5. **Checkpoint:** Test `/api/orders/stripe` and `/api/config/stripe` endpoints

### Phase 3: Stripe Frontend & Admin
1. Update `index.html`: Add weekly plan card, update prices, add payment method selector
2. Update `app.js`: Add Stripe checkout functions, payment method toggle
3. Update `admin.html`: Add payment method column and badges
4. Deploy frontend changes
5. Configure Stripe webhook in dashboard
6. **Checkpoint:** Test full Stripe checkout flow end-to-end in test mode

### Phase 4: AI Model Tiers
1. Update `config.py`: Add get_model_for_plan() function
2. Update `app.py`: Add model enforcement in /api/solve endpoint
3. Update `app.py`: Return plan in /api/keys/validate response
4. Update `gui.py`: Store validated plan, pass to solver
5. Update `main.py`: Use model based on plan
6. Update `index.html`: Add enhanced plan descriptions and AI model comparison table
7. **Checkpoint:** Test that semester users get Claude, monthly gets GPT-4o, weekly gets GPT-4o-mini

### Phase 5: Loading Indicator
1. Update `gui.py`: Add progress bar component and methods
2. Update `human.py`: Add progress_callback parameters to delay functions
3. Update `main.py`: Add progress callbacks at key delay points
4. **Checkpoint:** Test that progress bar appears during automation delays

### Phase 6: Testing & Launch
1. Test Stripe checkout flow (test mode → live mode)
2. Test Venmo flow still works (regression test)
3. Test all 3 plans (weekly/monthly/semester)
4. Test AI model enforcement
5. Test loading indicator during automation
6. Test admin panel with mixed Stripe/Venmo orders
7. Test email delivery for both payment methods
8. Switch Stripe to live mode
9. **Launch:** Announce new pricing and payment options to users

---

## Verification & Testing

### Stripe Integration Testing
- [ ] Create test Stripe checkout session (weekly plan)
- [ ] Complete payment on Stripe checkout page (use test card 4242 4242 4242 4242)
- [ ] Verify webhook receives `checkout.session.completed` event
- [ ] Verify order auto-approved in database
- [ ] Verify key generated and stored
- [ ] Verify email sent to customer with key and download link
- [ ] Verify admin panel shows order with "Stripe" badge
- [ ] Test duplicate webhook (should be idempotent)
- [ ] Test invalid webhook signature (should reject)

### Venmo Regression Testing
- [ ] Submit Venmo order (should still work as before)
- [ ] Verify admin receives notification email
- [ ] Verify admin can approve manually
- [ ] Verify customer receives key email after approval
- [ ] Verify admin panel shows order with "Venmo" badge

### AI Model Tier Testing
- [ ] Create semester plan key, verify software uses Claude Sonnet (can access all models)
- [ ] Create monthly plan key, verify software uses GPT-4o (can access GPT-4o and GPT-4o-mini)
- [ ] Create weekly plan key, verify software uses GPT-4o-mini (only mini)
- [ ] Verify server downgrades model if client requests unauthorized model
- [ ] Verify plan descriptions accurately reflect AI model differences (weekly=mini, monthly=4o, semester=Claude)

### Loading Indicator Testing
- [ ] Start automation, verify progress bar appears during reading delay
- [ ] Verify progress bar shows accurate time remaining
- [ ] Verify progress bar appears during random delays between questions
- [ ] Verify progress bar resets after each delay completes
- [ ] Verify UI remains responsive during delays

### End-to-End User Flow
- [ ] New user visits website → sees 3 plan options (weekly/monthly/semester)
- [ ] User clicks "Get Monthly" → sees payment method selector
- [ ] User chooses Stripe → enters name/email/referral → redirects to Stripe
- [ ] User completes payment → redirects to success page
- [ ] User receives email with key and download link within 1 minute
- [ ] User downloads app, enters key, starts automation
- [ ] User sees loading indicator during automation delays
- [ ] Automation completes successfully with appropriate AI model

---

## Rollback Plan

### If Stripe Integration Issues
- Database changes are backward compatible (default 'venmo')
- Disable Stripe option in frontend (hide payment method selector)
- Stripe endpoints are new, won't affect Venmo flow
- Can disable webhook in Stripe dashboard without code changes

### If AI Model Enforcement Issues
- Revert config.py to hardcoded Claude model temporarily
- Remove model enforcement from /api/solve endpoint
- Plan descriptions are marketing copy, can be updated anytime

### If Loading Indicator Issues
- Loading indicator is purely cosmetic
- Software functions normally without it
- Can be disabled by removing progress callbacks

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

# New (need to add)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
FRONTEND_URL=https://fanexllc.github.io
```

---

## Success Metrics

- **Stripe adoption rate:** % of new orders using Stripe vs Venmo
- **Manual admin time saved:** Reduction in orders requiring manual approval
- **Revenue growth:** Track weekly plan uptake and overall revenue
- **Support ticket reduction:** Fewer "is it working?" questions due to loading indicator
- **Premium plan conversion:** % of users choosing semester plan for Claude Sonnet access

---

## Notes & Considerations

1. **Stripe Test Mode:** Use test keys during development. Switch to live keys only after thorough testing.
2. **Webhook Reliability:** Stripe webhooks are critical for auto-approval. Ensure server returns 200 quickly (under 5s) or Stripe will retry.
3. **Email Deliverability:** Monitor EmailJS quota. Consider upgrading or migrating to dedicated email service (SendGrid, Mailgun) as volume grows.
4. **AI Model Costs:** Claude Sonnet is more expensive than GPT-4o. Monitor API costs and ensure semester plan pricing covers higher costs.
5. **Loading Indicator Performance:** Use `root.after()` for thread-safe GUI updates. Avoid blocking the main thread.
6. **Payment Method Marketing:** Promote Stripe as "instant access" to drive adoption over manual Venmo flow.
7. **Referral Tracking:** Both Stripe and Venmo orders support referral field. Consider referral incentive program in future.
8. **Security:** Never commit API keys. Use environment variables. Verify webhook signatures. Validate all user inputs.

---

**Total Estimated Implementation Time:** 12-16 hours across all phases
**Priority:** High - Addresses revenue growth, operational efficiency, and user experience
**Risk Level:** Medium - Stripe integration is well-documented, but webhook handling requires careful testing
