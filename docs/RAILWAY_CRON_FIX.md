# Railway Cron Service - Dependency Fix

## Problem

The cron service crashed with:
```
ModuleNotFoundError: No module named 'apscheduler'
```

**Root Cause:** Railway wasn't installing dependencies from `server/requirements.txt` before running `python server/cron.py`.

## Solution Applied

Created three fixes (choose one):

### Option 1: Use railway.toml (Recommended) ✅

Created [railway.toml](../railway.toml) at repository root:

```toml
[build]
builder = "nixpacks"
buildCommand = "pip install -r server/requirements.txt"

[deploy]
startCommand = "python server/cron.py"
restartPolicyType = "always"
restartPolicyMaxRetries = 10
```

**How to use:**
1. Commit and push railway.toml
2. Railway will automatically detect and use this configuration
3. No manual configuration needed in Railway dashboard

### Option 2: Use Startup Script ✅

Created [server/start_cron.sh](../server/start_cron.sh):

```bash
#!/bin/bash
set -e
echo "Installing dependencies..."
pip install -r requirements.txt
echo "Starting cron scheduler..."
python cron.py
```

**How to use:**
1. In Railway cron service settings
2. Set **Start Command:** `bash server/start_cron.sh`
3. This will install deps automatically on each deployment

### Option 3: Manual Railway Configuration

In Railway service settings:
- **Build Command:** `pip install -r server/requirements.txt`
- **Start Command:** `python server/cron.py`

## Deployment Steps

### Quick Fix (Use railway.toml)

```bash
# 1. Commit the configuration files
git add railway.toml server/start_cron.sh docs/
git commit -m "Fix Railway cron dependencies installation"
git push origin main

# 2. Railway will automatically redeploy with the new configuration
# 3. Check logs to verify: "Installing dependencies..." → "Cron scheduler started"
```

### Alternative (Manual Configuration)

If railway.toml doesn't work:

1. Go to Railway → Cron Service → Settings
2. Click "Build" section
3. Set **Build Command:**
   ```
   pip install -r server/requirements.txt
   ```
4. Click "Deploy" section
5. Set **Start Command:**
   ```
   python server/cron.py
   ```
6. Save and redeploy

## Verification

After deployment, check Railway logs for:

```
✅ Installing dependencies...
✅ Successfully installed APScheduler-3.10.0 ...
✅ Starting cron scheduler...
✅ INFO:__main__:Cron scheduler started
✅ INFO:__main__:- Email retry: DISABLED
✅ INFO:__main__:- Session cleanup: Every 5 minutes
✅ INFO:apscheduler.scheduler:Scheduler started
```

After 5 minutes, should see:
```
✅ INFO:__main__:Starting session cleanup job...
✅ === Session Cleanup Job Started ===
✅ INFO:__main__:No stale sessions found
✅ INFO:__main__:Active sessions remaining: 0
✅ === Session Cleanup Job Finished ===
```

## Troubleshooting

### Issue: Still getting ModuleNotFoundError

**Solution 1:** Check that requirements.txt path is correct
```bash
# From repository root:
ls server/requirements.txt  # Should exist

# Verify APScheduler is in requirements.txt:
grep -i apscheduler server/requirements.txt
# Should show: APScheduler>=3.10.0
```

**Solution 2:** Set Root Directory in Railway
- Railway Settings → "Root Directory" → `server`
- Update Start Command to: `python cron.py` (without server/ prefix)
- Update Build Command to: `pip install -r requirements.txt` (without server/ prefix)

### Issue: Railway not detecting railway.toml

**Solution:** Move railway.toml to repository root (it should already be there)
```bash
ls railway.toml  # Should be at c:\Users\PC\Mcgraw-Solver\railway.toml
```

### Issue: Permission denied on start_cron.sh

**Solution:** Make sure script is executable
```bash
chmod +x server/start_cron.sh
git add server/start_cron.sh
git commit -m "Make cron startup script executable"
git push origin main
```

### Issue: Cron runs but crashes immediately

**Check:**
1. DATABASE_URL is set on cron service
2. DATABASE_URL is correct and accessible
3. active_sessions table exists in database

**Test locally:**
```bash
cd server
export DATABASE_URL="your_railway_database_url"
python cron.py
```

## Files Added/Modified

- ✅ [railway.toml](../railway.toml) - Railway configuration for cron service
- ✅ [server/start_cron.sh](../server/start_cron.sh) - Startup script with dependency installation
- ✅ [docs/CRON_DEPLOYMENT.md](./CRON_DEPLOYMENT.md) - Updated deployment instructions
- ✅ [docs/RAILWAY_CRON_FIX.md](./RAILWAY_CRON_FIX.md) - This troubleshooting guide

## Next Steps

1. ✅ Commit and push fixes
2. ⏭️ Wait for Railway to redeploy (automatic)
3. ⏭️ Check logs to verify cron started successfully
4. ⏭️ Wait 5 minutes and verify session cleanup runs
5. ✅ Phase 3 complete!

## Quick Reference

| Method | Start Command | Build Command | Notes |
|--------|--------------|---------------|-------|
| railway.toml | Auto-detected | Auto-detected | **Recommended** |
| Startup script | `bash server/start_cron.sh` | None needed | Installs deps in script |
| Manual config | `python server/cron.py` | `pip install -r server/requirements.txt` | Set in Railway UI |

Choose **railway.toml** for the cleanest setup!
