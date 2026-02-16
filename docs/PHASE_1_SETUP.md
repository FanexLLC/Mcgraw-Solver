# Phase 1: Database & Environment Setup Guide

This guide walks through the setup steps for Phase 1 of the McGraw Solver feature implementation.

## Step 1: Create Stripe Price Objects

Before adding environment variables, you need to create Price objects in your Stripe Dashboard.

### Instructions:

1. **Log in to Stripe Dashboard**: https://dashboard.stripe.com/
2. **Navigate to Products**: Click "Products" in the left sidebar
3. **Create Product for Weekly Plan**:
   - Click "+ Add product"
   - Name: "McGraw Solver - Weekly Plan"
   - Description: "7-day access with GPT-4o-mini AI model"
   - Pricing model: One time
   - Price: $10.00 USD
   - Click "Save product"
   - **Copy the Price ID** (format: `price_xxxxxxxxxxxxx`)

4. **Create Product for Monthly Plan**:
   - Click "+ Add product"
   - Name: "McGraw Solver - Monthly Plan"
   - Description: "30-day access with GPT-4o AI model"
   - Pricing model: One time
   - Price: $25.00 USD
   - Click "Save product"
   - **Copy the Price ID** (format: `price_xxxxxxxxxxxxx`)

5. **Create Product for Semester Plan**:
   - Click "+ Add product"
   - Name: "McGraw Solver - Semester Plan"
   - Description: "120-day access with Claude Sonnet 4.5 AI model"
   - Pricing model: One time
   - Price: $50.00 USD
   - Click "Save product"
   - **Copy the Price ID** (format: `price_xxxxxxxxxxxxx`)

6. **Save all three Price IDs** - you'll need them for the environment variables

---

## Step 2: Add Environment Variables to Railway

Add the following NEW environment variables to your Railway project:

### Required Stripe Variables

```bash
# Stripe API Keys (get from: https://dashboard.stripe.com/apikeys)
STRIPE_SECRET_KEY=sk_test_...                    # Use sk_test_... for testing, sk_live_... for production
STRIPE_PUBLISHABLE_KEY=pk_test_...               # Use pk_test_... for testing, pk_live_... for production

# Stripe Price IDs (from Step 1 above)
STRIPE_PRICE_WEEKLY=price_xxxxxxxxxxxxx          # Weekly plan Price ID
STRIPE_PRICE_MONTHLY=price_xxxxxxxxxxxxx         # Monthly plan Price ID
STRIPE_PRICE_SEMESTER=price_xxxxxxxxxxxxx        # Semester plan Price ID

# Stripe Webhook Secret (configured in Step 4)
STRIPE_WEBHOOK_SECRET=whsec_...                  # Will be generated when you create webhook  #missing currently  

# Stripe Mode
STRIPE_MODE=test                                 # Use 'test' for development, 'live' for production
```

### Required Security Variable

```bash
# JWT Secret for Admin Authentication
JWT_SECRET=<GENERATE_RANDOM_SECRET>              # Generate a strong random secret (32+ characters)
```

**How to generate JWT_SECRET:**
```bash
# Option 1: Using Python
python -c "import secrets; print(secrets.token_hex(32))"

# Option 2: Using OpenSSL
openssl rand -hex 32

# Option 3: Using Node.js
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

### Other Required Variables

```bash
# Frontend URL (already configured, verify it's correct)
FRONTEND_URL=https://fanexllc.github.io
```

---

## Step 3: Run Database Migration

After adding the environment variables to Railway, run the migration script to update your database schema.

### Local Testing (Recommended First):

**For PowerShell (Windows):**
```powershell
# Set your production DATABASE_URL temporarily
$env:DATABASE_URL="postgresql://user:pass@host:port/database"

# Run the migration
python server/migrate.py
```

**For Bash (Mac/Linux):**
```bash
# Set your production DATABASE_URL temporarily
export DATABASE_URL="postgresql://user:pass@host:port/database"

# Run the migration
python server/migrate.py
```

### Expected Output:

```
McGraw Solver - Database Migration Script
==================================================
Connecting to database...
✓ Connected successfully

=== Starting Database Migration ===

1. Adding payment_method and stripe_session_id columns to orders table...
   ✓ Columns added successfully
2. Adding preferred_model column to keys table...
   ✓ Column added successfully
3. Creating email_retry_queue table...
   ✓ email_retry_queue table created
4. Creating active_sessions table...
   ✓ active_sessions table created
5. Creating database indexes...
   ✓ Indexes created successfully

=== Verifying Migration ===

✓ Orders table columns: payment_method, stripe_session_id
✓ Keys table columns: preferred_model
✓ email_retry_queue table exists: True
✓ active_sessions table exists: True
✓ Indexes created: idx_orders_stripe_session, idx_sessions_heartbeat, idx_sessions_key

=== Migration Completed Successfully ===

Timestamp: 2026-02-15T12:00:00Z

Next steps:
1. Deploy updated application code to Railway
2. Configure Stripe webhook in Stripe Dashboard
3. Add new environment variables to Railway
4. Test Stripe checkout in test mode
```

---

## Step 4: Configure Stripe Webhook (After Phase 2 deployment)

**Note**: This step should be done AFTER deploying the Phase 2 backend code to Railway.

1. Go to Stripe Dashboard → Developers → Webhooks
2. Click "+ Add endpoint"
3. Enter endpoint URL: `https://your-railway-domain.railway.app/api/stripe-webhook`
4. Select events to listen to:
   - ✓ `checkout.session.completed`
5. Click "Add endpoint"
6. Copy the **webhook signing secret** (format: `whsec_...`)
7. Add it to Railway environment variables as `STRIPE_WEBHOOK_SECRET`

---

## Verification Checklist

Before proceeding to Phase 2, verify:

- [ ] All three Stripe Price objects created
- [ ] All three Price IDs copied and saved
- [ ] Stripe API keys added to Railway (test mode for now)
- [ ] JWT_SECRET generated and added to Railway
- [ ] Database migration completed successfully
- [ ] All new tables created (email_retry_queue, active_sessions)
- [ ] All indexes created (idx_orders_stripe_session, idx_sessions_heartbeat, idx_sessions_key)
- [ ] New columns added to orders table (payment_method, stripe_session_id)
- [ ] New column added to keys table (preferred_model)

---

## Current Environment Variables Summary

### Existing Variables (Already Configured):
```bash
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
```

### New Variables (Added in Phase 1):
```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_WEEKLY=price_...
STRIPE_PRICE_MONTHLY=price_...
STRIPE_PRICE_SEMESTER=price_...
STRIPE_MODE=test
JWT_SECRET=<random-secret-here>
```

---

## Troubleshooting

### Migration Fails with "relation already exists"
This is normal if you're re-running the migration. The script uses `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ADD COLUMN IF NOT EXISTS`, so it's safe to run multiple times.

### Can't connect to database
- Verify `DATABASE_URL` is set correctly
- Check if your IP is whitelisted in Railway/database provider
- Ensure database is running and accessible

### Stripe API keys not working
- Make sure you're using the correct mode (test vs live)
- Verify keys are copied completely (they're very long strings)
- Check that keys match the mode (sk_test_... for test mode, sk_live_... for live mode)

---

## Next Steps

After completing Phase 1, proceed to **Phase 2: Stripe Backend Integration** which includes:
1. Adding `stripe>=7.0.0` and `PyJWT>=2.8.0` to requirements.txt
2. Updating `app.py` with Stripe endpoints and webhook handler
3. Updating `email_service.py` with new pricing
4. Creating cron scripts for email retry and session cleanup
5. Deploying backend changes to Railway
6. Configuring Stripe webhook
7. Testing Stripe checkout in test mode
