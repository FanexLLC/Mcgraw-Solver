"""
Test script for Phase 6: Session Management (One-Device-at-a-Time)

This script tests the session management implementation to ensure:
1. Only one active session per access key
2. New session disconnects previous session
3. Heartbeat keeps session alive
4. Sessions expire after 60s of no heartbeat

Usage:
    python test_phase6_session.py

Requirements:
    - Server must be running (local or Railway)
    - Valid access key in .env file or passed as argument
"""

import os
import sys
import time
import uuid
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SERVER_URL = os.getenv("SERVER_URL", "https://mcgraw-solver-production.up.railway.app")
ACCESS_KEY = os.getenv("ACCESS_KEY", "")


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_success(text):
    """Print success message."""
    print(f"✓ {text}")


def print_error(text):
    """Print error message."""
    print(f"✗ {text}")


def print_info(text):
    """Print info message."""
    print(f"ℹ {text}")


def test_health_check():
    """Test 1: Verify server is running."""
    print_header("Test 1: Health Check")
    try:
        response = requests.get(f"{SERVER_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Server is running: {data}")
            return True
        else:
            print_error(f"Server returned {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Cannot reach server: {e}")
        return False


def test_session_start(access_key):
    """Test 2: Start a new session."""
    print_header("Test 2: Start Session")
    try:
        session_id = str(uuid.uuid4())
        response = requests.post(
            f"{SERVER_URL}/api/session/start",
            json={
                "access_key": access_key,
                "session_id": session_id
            },
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            print_success(f"Session started: {session_id[:8]}...")
            if data.get("previous_session_terminated"):
                print_info("Previous session was terminated")
            return session_id
        else:
            error = response.json().get("error", "Unknown error")
            print_error(f"Failed to start session: {error}")
            return None
    except Exception as e:
        print_error(f"Exception during session start: {e}")
        return None


def test_heartbeat(session_id):
    """Test 3: Send heartbeat to keep session alive."""
    print_header("Test 3: Heartbeat")
    try:
        response = requests.post(
            f"{SERVER_URL}/api/session/heartbeat",
            json={"session_id": session_id},
            timeout=5
        )

        if response.status_code == 200:
            print_success("Heartbeat sent successfully")
            return True
        else:
            print_error(f"Heartbeat failed with status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Exception during heartbeat: {e}")
        return False


def test_session_status(access_key):
    """Test 4: Check active session status."""
    print_header("Test 4: Session Status")
    try:
        response = requests.post(
            f"{SERVER_URL}/api/session/status",
            json={"access_key": access_key},
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("active"):
                session_info = data.get("session")
                print_success(f"Active session found:")
                print_info(f"  Session ID: {session_info.get('session_id', '')[:8]}...")
                print_info(f"  Started: {session_info.get('started_at')}")
                print_info(f"  Last heartbeat: {session_info.get('last_heartbeat')}")
                return True
            else:
                print_info("No active session")
                return False
        else:
            print_error(f"Status check failed with {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Exception during status check: {e}")
        return False


def test_multiple_sessions(access_key):
    """Test 5: Verify only one session allowed (one-device-at-a-time)."""
    print_header("Test 5: One-Device-at-a-Time Enforcement")

    # Start first session
    print_info("Starting session on Device A...")
    session_a = str(uuid.uuid4())
    response_a = requests.post(
        f"{SERVER_URL}/api/session/start",
        json={"access_key": access_key, "session_id": session_a},
        timeout=10
    )

    if response_a.status_code != 200:
        print_error("Failed to start first session")
        return False

    print_success(f"Device A session started: {session_a[:8]}...")

    # Start second session (should disconnect first)
    time.sleep(2)
    print_info("Starting session on Device B (should disconnect Device A)...")
    session_b = str(uuid.uuid4())
    response_b = requests.post(
        f"{SERVER_URL}/api/session/start",
        json={"access_key": access_key, "session_id": session_b},
        timeout=10
    )

    if response_b.status_code != 200:
        print_error("Failed to start second session")
        return False

    data_b = response_b.json()
    if data_b.get("previous_session_terminated"):
        print_success("Device A was disconnected when Device B started ✓")
        print_success(f"Device B session active: {session_b[:8]}...")
        return session_b
    else:
        print_error("Device A was NOT disconnected (enforcement failed!)")
        return None


def test_session_end(session_id):
    """Test 6: End a session."""
    print_header("Test 6: End Session")
    try:
        response = requests.post(
            f"{SERVER_URL}/api/session/end",
            json={"session_id": session_id},
            timeout=5
        )

        if response.status_code == 200:
            print_success(f"Session ended: {session_id[:8]}...")
            return True
        else:
            print_error(f"Failed to end session: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Exception during session end: {e}")
        return False


def test_session_expiration(access_key):
    """Test 7: Verify sessions expire after 60s without heartbeat."""
    print_header("Test 7: Session Expiration (60s timeout)")
    print_info("This test requires admin access to trigger cleanup manually")

    # Start session
    session_id = str(uuid.uuid4())
    response = requests.post(
        f"{SERVER_URL}/api/session/start",
        json={"access_key": access_key, "session_id": session_id},
        timeout=10
    )

    if response.status_code != 200:
        print_error("Failed to start session")
        return False

    print_success(f"Session started: {session_id[:8]}...")

    # Wait 30 seconds and send heartbeat (should keep alive)
    print_info("Waiting 30s and sending heartbeat...")
    time.sleep(30)
    requests.post(
        f"{SERVER_URL}/api/session/heartbeat",
        json={"session_id": session_id},
        timeout=5
    )
    print_success("Heartbeat sent at 30s")

    # Wait 70 seconds WITHOUT heartbeat
    print_info("Waiting 70s WITHOUT heartbeat...")
    for i in range(70, 0, -10):
        print(f"  {i}s remaining...", end="\r")
        time.sleep(10)
    print("")

    # Trigger manual cleanup (requires admin password)
    print_info("Triggering manual session cleanup...")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if admin_password:
        try:
            cleanup_response = requests.post(
                f"{SERVER_URL}/api/admin/cleanup-sessions",
                headers={"X-Admin-Password": admin_password},
                timeout=10
            )
            if cleanup_response.status_code == 200:
                data = cleanup_response.json()
                print_info(f"Cleanup triggered: {data.get('deleted', 0)} session(s) deleted")
            else:
                print_info("Manual cleanup endpoint not available (needs deployment)")
        except:
            print_info("Could not trigger manual cleanup (endpoint may not exist yet)")

    # Check if session is still active (should be expired)
    time.sleep(2)  # Give cleanup a moment to process
    response = requests.post(
        f"{SERVER_URL}/api/session/status",
        json={"access_key": access_key},
        timeout=5
    )

    if response.status_code == 200:
        data = response.json()
        if not data.get("active"):
            print_success("Session expired as expected ✓")
            return True
        else:
            print_error("Session still active (cron cleanup may not have run yet)")
            print_info("Note: Cron runs every 5 minutes. Session will be cleaned up eventually.")
            print_info("For immediate cleanup, deploy the new code and ensure cron is running.")
            return False
    else:
        print_error("Failed to check session status")
        return False


def run_all_tests(access_key):
    """Run all Phase 6 tests."""
    print("\n" + "=" * 70)
    print("  PHASE 6: SESSION MANAGEMENT TEST SUITE")
    print("=" * 70)
    print(f"Server: {SERVER_URL}")
    print(f"Access Key: {access_key[:8]}...")
    print(f"Timestamp: {datetime.now().isoformat()}")

    results = []

    # Test 1: Health check
    results.append(("Health Check", test_health_check()))
    if not results[0][1]:
        print("\n" + "=" * 70)
        print_error("Server is not reachable. Please start the server first.")
        print("=" * 70)
        return

    # Test 2 & 3: Start session and heartbeat
    session_id = test_session_start(access_key)
    results.append(("Session Start", session_id is not None))
    if session_id:
        results.append(("Heartbeat", test_heartbeat(session_id)))
        results.append(("Session Status", test_session_status(access_key)))

    # Test 5: One-device-at-a-time
    session_id = test_multiple_sessions(access_key)
    results.append(("One-Device-at-a-Time", session_id is not None))

    # Test 6: End session
    if session_id:
        results.append(("Session End", test_session_end(session_id)))

    # Test 7: Session expiration (OPTIONAL - takes 70 seconds)
    print_info("\nSession expiration test is optional and takes ~70 seconds.")
    run_expiration = input("Run expiration test? (y/N): ").strip().lower()
    if run_expiration == 'y':
        results.append(("Session Expiration", test_session_expiration(access_key)))

    # Summary
    print_header("TEST SUMMARY")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")

    print("\n" + "=" * 70)
    print(f"  {passed}/{total} tests passed")
    if passed == total:
        print_success("All tests passed! Phase 6 implementation is working correctly.")
    else:
        print_error(f"{total - passed} test(s) failed. Please review the output above.")
    print("=" * 70)


if __name__ == "__main__":
    # Get access key from argument or env
    if len(sys.argv) > 1:
        access_key = sys.argv[1]
    elif ACCESS_KEY:
        access_key = ACCESS_KEY
    else:
        print_error("No access key provided!")
        print("Usage:")
        print("  1. Set ACCESS_KEY in .env file")
        print("  2. Or run: python test_phase6_session.py <your-access-key>")
        sys.exit(1)

    run_all_tests(access_key)
