# Stripe Auto-Approval Fix Guide

## 🔍 Problem
Stripe payments are staying in "pending" status instead of auto-approving because the webhook isn't being triggered.

## ✅ Immediate Solution: Manual Sync

### Step 1: Sync Pending Orders
1. Go to admin panel: `https://fanexllc.github.io/Mcgraw-Solver/admin.html`
2. Login with your admin password
3. Find the pending Stripe orders
4. Click **"Sync from Stripe"** button for each pending order
5. The system will:
   - Check payment status with Stripe
   - Auto-approve if payment is confirmed
   - Generate access key
   - Send email to customer

### How Sync Works
The sync endpoint (`/api/admin/sync-stripe`) does this:
```javascript
// Frontend makes this call when you click Sync button
fetch('/api/admin/sync-stripe', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer YOUR_JWT_TOKEN' },
  body: JSON.stringify({ order_id: 'order_123' })
})
```

Backend process:
1. Fetches session from Stripe API
2. Checks if payment status = "paid"
3. Validates payment amount matches plan
4. Generates access key
5. Updates order status to "approved"
6. Sends email with key

---

## 🔧 Permanent Fix: Configure Webhook

**Why webhooks aren't working:**
- Webhooks need a **publicly accessible URL**
- Local server (localhost:8080) cannot receive webhooks from Stripe
- Railway deployment URL works, but webhook must be configured in Stripe

### Step 2: Configure Stripe Webhook (Production)

#### A. Get Your Webhook URL
Your Railway backend URL:
```
https://mcgraw-solver-production.up.railway.app/api/stripe/webhook
```

#### B. Add Webhook in Stripe Dashboard
1. Go to [Stripe Dashboard → Webhooks](https://dashboard.stripe.com/test/webhooks)
2. Click **"Add endpoint"**
3. Enter endpoint URL:
   ```
   https://mcgraw-solver-production.up.railway.app/api/stripe/webhook
   ```
4. Select events to listen for:
   - ✅ `checkout.session.completed`
5. Click **"Add endpoint"**
6. Copy the **Signing secret** (starts with `whsec_...`)

#### C. Update Railway Environment Variable
1. Go to Railway Dashboard → Your Project → Variables
2. Update `STRIPE_WEBHOOK_SECRET` with the signing secret from step B.6
3. Save and redeploy

#### D. Test Auto-Approval
1. Make a new test purchase
2. Complete Stripe checkout
3. Check admin panel - order should auto-approve within seconds
4. Customer should receive email automatically

---

## 🧪 Testing Locally with ngrok

If you want to test webhooks on your local machine:

### Step 1: Install ngrok
```bash
# Download from https://ngrok.com/download
# Or via chocolatey on Windows:
choco install ngrok
```

### Step 2: Start Your Local Server
```bash
cd server
python app.py
# Server runs on http://localhost:8080
```

### Step 3: Create ngrok Tunnel
```bash
ngrok http 8080
```

You'll see output like:
```
Forwarding: https://abc123.ngrok.io -> http://localhost:8080
```

### Step 4: Configure Stripe Webhook
1. Go to Stripe Dashboard → Webhooks
2. Add endpoint: `https://abc123.ngrok.io/api/stripe/webhook`
3. Select event: `checkout.session.completed`
4. Copy the signing secret
5. Update `.env` file:
   ```
   STRIPE_WEBHOOK_SECRET=whsec_your_new_secret
   ```
6. Restart your server

### Step 5: Test
- Make a test payment
- Watch ngrok terminal for incoming webhook
- Watch server logs for processing
- Order should auto-approve

---

## 📊 Verify Webhook is Working

### Check Stripe Dashboard
1. Go to [Stripe → Webhooks](https://dashboard.stripe.com/test/webhooks)
2. Click on your endpoint
3. Check **"Recent Events"** tab
4. Look for successful deliveries (HTTP 200)

### Check Server Logs
Look for these log messages:
```
INFO: Stripe session created: cs_test_abc123 for order order_xyz
INFO: Webhook received: checkout.session.completed
INFO: Key email sent for order order_xyz
```

### Check Order in Database
Order should have:
- `status`: "approved" ✅
- `payment_method`: "stripe"
- `access_key`: Generated key
- `stripe_session_id`: Session ID

---

## 🚨 Troubleshooting

### Webhook Returns 400 Error
**Cause:** Invalid signature
**Fix:** Make sure `STRIPE_WEBHOOK_SECRET` matches the signing secret in Stripe dashboard

### Webhook Returns 404 Error
**Cause:** Wrong URL or server not running
**Fix:** Verify URL is `https://your-domain.com/api/stripe/webhook` (no trailing slash)

### Orders Still Pending After Webhook
**Causes:**
1. Payment amount doesn't match plan price
2. Payment status not "paid"
3. Metadata missing from checkout session

**Fix:** Check server logs for specific error, or use Sync button to manually approve

### Email Not Sending
**Causes:**
1. EmailJS not configured
2. Rate limiting
3. Email service error

**Fix:**
- Check `ADMIN_EMAIL` in .env
- Orders still approve (key stored in database)
- User can login to admin panel to get key manually

---

## 📝 Checklist

### For Production (Railway):
- [ ] Add webhook endpoint in Stripe dashboard
- [ ] Copy signing secret
- [ ] Update `STRIPE_WEBHOOK_SECRET` on Railway
- [ ] Redeploy Railway service
- [ ] Test with real payment
- [ ] Verify auto-approval works
- [ ] Verify email sent

### For Local Testing (ngrok):
- [ ] Install ngrok
- [ ] Start local server
- [ ] Run `ngrok http 8080`
- [ ] Add ngrok URL to Stripe webhooks
- [ ] Update `.env` with new signing secret
- [ ] Restart server
- [ ] Test payment
- [ ] Watch ngrok terminal for webhook

---

## 💡 Best Practices

1. **Use Different Webhooks for Test/Live Mode**
   - Test mode: Use ngrok or test Railway URL
   - Live mode: Use production Railway URL

2. **Monitor Webhook Health**
   - Check Stripe dashboard regularly
   - Set up alerts for failed webhooks
   - Have fallback plan (manual sync)

3. **Keep Secrets Secure**
   - Never commit webhook secrets to git
   - Rotate secrets if exposed
   - Use different secrets for test/live

4. **Test Thoroughly**
   - Test all three plans
   - Test duplicate webhooks (idempotency)
   - Test wrong payment amounts
   - Test cancelled payments

---

## 🎯 Quick Commands

### Sync a Single Order (via API)
```bash
curl -X POST https://mcgraw-solver-production.up.railway.app/api/admin/sync-stripe \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"order_id": "order_123abc"}'
```

### Check Stripe Session Status
```bash
# Via Stripe CLI (if installed)
stripe checkout sessions retrieve cs_test_abc123
```

### View Server Logs (Railway)
```bash
# In Railway dashboard → Deployments → View Logs
# Or via Railway CLI:
railway logs
```

---

**TL;DR:** Click "Sync from Stripe" button in admin panel for pending orders. Then configure webhook URL in Stripe dashboard for future auto-approvals.
