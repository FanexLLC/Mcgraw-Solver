"""Generate a new access key for a friend."""
import json
import os
import secrets
import sys
from datetime import datetime, timedelta

KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys.json")

PLAN_DURATIONS = {
    "monthly": 30,
    "semester": 120,
}


def load_keys():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            return json.load(f)
    return {"keys": []}


def save_keys(data):
    with open(KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def generate_key(label=None, plan=None):
    key = secrets.token_hex(16)  # 32-char hex key
    keys_data = load_keys()
    entry = {"key": key}
    if label:
        entry["label"] = label
    if plan and plan in PLAN_DURATIONS:
        now = datetime.utcnow()
        entry["plan"] = plan
        entry["created"] = now.isoformat() + "Z"
        entry["expires"] = (now + timedelta(days=PLAN_DURATIONS[plan])).isoformat() + "Z"
    keys_data["keys"].append(entry)
    save_keys(keys_data)
    return key, entry


if __name__ == "__main__":
    label = None
    plan = None
    args = sys.argv[1:]

    i = 0
    while i < len(args):
        if args[i] == "--plan" and i + 1 < len(args):
            plan = args[i + 1]
            i += 2
        elif label is None:
            label = args[i]
            i += 1
        else:
            i += 1

    key, entry = generate_key(label, plan)
    print(f"New access key: {key}")
    if label:
        print(f"Label: {label}")
    if plan:
        print(f"Plan: {plan}")
        print(f"Expires: {entry.get('expires', 'never')}")
    print(f"Saved to {KEYS_FILE}")
