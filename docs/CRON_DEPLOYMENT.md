# Cron Jobs Deployment Guide

## Overview

Your McGraw Solver backend has two automated cron jobs:

1. **Session Cleanup** - Runs every 5 minutes to remove stale sessions
2. **Email Retry** - Runs hourly to retry failed email deliveries (currently disabled)

## Files Involved

- [server/cron.py](../server/cron.py) - Main APScheduler cron runner
- [server/cleanup_sessions.py](../server/cleanup_sessions.py) - Session cleanup worker
- [server/retry_emails.py](../server/retry_emails.py) - Email retry worker
- [server/Procfile](../server/Procfile) - Process definitions for Railway

## Current Configuration

### Session Cleanup ✅ (ENABLED)
**Schedule:** Every 5 minutes
**Function:** Removes sessions that haven't sent a heartbeat in 60+ seconds
**Why:** Enforces one-device-at-a-time session management

**How it works:**
1. Queries `active_sessions` table for sessions with `last_heartbeat < NOW() - 60 seconds`
2. Deletes stale sessions
3. Logs cleanup activity
4. Allows new sessions to start on those keys

### Email Retry ⏸️ (DISABLED)
**Schedule:** Hourly (currently commented out)
**Function:** Retries failed email deliveries up to 5 times
**Why:** Ensures users receive their access keys even if email service has temporary issues

**How it works:**
1. Queries `email_retry_queue` table for pending retries
2. Attempts to resend failed emails
3. Tracks retry attempts (max 5 attempts in 24 hours)
4. Notifies admin if email fails after 5 attempts
5. Deletes successfully sent emails from queue

## Railway Deployment

### Method 1: Using Railway's Cron Service (Recommended)

Railway supports running multiple processes from a Procfile. Your [Procfile](../server/Procfile) already defines:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT
cron: python cron.py
```

**Steps:**

1. **Push your code to Railway:**
   ```bash
   git add .
   git commit -m "Add cron jobs for session cleanup and email retry"
   git push origin main
   ```

2. **Create a new Railway service for cron jobs:**
   - Go to your Railway project
   - Click "New Service" → "Add Service" → "From GitHub Repo"
   - Select the same repository
   - In the service settings, configure:
     - **Name:** `mcgraw-solver-cron`
     - **Build Command:** `pip install -r server/requirements.txt`
     - **Start Command:** `python server/cron.py`
     - **Watch Paths:** `server/**`

   **Alternative method (using startup script):**
   - **Start Command:** `bash server/start_cron.sh`
   - This script automatically installs dependencies before running cron

   **Note:** Railway should automatically detect the [railway.toml](../railway.toml) configuration file which sets these commands.

3. **Configure environment variables for cron service:**

   Copy these from your main web service:
   - `DATABASE_URL` - **REQUIRED** for session cleanup and email retry
   - `ADMIN_EMAIL` - Optional, for admin notifications

   **Important:** The cron service needs the same `DATABASE_URL` as your web service to access the same database.

4. **Verify cron is running:**
   - Check Railway logs for the cron service
   - Look for: `Cron scheduler started`
   - Should see session cleanup logs every 5 minutes

### Method 2: External Cron Service (Alternative)

If Railway doesn't support multiple processes, use an external cron service like GitHub Actions or Render Cron Jobs.

#### Using GitHub Actions

Create `.github/workflows/cron.yml`:

```yaml
name: Cron Jobs

on:
  schedule:
    # Session cleanup: every 5 minutes
    - cron: '*/5 * * * *'
    # Email retry: every hour
    - cron: '0 * * * *'

jobs:
  cleanup-sessions:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r server/requirements.txt
      - run: python server/cleanup_sessions.py
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}

  retry-emails:
    runs-on: ubuntu-latest
    if: github.event.schedule == '0 * * * *'
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r server/requirements.txt
      - run: python server/retry_emails.py
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          ADMIN_EMAIL: ${{ secrets.ADMIN_EMAIL }}
```

Then add `DATABASE_URL` to GitHub Secrets.

## Testing Cron Jobs

### Test Session Cleanup Locally

```bash
cd c:/Users/PC/Mcgraw-Solver/server

# Set environment variable
export DATABASE_URL="your_railway_database_url"

# Run cleanup manually
python cleanup_sessions.py
```

**Expected output:**
```
=== Session Cleanup Job Started ===
Timestamp: 2026-02-16T...
INFO:__main__:Cleaned up 3 stale session(s):
INFO:__main__:  - Key: 69c75287..., Session: abc12345...
INFO:__main__:Active sessions remaining: 5
=== Session Cleanup Job Finished ===
```

### Test Email Retry Locally

```bash
# Run email retry manually
python retry_emails.py
```

**Expected output:**
```
=== Email Retry Job Started ===
Timestamp: 2026-02-16T...
INFO:__main__:Found 2 emails to retry
INFO:__main__:Retrying key_email for order order_abc123 (attempt 1)
INFO:__main__:✓ Email sent successfully for order order_abc123
INFO:__main__:Email retry job completed
=== Email Retry Job Finished ===
```

### Test Full Cron Runner Locally

```bash
# This will run the scheduler (blocking process)
python cron.py
```

**Expected output:**
```
INFO:__main__:Cron scheduler started
INFO:__main__:- Email retry: DISABLED
INFO:__main__:- Session cleanup: Every 5 minutes
INFO:apscheduler.scheduler:Added job "run_session_cleanup" to job store "default"
INFO:apscheduler.scheduler:Scheduler started
# ... will run cleanup every 5 minutes
```

## Monitoring Cron Jobs

### Railway Logs

1. Go to Railway project → Cron service
2. Click "Deployments" → Latest deployment
3. View logs in real-time
4. Filter for:
   - `Session cleanup` - To see cleanup activity
   - `Email retry` - To see retry attempts
   - `ERROR` - To catch any failures

### Database Checks

**Check active sessions:**
```sql
SELECT COUNT(*) FROM active_sessions;
SELECT access_key, session_id, last_heartbeat
FROM active_sessions
ORDER BY last_heartbeat DESC;
```

**Check email retry queue:**
```sql
SELECT COUNT(*) FROM email_retry_queue;
SELECT order_id, email_type, attempts, created, last_attempt
FROM email_retry_queue
ORDER BY created DESC;
```

**Expected state:**
- `active_sessions` should only have sessions with recent heartbeats (< 60s old)
- `email_retry_queue` should be mostly empty (only failed emails)

## Enabling Email Retry

Currently, email retry is **disabled** in [server/cron.py:36](../server/cron.py#L36).

To enable it:

1. Edit [server/cron.py](../server/cron.py):
   ```python
   # Change from:
   # scheduler.add_job(run_email_retry, 'cron', minute=0)

   # To:
   scheduler.add_job(run_email_retry, 'cron', minute=0)
   ```

2. Update the startup log:
   ```python
   logger.info("- Email retry: Every hour at minute 0")
   ```

3. Commit and push:
   ```bash
   git add server/cron.py
   git commit -m "Enable email retry cron job"
   git push origin main
   ```

4. Railway will automatically redeploy the cron service

## Troubleshooting

### Cron job not running

**Check:**
1. Railway cron service is deployed and running (not crashed)
2. `DATABASE_URL` environment variable is set on cron service
3. APScheduler is installed (`pip list | grep APScheduler`)
4. No syntax errors in cron.py (check logs)

**Fix:**
```bash
# Restart the cron service in Railway
# Or redeploy:
git commit --allow-empty -m "Redeploy cron"
git push origin main
```

### Sessions not being cleaned up

**Check:**
1. Cron job is running (see logs for "Session cleanup job started")
2. `active_sessions` table exists in database
3. Database connection is working

**Manual cleanup:**
```bash
python server/cleanup_sessions.py
```

### Email retry not working

**Check:**
1. Email retry is enabled in cron.py
2. `email_retry_queue` table exists
3. Email service credentials are configured (EMAILJS keys)

**Test manually:**
```bash
python server/retry_emails.py
```

## Configuration Summary

| Cron Job | Schedule | Status | Required Env Vars |
|----------|----------|--------|-------------------|
| Session Cleanup | Every 5 min | ✅ Enabled | `DATABASE_URL` |
| Email Retry | Hourly | ⏸️ Disabled | `DATABASE_URL`, `ADMIN_EMAIL` |

## Next Steps

1. ✅ Cron jobs are implemented and ready
2. ⏭️ Deploy cron service to Railway (see Method 1 above)
3. ⏭️ Configure `DATABASE_URL` on Railway cron service
4. ⏭️ Monitor logs to verify session cleanup runs every 5 minutes
5. ⏭️ (Optional) Enable email retry if needed

## Related Files

- [server/app.py](../server/app.py) - Main web server
- [server/db.py](../server/db.py) - Database functions (session and email queue operations)
- [server/email_service.py](../server/email_service.py) - Email sending functions
- [FIXES_APPLIED.md](./FIXES_APPLIED.md) - Recent bug fixes for Phase 3

---

**Note:** Session cleanup is critical for the one-device-at-a-time feature to work properly. Make sure the cron service is deployed and running!
