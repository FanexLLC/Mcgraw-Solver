import os
import json
import logging
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load OpenAI key from environment
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
client = None

# Load valid access keys
KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys.json")


def load_keys():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            return json.load(f)
    return {"keys": []}


def get_client():
    global client
    if client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not set on server")
        client = OpenAI(api_key=OPENAI_API_KEY)
    return client


@app.route("/api/solve", methods=["POST"])
def solve():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    # Validate access key
    access_key = data.get("access_key", "")
    keys_data = load_keys()
    valid_keys = [k["key"] for k in keys_data.get("keys", [])]

    if access_key not in valid_keys:
        return jsonify({"error": "Invalid access key"}), 403

    # Extract question data
    question = data.get("question", "")
    prompt = data.get("prompt", "")
    model = data.get("model", "gpt-4o")
    temperature = data.get("temperature", 0.0)

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    # Call OpenAI
    try:
        oai = get_client()
        response = oai.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": "You are a knowledgeable academic assistant. Answer precisely and concisely."},
                {"role": "user", "content": prompt},
            ],
        )
        answer = response.choices[0].message.content.strip()
        logger.info(f"Key={access_key[:8]}... | Model={model} | Answer={answer[:50]}")
        return jsonify({"answer": answer})

    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
