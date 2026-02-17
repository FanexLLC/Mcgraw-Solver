# Phase 4 Test Keys

## Test Access Keys (Local Database)

Use these keys to test AI Model Tier features:

### Weekly Plan (GPT-4o-mini only)
```
641072dff0cae5bed62244f73622a5f2
```
- **Allowed Models:** GPT-4o-mini only
- **GUI Behavior:** Should show "GPT-4o Mini (Fast)" as label (no dropdown)
- **Expires:** 2026-02-23

### Monthly Plan (GPT-4o-mini + GPT-4o)
```
cffc4691dd2af662687e7e9fd61974d1
```
- **Allowed Models:** GPT-4o-mini, GPT-4o
- **GUI Behavior:** Should show dropdown with 2 options
- **Default:** GPT-4o (Balanced)
- **Expires:** 2026-03-18

### Semester Plan (All Models)
```
db2ac80bbc903df1ebaaba7bbda26263
```
- **Allowed Models:** GPT-4o-mini, GPT-4o, Claude Sonnet 4.5
- **GUI Behavior:** Should show dropdown with 3 options
- **Default:** Claude Sonnet 4.5 (Best)
- **Expires:** 2026-06-16

---

## GUI Testing Checklist

### Test 1: Weekly Plan - Single Model
- [ ] Log in with weekly key
- [ ] Verify "AI Model" shows as label (not dropdown)
- [ ] Verify it shows "GPT-4o Mini (Fast)"
- [ ] Start solving - should use gpt-4o-mini model

### Test 2: Monthly Plan - Dual Model Selection
- [ ] Log in with monthly key
- [ ] Verify "AI Model" shows as dropdown
- [ ] Verify dropdown has 2 options:
  - GPT-4o Mini (Fast)
  - GPT-4o (Balanced)
- [ ] Verify default is "GPT-4o (Balanced)"
- [ ] Change to GPT-4o-mini
- [ ] Verify log shows "AI model changed to GPT-4o Mini (Fast)"
- [ ] Logout and login again
- [ ] Verify preference persisted (still GPT-4o-mini)

### Test 3: Semester Plan - Triple Model Selection
- [ ] Log in with semester key
- [ ] Verify "AI Model" shows as dropdown
- [ ] Verify dropdown has 3 options:
  - GPT-4o Mini (Fast)
  - GPT-4o (Balanced)
  - Claude Sonnet 4.5 (Best)
- [ ] Verify default is "Claude Sonnet 4.5 (Best)"
- [ ] Change between models
- [ ] Verify each change is logged
- [ ] Logout and login again
- [ ] Verify preference persisted

### Test 4: Model Enforcement (Server-Side)
This requires API keys to be set. Server should:
- [ ] Reject unauthorized model requests with 403 error
- [ ] Return error message explaining which models are allowed
- [ ] Allow requests for models within the user's plan

### Test 5: Grace Period Logic
- [ ] Start session with valid key
- [ ] Simulate key expiration (requires DB update)
- [ ] Verify session can continue for 5 hours after expiry
- [ ] Verify error message after grace period ends

---

## Notes

- All test keys are stored in local `server/keys.json` database
- For production testing, use keys from Railway database
- Grace period testing requires manual database manipulation
- Model preference is stored server-side in the `preferred_model` column
