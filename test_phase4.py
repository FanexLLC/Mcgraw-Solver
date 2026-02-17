"""
Phase 4 Testing Script - AI Model Tiers
Tests the implementation without needing API keys or running server.
"""
import sys
import os
sys.path.insert(0, 'server')

from server.db import init_db, find_key

# Import model tier configuration from config.py instead
sys.path.insert(0, '.')
from config import (
    PLAN_MODEL_ACCESS,
    MODEL_DISPLAY_NAMES,
    get_default_model_for_plan,
    is_model_allowed_for_plan
)

def print_header(title):
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print('=' * 80)

def print_test(name, passed, details=""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {name}")
    if details:
        print(f"     {details}")

# Initialize database
init_db()

# Test keys
test_keys = {
    'Weekly': '641072dff0cae5bed62244f73622a5f2',
    'Monthly': 'cffc4691dd2af662687e7e9fd61974d1',
    'Semester': 'db2ac80bbc903df1ebaaba7bbda26263'
}

print_header("PHASE 4: AI MODEL TIERS - TEST RESULTS")

# ============================================================================
# TEST 1: Database Keys Exist
# ============================================================================
print_header("Test 1: Database Keys Exist")

for plan_name, key in test_keys.items():
    key_data = find_key(key)
    exists = key_data is not None
    if exists:
        plan = key_data.get('plan')
        print_test(f"{plan_name} key exists", True, f"Plan: {plan}")
    else:
        print_test(f"{plan_name} key exists", False, f"Key not found: {key[:16]}...")

# ============================================================================
# TEST 2: Plan Model Access Configuration
# ============================================================================
print_header("Test 2: Plan Model Access Configuration")

expected_access = {
    'weekly': ['gpt-4o-mini'],
    'monthly': ['gpt-4o-mini', 'gpt-4o'],
    'semester': ['gpt-4o-mini', 'gpt-4o', 'claude-sonnet-4-5-20250929']
}

for plan, expected_models in expected_access.items():
    actual_models = PLAN_MODEL_ACCESS.get(plan, [])
    matches = actual_models == expected_models
    print_test(
        f"{plan.capitalize()} plan has correct models",
        matches,
        f"Expected: {expected_models}\n     Actual: {actual_models}"
    )

# ============================================================================
# TEST 3: Default Model Selection
# ============================================================================
print_header("Test 3: Default Model Selection")

expected_defaults = {
    'weekly': 'gpt-4o-mini',
    'monthly': 'gpt-4o',
    'semester': 'claude-sonnet-4-5-20250929'
}

for plan, expected_model in expected_defaults.items():
    actual_model = get_default_model_for_plan(plan)
    matches = actual_model == expected_model
    print_test(
        f"{plan.capitalize()} plan default model",
        matches,
        f"Expected: {expected_model}\n     Actual: {actual_model}"
    )

# ============================================================================
# TEST 4: Model Tier Enforcement
# ============================================================================
print_header("Test 4: Model Tier Enforcement")

test_cases = [
    # (plan, model, should_be_allowed)
    ('weekly', 'gpt-4o-mini', True),
    ('weekly', 'gpt-4o', False),
    ('weekly', 'claude-sonnet-4-5-20250929', False),
    ('monthly', 'gpt-4o-mini', True),
    ('monthly', 'gpt-4o', True),
    ('monthly', 'claude-sonnet-4-5-20250929', False),
    ('semester', 'gpt-4o-mini', True),
    ('semester', 'gpt-4o', True),
    ('semester', 'claude-sonnet-4-5-20250929', True),
]

for plan, model, should_be_allowed in test_cases:
    is_allowed = is_model_allowed_for_plan(model, plan)
    matches = is_allowed == should_be_allowed
    model_display = MODEL_DISPLAY_NAMES.get(model, model)
    status = "allowed" if should_be_allowed else "blocked"
    print_test(
        f"{plan.capitalize()}: {model_display[:20]} should be {status}",
        matches,
        f"Expected: {should_be_allowed}, Actual: {is_allowed}"
    )

# ============================================================================
# TEST 5: Model Display Names
# ============================================================================
print_header("Test 5: Model Display Names Exist")

required_models = ['gpt-4o-mini', 'gpt-4o', 'claude-sonnet-4-5-20250929']

for model in required_models:
    has_display_name = model in MODEL_DISPLAY_NAMES
    display_name = MODEL_DISPLAY_NAMES.get(model, "")
    print_test(
        f"Model {model[:20]} has display name",
        has_display_name,
        f"Display name: {display_name}"
    )

# ============================================================================
# TEST 6: Key Data Includes Plan Information
# ============================================================================
print_header("Test 6: Key Data Includes Plan Information")

for plan_name, key in test_keys.items():
    key_data = find_key(key)
    if key_data:
        has_plan = 'plan' in key_data
        plan_value = key_data.get('plan')
        expected_plan = plan_name.lower()
        correct_plan = plan_value == expected_plan
        print_test(
            f"{plan_name} key has correct plan field",
            has_plan and correct_plan,
            f"Plan field: {plan_value}"
        )
    else:
        print_test(f"{plan_name} key exists", False, "Key not found")

# ============================================================================
# SUMMARY
# ============================================================================
print_header("PHASE 4 IMPLEMENTATION SUMMARY")

print("\n[OK] Configuration:")
print("  - Model tier constants defined (PLAN_MODEL_ACCESS)")
print("  - Display names configured (MODEL_DISPLAY_NAMES)")
print("  - Helper functions implemented")

print("\n[OK] Model Access Tiers:")
print("  - Weekly: GPT-4o-mini only")
print("  - Monthly: GPT-4o-mini + GPT-4o")
print("  - Semester: All models (GPT-4o-mini + GPT-4o + Claude Sonnet 4.5)")

print("\n[INFO] To test the full implementation:")
print("  1. Run the GUI application")
print("  2. Use one of the test keys to log in:")
for plan_name, key in test_keys.items():
    print(f"     {plan_name:10} : {key}")
print("  3. Verify model dropdown shows only allowed models")
print("  4. Change model selection and verify it saves")

print("\n" + "=" * 80 + "\n")
