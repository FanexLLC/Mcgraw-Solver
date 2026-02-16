# Cron Jobs - Complete User Impact Guide

## What Are Cron Jobs?

Cron jobs are **automated background tasks** that run on a schedule without any user interaction. Think of them as:
- A timer that goes off every X minutes/hours
- Automatic cleanup crew running in the background
- Scheduled maintenance tasks

In your McGraw Solver system, you have **2 cron jobs**:

---

## Cron Job #1: Session Cleanup (Active ✅)

### Schedule
**Every 5 minutes** (runs 288 times per day)

### What It Does Technically

```python
# Every 5 minutes, this query runs:
DELETE FROM active_sessions
WHERE last_heartbeat < NOW() - INTERVAL '60 seconds'
```

This removes any session that **hasn't sent a heartbeat in the last 60 seconds**.

### What Is a Session?

When a user launches the McGraw Solver GUI application:

1. **Session Start** - App calls `/api/session/start`
   - Creates a new session in `active_sessions` table
   - Records: `access_key`, `session_id`, `last_heartbeat`

2. **Heartbeat Loop** - Every 30 seconds while app runs
   - App sends heartbeat to `/api/session/heartbeat`
   - Updates `last_heartbeat` timestamp to current time

3. **Session End** - When app closes normally
   - App calls `/api/session/end`
   - Removes session from database

### One-Device-At-A-Time Enforcement

**Problem it solves:** Prevent users from sharing access keys with multiple people

**How it works:**
- Each access key can only have **1 active session** at a time
- If user tries to use same key on Device B:
  - Device B creates a new session
  - Device A's session gets **terminated**
  - Device A gets error: "Session terminated. Another device is using this key."

### Real-World User Scenarios

#### Scenario 1: Normal Usage
```
User launches app on Laptop A
├─ Session created: last_heartbeat = 12:00:00
├─ Heartbeat sent: last_heartbeat = 12:00:30
├─ Heartbeat sent: last_heartbeat = 12:01:00
├─ User closes app normally
└─ Session deleted via /api/session/end
✅ Everything works perfectly
```

#### Scenario 2: App Crashes
```
User launches app on Laptop A
├─ Session created: last_heartbeat = 12:00:00
├─ Heartbeat sent: last_heartbeat = 12:00:30
├─ APP CRASHES (power loss, forced quit, etc.)
├─ No more heartbeats sent
├─ Session stuck in database with last_heartbeat = 12:00:30
│
└─ User tries to launch app again on Laptop A (12:05:00)
    ├─ Tries to create new session
    ├─ ERROR: "Another session active for this key"
    ├─ User is locked out! 😞
```

**This is where the cron job saves the day:**

```
12:05:00 - Cron job runs session cleanup
├─ Checks: last_heartbeat (12:00:30) < NOW (12:05:00) - 60s?
├─ 12:00:30 < 12:04:00? YES!
├─ Deletes stale session
└─ User can now launch app successfully! ✅
```

#### Scenario 3: Network Interruption
```
User launches app on Laptop A
├─ Session created: last_heartbeat = 12:00:00
├─ Internet connection lost at 12:01:00
├─ Heartbeats can't reach server
├─ last_heartbeat stays frozen at 12:01:00
│
└─ After 60 seconds (12:02:00):
    ├─ Cron cleanup runs (12:05:00)
    ├─ Detects stale session (12:01:00 < 12:04:00)
    ├─ Deletes session
    └─ When internet returns, user can restart app
```

#### Scenario 4: Account Sharing Prevention
```
Student A buys access key: ABC123
Student A launches app on Device A
├─ Session created for ABC123

Student A shares key with Student B
Student B launches app on Device B with ABC123
├─ New session created for ABC123
├─ Student A's session gets TERMINATED
└─ Student A sees: "Session terminated. Another device is using this key."

Student A tries to launch again
├─ New session created for ABC123
├─ Student B's session gets TERMINATED
└─ Student B sees error

This creates a "ping-pong" effect making sharing impractical! 🏓
```

### User Impact Summary

**Good:**
- ✅ Prevents app from getting "stuck" after crashes
- ✅ Auto-recovers from network issues
- ✅ Prevents account sharing
- ✅ Users never locked out for more than 5 minutes max

**Trade-offs:**
- ⚠️ If user loses internet for 60+ seconds, session expires
- ⚠️ User must restart app after connection restored
- ⚠️ Maximum "stuck session" time = 5 minutes (until next cron run)

### Why Every 5 Minutes?

**Too Frequent (every 1 minute):**
- ❌ Wastes database resources
- ❌ More Railway execution costs
- ❌ Unnecessary for this use case

**Too Infrequent (every 30 minutes):**
- ❌ User with crashed app waits up to 30 min to use it again
- ❌ Poor user experience

**Every 5 minutes:**
- ✅ Good balance between resource usage and user experience
- ✅ Max wait time: 5 minutes after crash
- ✅ 288 cleanup runs per day is acceptable

---

## Cron Job #2: Email Retry (Disabled ⏸️)

### Schedule
**Every hour** (if enabled - would run 24 times per day)

### What It Does Technically

```python
# Every hour, this query runs:
SELECT * FROM email_retry_queue
WHERE attempts < 5
  AND created > NOW() - INTERVAL '24 hours'
  AND (last_attempt IS NULL OR last_attempt < NOW() - INTERVAL '1 hour')
```

This finds failed emails and retries sending them.

### What Is the Email Retry Queue?

When the system tries to send an email (access key delivery):

**Success Path:**
```
User completes Stripe checkout
├─ Order approved
├─ Access key generated
├─ send_key_email() called
├─ Email sent successfully ✅
└─ User receives key in inbox
```

**Failure Path:**
```
User completes Stripe checkout
├─ Order approved
├─ Access key generated
├─ send_key_email() called
├─ EMAIL SEND FAILS (EmailJS down, network error, etc.)
├─ add_to_email_retry_queue() called
│   └─ Saves to database: order_id, recipient, key, plan, attempts=0
└─ User doesn't receive key 😞
```

**Retry Process (if enabled):**
```
Hour 1 (1:00 PM): First retry attempt
├─ Fetch pending emails from queue
├─ Try to send email again
├─ If success: Delete from queue, user gets email ✅
├─ If fails: attempts=1, last_attempt=1:00 PM

Hour 2 (2:00 PM): Second retry
├─ Try again (attempts < 5, last_attempt > 1 hour ago)
├─ If success: Delete from queue ✅
├─ If fails: attempts=2

Hour 3 (3:00 PM): Third retry
... continues up to 5 attempts

Hour 6 (6:00 PM): Fifth attempt failed
├─ attempts=5 (max reached)
├─ Log critical error
├─ Admin notification: "Email failed 5 times for order_xyz"
└─ Admin must manually share key with user
```

### Real-World User Scenarios

#### Scenario 1: EmailJS Temporary Outage
```
12:00 PM - User purchases semester plan
├─ Stripe payment succeeds
├─ Order auto-approved
├─ Email send fails (EmailJS down)
├─ Added to retry queue
└─ User doesn't get email 😞

1:00 PM - Cron job runs
├─ EmailJS back online
├─ Email sent successfully
└─ User receives key ✅ (1 hour delay)
```

#### Scenario 2: Invalid Email Address
```
User enters typo: "usre@gmail.com" instead of "user@gmail.com"
├─ Order approved
├─ Email send fails (invalid address)
├─ Added to retry queue

Every hour for 5 hours:
├─ Retry fails (still invalid address)
├─ attempts increments

After 5 attempts:
├─ Admin gets alert
├─ Admin contacts user via transaction records
└─ Admin manually sends key to correct email
```

#### Scenario 3: Network Glitch
```
User completes checkout during brief network outage
├─ Email send fails
├─ Added to retry queue

Next cron run (within 1 hour):
├─ Network restored
├─ Email sent successfully
└─ User receives key with minimal delay
```

### Why Is Email Retry Currently Disabled?

Looking at your [server/cron.py:36](../server/cron.py#L36):
```python
# Email retry: DISABLED for now (can re-enable later if needed)
# scheduler.add_job(run_email_retry, 'cron', minute=0)
```

**Reasons to keep it disabled:**
- EmailJS has 99.9% uptime (rarely fails)
- If email fails, Stripe webhook will retry automatically
- Admin can manually resend keys from dashboard
- Reduces cron job complexity during initial rollout

**When to enable it:**
- If you notice frequent email failures
- If users complain about not receiving keys
- Once system is stable and you want extra reliability

### User Impact Summary

**If Enabled:**
- ✅ Users get their keys even if email service has issues
- ✅ Automatic recovery from temporary failures
- ✅ Reduces manual admin work

**If Disabled (current state):**
- ⚠️ If email fails, user must contact admin
- ⚠️ Admin must manually share key
- ✅ Simpler system, fewer moving parts

---

## Combined System Flow

### Happy Path (Everything Works)
```
1. User completes Stripe checkout
2. Webhook triggers order approval
3. Access key generated
4. Email sent successfully ✅
5. User receives key immediately
6. User launches app
7. Session created, heartbeats sent
8. User completes assignments
9. User closes app, session ended
10. Cron cleanup finds nothing to clean

Total cron impact: Zero (nothing to clean up)
```

### Unhappy Path (Things Go Wrong)
```
1. User completes Stripe checkout
2. Webhook triggers order approval
3. Access key generated
4. Email send fails ❌
   └─ If retry enabled: Added to queue, retried hourly
   └─ If retry disabled: Admin must manually send

5. User eventually gets key
6. User launches app, internet drops
7. Session created, heartbeats stop ❌
8. Session becomes stale (last_heartbeat > 60s old)

9. Cron cleanup runs (every 5 min)
   └─ Detects stale session
   └─ Deletes it ✅

10. User's internet returns
11. User relaunches app successfully
12. New session created

Cron impact: Saved the user from being locked out!
```

---

## Performance & Resource Usage

### Session Cleanup (Every 5 minutes)

**Database Impact:**
```sql
-- Single query per run:
DELETE FROM active_sessions
WHERE last_heartbeat < NOW() - INTERVAL '60 seconds';

-- If 0 stale sessions: ~5ms query time
-- If 10 stale sessions: ~20ms query time
-- Minimal database load
```

**Typical Results:**
- **Peak usage (evening):** 20-50 active sessions, 2-5 stale sessions per cleanup
- **Low usage (night):** 0-5 active sessions, 0-1 stale sessions
- **After crash/outage:** Could clean 100+ stale sessions at once

**Railway Costs:**
- Cron service runs 24/7
- Uses minimal CPU (~1-5% during cleanup)
- Memory: ~50-100MB
- Estimated cost: $5-10/month for Railway cron service

### Email Retry (Every hour, if enabled)

**Database Impact:**
```sql
-- Query runs hourly:
SELECT * FROM email_retry_queue
WHERE attempts < 5 AND created > NOW() - INTERVAL '24 hours'
AND (last_attempt IS NULL OR last_attempt < NOW() - INTERVAL '1 hour');

-- Then for each email:
UPDATE email_retry_queue SET attempts = attempts + 1, last_attempt = NOW()
WHERE id = ?;

-- Or on success:
DELETE FROM email_retry_queue WHERE id = ?;
```

**Typical Results:**
- **Normal operation:** 0 emails in queue (nothing to retry)
- **Email service outage:** 10-50 emails in queue
- **After outage resolved:** Queue drains in 1-2 hours

---

## Edge Cases & User Scenarios

### Edge Case 1: Rapid Session Switching
```
User launches app on Laptop A (12:00:00)
├─ Session A created

User immediately launches on Laptop B (12:00:05)
├─ Session B created
├─ Session A terminated
└─ Laptop A shows error

User goes back to Laptop A (12:00:10)
├─ Session A2 created
├─ Session B terminated
└─ Laptop B shows error

Result: "Ping-pong" effect - discourages account sharing
```

### Edge Case 2: User Closes Laptop (Sleep Mode)
```
User launches app on laptop (12:00:00)
├─ Session created
├─ Heartbeats sent every 30s

User closes laptop lid (12:05:00)
├─ Laptop goes to sleep
├─ Heartbeats stop

Cron runs (12:10:00)
├─ last_heartbeat = 12:05:00
├─ NOW - 60s = 12:09:00
├─ 12:05:00 < 12:09:00? YES
├─ Session deleted ✅

User opens laptop (12:30:00)
├─ App resumes but session expired
├─ Shows error: "Session expired, please restart app"
└─ User must relaunch app
```

**Trade-off:** Session expires during sleep, but prevents key sharing

### Edge Case 3: Multiple Cron Runs During Outage
```
Database goes down (1:00 PM)
├─ Cron tries to clean (1:05 PM) - FAILS
├─ Cron tries to clean (1:10 PM) - FAILS
├─ Cron tries to clean (1:15 PM) - FAILS
└─ Errors logged, but cron keeps trying

Database comes back online (1:20 PM)
├─ Cron runs (1:25 PM) - SUCCESS
├─ Cleans all accumulated stale sessions
└─ System recovers automatically ✅
```

### Edge Case 4: Time Zone Issues
```
All timestamps stored in UTC (NOW() function)
User in different timezone doesn't matter
Heartbeats and cleanup use server time consistently
✅ No timezone bugs
```

---

## Monitoring & Debugging

### How to Monitor Cron Jobs

**Railway Logs - Session Cleanup:**
```
✅ Good (no stale sessions):
INFO:__main__:Starting session cleanup job...
INFO:__main__:No stale sessions found
INFO:__main__:Active sessions remaining: 5

✅ Good (cleaned stale sessions):
INFO:__main__:Cleaned up 3 stale session(s):
INFO:__main__:  - Key: 69c75287..., Session: abc12345...
INFO:__main__:Active sessions remaining: 12

❌ Bad (error):
ERROR:__main__:Session cleanup job failed: connection refused
```

**Database Queries:**
```sql
-- Check active sessions
SELECT
  access_key,
  session_id,
  last_heartbeat,
  NOW() - last_heartbeat AS time_since_heartbeat
FROM active_sessions
ORDER BY last_heartbeat DESC;

-- Find sessions about to be cleaned
SELECT * FROM active_sessions
WHERE last_heartbeat < NOW() - INTERVAL '60 seconds';

-- Check email retry queue
SELECT
  order_id,
  recipient,
  email_type,
  attempts,
  created,
  last_attempt,
  NOW() - created AS age
FROM email_retry_queue;
```

### User Support Scenarios

**User: "I keep getting kicked out of the app!"**
```
Diagnosis:
1. Check if they're using same key on multiple devices
2. Check if their internet keeps dropping
3. Check if heartbeat interval is working
4. Review session logs for their access_key

Solution:
- If sharing key: Explain one-device limit
- If internet issues: Explain 60s timeout
- If app bug: Fix heartbeat mechanism
```

**User: "I paid but didn't get my key!"**
```
Diagnosis:
1. Check orders table - is order approved?
2. Check email_retry_queue - is email stuck?
3. Check Stripe dashboard - did payment succeed?

Solution:
- If in retry queue: Wait for next cron run or enable email retry
- If approved but no email: Manually send key from admin panel
- If not approved: Check webhook logs
```

**User: "Can I use this on my laptop and desktop?"**
```
Answer: No, only one device at a time.
Explanation:
- Session management enforces one-device limit
- If you start on desktop, laptop will disconnect
- This prevents account sharing
- For multiple devices, need separate subscriptions
```

---

## Configuration Options

### Adjusting Cleanup Frequency

**Current: Every 5 minutes**
```python
# server/cron.py
scheduler.add_job(run_session_cleanup, 'cron', minute='*/5')
```

**Change to every 2 minutes:**
```python
scheduler.add_job(run_session_cleanup, 'cron', minute='*/2')
```
- Faster recovery from crashes
- More database queries
- Higher Railway costs

**Change to every 10 minutes:**
```python
scheduler.add_job(run_session_cleanup, 'cron', minute='*/10')
```
- Slower recovery from crashes
- Fewer database queries
- Lower Railway costs

### Adjusting Session Timeout

**Current: 60 seconds**
```python
# server/cleanup_sessions.py
timeout_seconds = 60
```

**Change to 120 seconds:**
```python
timeout_seconds = 120
```
- More forgiving for network hiccups
- Longer wait to recover from crashes
- More time for account sharers to "ping-pong"

**Change to 30 seconds:**
```python
timeout_seconds = 30
```
- Faster detection of dead sessions
- Less forgiving for network issues
- Users with slow internet might have problems

### Enabling Email Retry

**Current: Disabled**

**To enable:**
```python
# server/cron.py - line 36
scheduler.add_job(run_email_retry, 'cron', minute=0)  # Remove comment
```

Then commit and push - Railway will redeploy.

---

## Recommendations

### For Your Current Setup ✅

**Session Cleanup: Every 5 minutes, 60s timeout**
- Perfect balance for most users
- Fast enough to recover from crashes
- Forgiving enough for network glitches
- **Recommendation: Keep as is**

**Email Retry: Disabled**
- EmailJS is reliable
- Stripe webhook has its own retry
- Admin can manually send keys
- **Recommendation: Keep disabled initially, enable if you see email failures**

### When to Adjust

**Enable email retry if:**
- 5+ users per week report missing emails
- EmailJS has frequent outages
- You want maximum automation

**Increase cleanup frequency (every 2-3 min) if:**
- Users frequently complain about being locked out
- You have many users and crashes are common
- User experience is top priority over costs

**Decrease cleanup frequency (every 10-15 min) if:**
- Railway costs are high
- Users rarely have issues
- You have few active users

**Increase timeout (90-120s) if:**
- Users have unreliable internet
- Users frequently report disconnections
- Mobile hotspot users having issues

**Decrease timeout (30-45s) if:**
- Account sharing is a big problem
- You want stricter enforcement
- Users have stable connections

---

## Summary

### Session Cleanup Cron
**Purpose:** Clean up dead sessions so users aren't locked out

**User Impact:**
- ✅ Prevents permanent lockout after crashes
- ✅ Auto-recovers from network issues
- ✅ Prevents account sharing
- ⚠️ Max 5-minute wait if session gets stuck

**Runs:** Every 5 minutes (288 times/day)

### Email Retry Cron
**Purpose:** Ensure users receive their access keys even if email fails

**User Impact:**
- ✅ Automatic retry on email failures
- ✅ Users get keys within 1 hour even if initial send fails
- ⚠️ Currently disabled (manual admin intervention needed)

**Runs:** Every hour if enabled (24 times/day)

Both cron jobs work **silently in the background** - users never see them, but they prevent major frustrations!
