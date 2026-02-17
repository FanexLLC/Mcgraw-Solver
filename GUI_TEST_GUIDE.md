# Phase 4 GUI Testing Guide

## Quick Start - Test the Implementation

### Option 1: Test with Local Database (Easiest)

Since you have test keys in your local database, you can test locally:

**Step 1: Temporarily use local SERVER_URL**
Edit `config.py` line 40 to use localhost:
```python
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:5000")
```

**Step 2: Start local server** (in a separate terminal)
```bash
cd c:\Users\PC\Mcgraw-Solver\server
# Make sure .env has required API keys or server will fail
python app.py
```

**Step 3: Run the GUI**
```bash
cd c:\Users\PC\Mcgraw-Solver
python main.py
```

**Step 4: Test with each key**
Use the keys from [TEST_KEYS.md](TEST_KEYS.md)

---

### Option 2: Test with Production (Railway)

If you want to test with the production server, you'll need to create test keys on Railway.

---

## What to Look For

### ✅ Weekly Plan UI Behavior
When logged in with weekly key: `641072dff0cae5bed62244f73622a5f2`

**Expected UI:**
```
SETTINGS
━━━━━━━━━━━━━━━━━━━━━
AI Model
GPT-4o Mini (Fast)

Speed
[Slow] [Normal] [Fast]  ...
```

**What to verify:**
- ✓ "AI Model" label exists
- ✓ Shows "GPT-4o Mini (Fast)" as plain text (not a dropdown)
- ✓ No dropdown selector visible
- ✓ Cannot select other models

---

### ✅ Monthly Plan UI Behavior
When logged in with monthly key: `cffc4691dd2af662687e7e9fd61974d1`

**Expected UI:**
```
SETTINGS
━━━━━━━━━━━━━━━━━━━━━
AI Model
[GPT-4o (Balanced)        ▼]  <- Dropdown

Speed
[Slow] [Normal] [Fast]  ...
```

**What to verify:**
- ✓ "AI Model" label exists
- ✓ Shows dropdown selector
- ✓ Dropdown has exactly 2 options:
  - GPT-4o Mini (Fast)
  - GPT-4o (Balanced)
- ✓ Default selected is "GPT-4o (Balanced)"

**Interaction test:**
1. Click dropdown → select "GPT-4o Mini (Fast)"
2. Check log panel → should show: "AI model changed to GPT-4o Mini (Fast)"
3. Click Logout
4. Log back in with same key
5. Verify dropdown still shows "GPT-4o Mini (Fast)" (preference persisted)

---

### ✅ Semester Plan UI Behavior
When logged in with semester key: `db2ac80bbc903df1ebaaba7bbda26263`

**Expected UI:**
```
SETTINGS
━━━━━━━━━━━━━━━━━━━━━
AI Model
[Claude Sonnet 4.5 (Best) ▼]  <- Dropdown

Speed
[Slow] [Normal] [Fast]  ...
```

**What to verify:**
- ✓ "AI Model" label exists
- ✓ Shows dropdown selector
- ✓ Dropdown has exactly 3 options:
  - GPT-4o Mini (Fast)
  - GPT-4o (Balanced)
  - Claude Sonnet 4.5 (Best)
- ✓ Default selected is "Claude Sonnet 4.5 (Best)"

**Interaction test:**
1. Click dropdown → select "GPT-4o (Balanced)"
2. Check log panel → should show: "AI model changed to GPT-4o (Balanced)"
3. Click dropdown → select "GPT-4o Mini (Fast)"
4. Check log panel → should show: "AI model changed to GPT-4o Mini (Fast)"
5. Click Logout
6. Log back in with same key
7. Verify dropdown still shows "GPT-4o Mini (Fast)" (preference persisted)

---

## Troubleshooting

### GUI shows error "Cannot reach server"
- Make sure server is running: `cd server && python app.py`
- Check `config.py` has correct SERVER_URL
- For local testing: `http://localhost:5000`
- For production: `https://mcgraw-solver-production.up.railway.app`

### Dropdown doesn't show / Shows old hardcoded models
- Clear cache: Delete any `.pyc` files
- Restart the GUI application
- Make sure you're using the updated `gui.py` with Phase 4 changes

### Model change doesn't save
- Check server logs for errors
- Verify `/api/model/preference` endpoint is working
- Check database has `preferred_model` column

### Wrong models shown for plan
- Verify key plan in database: Check `server/keys.json`
- Verify `PLAN_MODEL_ACCESS` in `config.py`
- Check validation response includes correct `allowed_models`

---

## Quick Verification Commands

Check what plan a key has:
```bash
cd c:\Users\PC\Mcgraw-Solver\server
python -c "from db import init_db, find_key; init_db(); print(find_key('641072dff0cae5bed62244f73622a5f2'))"
```

List all keys and plans:
```bash
cd c:\Users\PC\Mcgraw-Solver
python test_phase4.py
```
