# McGraw Solver - Complete Deployment Checklist

## Phase 3 Implementation Status

✅ **Completed:**
- Dual payment system (Stripe + Venmo)
- Tiered pricing (Weekly/Monthly/Semester)
- AI model tiers (GPT-4o-mini, GPT-4o, Claude Sonnet)
- Session management (one-device-at-a-time)
- Admin JWT authentication
- Stripe webhook handling
- Email retry queue system
- Session cleanup system
- **Bug fixes:** Stripe redirect URL, Admin login endpoint

⏭️ **Ready to Deploy:**
- Cron jobs for session cleanup
- Email retry automation (optional)

---

## Quick Deployment Steps

### 1. Deploy Backend Fixes to Railway

```bash
# Commit the Phase 3 fixes
git add server/app.py .env.example docs/
git commit -m "Phase 3: Fix Stripe redirect, add admin login, prepare cron deployment"
git push origin main
```

### 2. Update Railway Environment Variables

**Main Web Service (`mcgraw-solver-production`):**

| Variable | Value | Required |
|----------|-------|----------|
| `FRONTEND_URL` | `https://fanexllc.github.io/Mcgraw-Solver` | ✅ Yes |
| `JWT_SECRET` | Generate with `python -c "import secrets; print(secrets.token_hex(32))"` | ✅ Yes |
| `DATABASE_URL` | Auto-set by Railway | ✅ Yes |
| `OPENAI_API_KEY` | Your OpenAI key | ✅ Yes |
| `ANTHROPIC_API_KEY` | Your Anthropic key | ✅ Yes |
| `ADMIN_PASSWORD` | Your admin password | ✅ Yes |
| `STRIPE_SECRET_KEY` | Your Stripe secret key | ✅ Yes |
| `STRIPE_PUBLISHABLE_KEY` | Your Stripe publishable key | ✅ Yes |
| `STRIPE_WEBHOOK_SECRET` | From Stripe dashboard | ✅ Yes |
| `STRIPE_PRICE_WEEKLY` | Stripe Price ID | ✅ Yes |
| `STRIPE_PRICE_MONTHLY` | Stripe Price ID | ✅ Yes |
| `STRIPE_PRICE_SEMESTER` | Stripe Price ID | ✅ Yes |
| `STRIPE_MODE` | `test` or `live` | Optional |
| `ADMIN_EMAIL` | Your email | Optional |

### 3. Deploy Cron Service to Railway

**Option A: Create New Railway Service (Recommended)**

1. In Railway project → "New Service" → "GitHub Repo"
2. Select same repo as main service
3. Configure:
   - **Service Name:** `mcgraw-solver-cron`
   - **Start Command:** `python server/cron.py`
   - **Build Command:** `pip install -r server/requirements.txt`
   - **Root Directory:** `server`

4. Add environment variables:
   - `DATABASE_URL` - Copy from main web service
   - `ADMIN_EMAIL` - Optional

**Option B: Use GitHub Actions**

See [CRON_DEPLOYMENT.md](./CRON_DEPLOYMENT.md#method-2-external-cron-service-alternative) for GitHub Actions setup.

### 4. Verify Deployment

**Test Stripe Checkout:**
1. Go to https://fanexllc.github.io/Mcgraw-Solver/#pricing
2. Click "Get Started" on any plan
3. Select "Pay with Stripe"
4. Use test card: `4242 4242 4242 4242`
5. ✅ Should redirect to success page (not 404)
6. ✅ Should receive email with access key

**Test Admin Login:**
1. Go to https://fanexllc.github.io/Mcgraw-Solver/admin.html
2. Enter admin password
3. ✅ Should see dashboard (not CORS error)
4. ✅ Should see orders table

**Test Cron Jobs:**
1. Check Railway logs for cron service
2. ✅ Should see "Cron scheduler started"
3. ✅ Should see "Session cleanup job" every 5 minutes
4. ✅ Active sessions should be cleaned up after 60s of no heartbeat

---

## Environment Variables Quick Reference

### Generate Secrets

```bash
# Generate JWT_SECRET
python -c "import secrets; print(secrets.token_hex(32))"

# Generate ADMIN_PASSWORD (or use your own)
python -c "import secrets; print(secrets.token_urlsafe(16))"
```

### Get Stripe Keys

1. Go to https://dashboard.stripe.com/apikeys
2. Copy:
   - **Publishable key:** `pk_test_...` or `pk_live_...`
   - **Secret key:** `sk_test_...` or `sk_live_...`

3. Create products and prices:
   - Weekly: $10.00 → Copy Price ID
   - Monthly: $25.00 → Copy Price ID
   - Semester: $50.00 → Copy Price ID

4. Set up webhook:
   - URL: `https://mcgraw-solver-production.up.railway.app/api/stripe/webhook`
   - Event: `checkout.session.completed`
   - Copy webhook secret: `whsec_...`

---

## Testing Checklist

### Payment Flow
- [ ] Stripe checkout redirects correctly after payment
- [ ] Venmo order submission shows success message
- [ ] Stripe orders auto-approve (check webhook logs)
- [ ] Venmo orders stay pending for admin approval
- [ ] Access key emails are sent successfully
- [ ] Keys work in the GUI application

### Admin Panel
- [ ] Admin login works (JWT authentication)
- [ ] Can see pending Venmo orders
- [ ] Can approve orders manually
- [ ] Can reject orders
- [ ] Can sync Stripe orders manually
- [ ] Order history displays correctly

### AI Model Tiers
- [ ] Weekly plan only allows GPT-4o-mini
- [ ] Monthly plan allows GPT-4o-mini and GPT-4o
- [ ] Semester plan allows all models (including Claude)
- [ ] GUI app respects model restrictions

### Session Management
- [ ] Only one device can use a key at a time
- [ ] Second device disconnects first device
- [ ] Sessions expire after 60s without heartbeat
- [ ] Cron job cleans up stale sessions

### Email System
- [ ] Key approval emails send successfully
- [ ] Failed emails go to retry queue
- [ ] Email retry cron processes queue (if enabled)

---

## Post-Deployment Monitoring

### Railway Dashboard
- Monitor CPU/Memory usage
- Check for crashed services
- Review deployment logs for errors

### Database Queries

```sql
-- Check active sessions (should be current users only)
SELECT COUNT(*) FROM active_sessions;

-- Check email retry queue (should be mostly empty)
SELECT COUNT(*) FROM email_retry_queue;

-- Check recent orders
SELECT id, name, plan, status, payment_method, created
FROM orders
ORDER BY created DESC
LIMIT 10;

-- Check active keys
SELECT owner, plan, created, expires, uses
FROM api_keys
WHERE expires > NOW()
ORDER BY created DESC
LIMIT 10;
```

### Logs to Watch

**Main Web Service:**
- Stripe webhook events
- Order creation and approval
- API solve requests
- Admin login attempts

**Cron Service:**
- Session cleanup activity
- Email retry attempts
- Any errors or exceptions

---

## Rollback Plan

If deployment fails:

```bash
# Revert to previous commit
git revert HEAD
git push origin main

# Or rollback to specific commit
git reset --hard <previous-commit-hash>
git push -f origin main
```

Railway will automatically redeploy the previous version.

---

## Documentation Reference

- [FIXES_APPLIED.md](./FIXES_APPLIED.md) - Recent bug fixes (Stripe redirect, admin login)
- [CRON_DEPLOYMENT.md](./CRON_DEPLOYMENT.md) - Detailed cron job setup
- [IMPLEMENTATION_PLAN_UPDATED.md](./IMPLEMENTATION_PLAN_UPDATED.md) - Complete Phase 3 plan
- [PHASE_1_SETUP.md](./PHASE_1_SETUP.md) - Initial database setup

---

## Support & Troubleshooting

### Common Issues

**Issue:** Stripe checkout shows 404
- **Fix:** Update `FRONTEND_URL` to include `/Mcgraw-Solver` path

**Issue:** Admin login fails with CORS error
- **Fix:** Deploy updated backend with JWT login endpoint, add `JWT_SECRET`

**Issue:** Sessions not cleaning up
- **Fix:** Deploy cron service with `DATABASE_URL` configured

**Issue:** Emails not sending
- **Fix:** Check EmailJS credentials in email_service.py

**Issue:** Stripe webhook not working
- **Fix:** Verify webhook secret matches, check event type is `checkout.session.completed`

---

## Final Steps

1. ✅ Deploy backend with fixes
2. ✅ Update environment variables on Railway
3. ✅ Deploy cron service
4. ✅ Test all payment flows
5. ✅ Test admin panel
6. ✅ Monitor logs for 24 hours
7. ✅ Update Stripe to live mode (when ready for production)

**Phase 3 Complete! 🎉**
