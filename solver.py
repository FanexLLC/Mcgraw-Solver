import random
import logging
import requests
import config
import human

logger = logging.getLogger(__name__)

_access_key = None
_server_url = None


def init_client(access_key=None):
    """Store the access key and server URL for proxy requests."""
    global _access_key, _server_url
    _access_key = access_key or config.ACCESS_KEY
    _server_url = config.SERVER_URL

    if not _access_key:
        raise ValueError("Access key not set. Please enter your access key.")

    # Verify the server is reachable
    try:
        resp = requests.get(f"{_server_url}/health", timeout=5)
        resp.raise_for_status()
    except requests.ConnectionError:
        raise ConnectionError(f"Cannot reach server at {_server_url}. Is it running?")
    except Exception as e:
        raise ConnectionError(f"Server error: {e}")


def get_answer(question_data):
    """Send a question to the proxy server and get the answer back."""
    if _access_key is None:
        init_client()

    q_type = question_data["type"]
    question = question_data["question"]
    context = question_data.get("context", "")
    choices = question_data.get("choices", [])

    blank_count = question_data.get("blank_count", 1)
    prompt = _build_prompt(q_type, question, context, choices, blank_count)

    # Send to proxy server
    payload = {
        "access_key": _access_key,
        "prompt": prompt,
        "model": config.GPT_MODEL,
        "temperature": config.GPT_TEMPERATURE,
    }

    resp = requests.post(f"{_server_url}/api/solve", json=payload, timeout=30)

    if resp.status_code == 403:
        raise PermissionError("Invalid access key.")
    elif resp.status_code != 200:
        error_msg = resp.json().get("error", "Unknown server error")
        raise RuntimeError(f"Server error: {error_msg}")

    answer_text = resp.json()["answer"]
    logger.info(f"Server response: {answer_text}")

    action = parse_gpt_response(answer_text, question_data)
    return action


def _build_prompt(q_type, question, context, choices, blank_count=1):
    """Build the GPT prompt based on question type."""
    context_section = f"\nContext: {context}\n" if context else ""

    if q_type == "mc_single":
        choices_text = "\n".join(
            f"{c['label']}) {c['text']}" for c in choices
        )
        return (
            f"Answer this multiple choice question. Reply with ONLY the letter "
            f"({', '.join(c['label'] for c in choices)}).\n\n"
            f"Question: {question}\n"
            f"{context_section}\n"
            f"{choices_text}\n\n"
            f"Answer:"
        )

    elif q_type == "mc_multi":
        choices_text = "\n".join(
            f"{c['label']}) {c['text']}" for c in choices
        )
        return (
            f"Answer this question by selecting ALL correct options. "
            f"Reply with ONLY the letters separated by commas (e.g., \"A, C\").\n\n"
            f"Question: {question}\n"
            f"{context_section}\n"
            f"{choices_text}\n\n"
            f"Answer:"
        )

    elif q_type == "fill":
        if blank_count > 1:
            return (
                f"This question has exactly {blank_count} blanks to fill in. "
                f"Each blank expects exactly ONE word. "
                f"Reply with ONLY the single words separated by semicolons. "
                f"Format: word1; word2; word3\n"
                f"IMPORTANT: Each answer MUST be exactly one word. Never use phrases.\n\n"
                f"Question: {question}\n"
                f"{context_section}\n"
                f"Answer:"
            )
        else:
            return (
                f"Fill in the blank with exactly ONE word. "
                f"Reply with ONLY that single word, nothing else. "
                f"IMPORTANT: Your answer MUST be exactly one word.\n\n"
                f"Question: {question}\n"
                f"{context_section}\n"
                f"Answer:"
            )

    elif q_type == "dropdown":
        dropdown_info = ""
        for i, c in enumerate(choices):
            opts = ", ".join(c.get("options", []))
            dropdown_info += f"Blank {i+1} options: {opts}\n"
        return (
            f"Fill in each blank with the correct option from the choices given. "
            f"Reply as:\n1: chosen_option\n2: chosen_option\n\n"
            f"Sentence: {question}\n"
            f"{context_section}\n"
            f"{dropdown_info}\n"
            f"Answer:"
        )

    else:
        return (
            f"Answer this question as accurately as possible. "
            f"Reply with ONLY the answer, nothing else.\n\n"
            f"Question: {question}\n"
            f"{context_section}\n"
            f"Answer:"
        )


def parse_gpt_response(response_text, question_data):
    """Parse GPT's response into an action dict."""
    q_type = question_data["type"]
    choices = question_data.get("choices", [])

    if q_type == "mc_single":
        letter = response_text.strip().upper()
        letter = letter.replace(")", "").replace(".", "").replace(":", "").strip()
        if len(letter) > 1:
            letter = letter[0]

        target = None
        for c in choices:
            if c["label"].upper() == letter:
                target = c.get("element")
                break

        return {
            "type": "click",
            "answer_text": letter,
            "targets": [target] if target else [],
            "values": [],
        }

    elif q_type == "mc_multi":
        letters = [l.strip().upper().replace(")", "").replace(".", "")
                   for l in response_text.split(",")]

        targets = []
        for letter in letters:
            for c in choices:
                if c["label"].upper() == letter:
                    el = c.get("element")
                    if el:
                        targets.append(el)
                    break

        return {
            "type": "multi_click",
            "answer_text": ", ".join(letters),
            "targets": targets,
            "values": [],
        }

    elif q_type == "fill":
        blank_count = question_data.get("blank_count", 1)
        inputs = question_data.get("input_elements", [])

        if blank_count > 1:
            raw = response_text.strip()
            raw = raw.replace(" and ", "; ")
            values = [v.strip() for v in raw.split(";") if v.strip()]

            if len(values) == 1 and len(inputs) > 1:
                values = [v.strip() for v in raw.split(",") if v.strip()]

            if len(values) == 1 and len(inputs) > 1:
                values = [v.strip() for v in raw.split("\n") if v.strip()]

            import re
            cleaned = []
            for v in values:
                v = re.sub(r'^\d+[\.:]\s*', '', v)
                cleaned.append(v)
            values = cleaned

            while len(values) < len(inputs):
                values.append("")
            values = values[:len(inputs)]
        else:
            values = [response_text.strip()]

        return {
            "type": "multi_type",
            "answer_text": "; ".join(values),
            "targets": inputs,
            "values": values,
        }

    elif q_type == "dropdown":
        lines = response_text.strip().split("\n")
        values = []
        for line in lines:
            if ":" in line:
                val = line.split(":", 1)[1].strip()
                values.append(val)

        return {
            "type": "dropdown",
            "answer_text": ", ".join(values),
            "targets": question_data.get("input_elements", []),
            "values": values,
        }

    else:
        return {
            "type": "type",
            "answer_text": response_text.strip(),
            "targets": question_data.get("input_elements", []),
            "values": [response_text.strip()],
        }


def maybe_inject_error(action, question_data):
    """Possibly replace the correct answer with a wrong one."""
    if not human.should_miss():
        return action, False

    q_type = question_data["type"]
    choices = question_data.get("choices", [])

    if q_type == "mc_single" and len(choices) > 1:
        correct_letter = action.get("answer_text", "")
        wrong_choices = [c for c in choices if c["label"].upper() != correct_letter]
        if wrong_choices:
            wrong = random.choice(wrong_choices)
            action["answer_text"] = wrong["label"]
            action["targets"] = [wrong.get("element")] if wrong.get("element") else []
            logger.info(f"Intentional miss: changed {correct_letter} -> {wrong['label']}")
            return action, True

    elif q_type == "mc_multi" and len(choices) > 1:
        if random.random() < 0.5 and len(action["targets"]) > 1:
            idx = random.randint(0, len(action["targets"]) - 1)
            action["targets"].pop(idx)
            logger.info("Intentional miss: removed one correct answer from multi-select")
            return action, True

    return action, False
