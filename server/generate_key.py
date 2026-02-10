"""Generate a new access key for a friend."""
import json
import os
import secrets
import sys

KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys.json")


def load_keys():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            return json.load(f)
    return {"keys": []}


def save_keys(data):
    with open(KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def generate_key(label=None):
    key = secrets.token_hex(16)  # 32-char hex key
    keys_data = load_keys()
    entry = {"key": key}
    if label:
        entry["label"] = label
    keys_data["keys"].append(entry)
    save_keys(keys_data)
    return key


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else None
    key = generate_key(label)
    print(f"New access key: {key}")
    if label:
        print(f"Label: {label}")
    print(f"Saved to {KEYS_FILE}")
