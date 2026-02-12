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
    items = question_data.get("items", [])
    sources = question_data.get("sources", [])
    targets = question_data.get("targets", [])
    prompt = _build_prompt(q_type, question, context, choices, blank_count,
                           items=items, sources=sources, targets=targets)

    # Send to proxy server
    payload = {
        "access_key": _access_key,
        "prompt": prompt,
        "model": config.GPT_MODEL,
        "temperature": config.GPT_TEMPERATURE,
    }

    resp = requests.post(f"{_server_url}/api/solve", json=payload, timeout=30)

    if resp.status_code == 403:
        error_msg = resp.json().get("error", "")
        if "expired" in error_msg.lower():
            raise PermissionError("Access key expired. Please renew your subscription.")
        raise PermissionError("Invalid access key.")
    elif resp.status_code != 200:
        error_msg = resp.json().get("error", "Unknown server error")
        raise RuntimeError(f"Server error: {error_msg}")

    answer_text = resp.json()["answer"]
    logger.info(f"Server response: {answer_text}")

    action = parse_gpt_response(answer_text, question_data)
    return action


def _build_prompt(q_type, question, context, choices, blank_count=1,
                  items=None, sources=None, targets=None):
    """Build the prompt based on question type.

    Key design decisions:
    - Context always comes BEFORE the question (read-then-answer improves accuracy).
    - Fill-in-the-blank no longer forces single-word answers.
    - A brief reasoning step is requested then a final ANSWER: line for easy parsing.
    """
    # --- context block (always first) ---
    if context:
        context_block = (
            f"The following passage is from the textbook. Use it as your PRIMARY "
            f"source when answering:\n\n{context}\n\n"
        )
    else:
        context_block = ""

    # --- per-type prompt ---
    if q_type == "ordering":
        items_text = "\n".join(f"- {item}" for item in (items or []))
        return (
            f"{context_block}"
            f"Put the following items in the correct order.\n\n"
            f"Question: {question}\n\n"
            f"Items (currently in this order):\n{items_text}\n\n"
            f"Reply with ONLY the items in the correct order, one per line, "
            f"numbered 1, 2, 3, etc. Use the EXACT text of each item.\n\n"
            f"Correct order:"
        )

    elif q_type == "matching":
        sources_text = "\n".join(f"- {s}" for s in (sources or []))
        targets_text = "\n".join(f"- {t}" for t in (targets or []))
        return (
            f"{context_block}"
            f"Match each item on the left with the correct item on the right.\n\n"
            f"Question: {question}\n\n"
            f"Left items:\n{sources_text}\n\n"
            f"Right items:\n{targets_text}\n\n"
            f"Reply with each match on its own line in the format:\n"
            f"Left Item -> Right Item\n"
            f"Use the EXACT text of each item.\n\n"
            f"Matches:"
        )

    elif q_type == "mc_single":
        choices_text = "\n".join(
            f"{c['label']}) {c['text']}" for c in choices
        )
        return (
            f"{context_block}"
            f"Question: {question}\n\n"
            f"{choices_text}\n\n"
            f"Think step-by-step, then on the LAST line write ONLY:\n"
            f"ANSWER: <letter>\n"
            f"where <letter> is one of {', '.join(c['label'] for c in choices)}."
        )

    elif q_type == "mc_multi":
        choices_text = "\n".join(
            f"{c['label']}) {c['text']}" for c in choices
        )
        return (
            f"{context_block}"
            f"Question: {question}\n\n"
            f"{choices_text}\n\n"
            f"Select ALL correct options. Think step-by-step, then on the LAST "
            f"line write ONLY:\n"
            f"ANSWER: <letters separated by commas>\n"
            f"Example: ANSWER: A, C"
        )

    elif q_type == "fill":
        if blank_count > 1:
            return (
                f"{context_block}"
                f"Question: {question}\n\n"
                f"This question has exactly {blank_count} blanks to fill in. "
                f"Each blank may require one or more words.\n\n"
                f"Think step-by-step using the textbook passage above, then on "
                f"the LAST line write ONLY:\n"
                f"ANSWER: answer1; answer2; answer3\n"
                f"Separate each blank's answer with a semicolon. Use the exact "
                f"terminology from the textbook passage when possible."
            )
        else:
            return (
                f"{context_block}"
                f"Question: {question}\n\n"
                f"Fill in the blank. The answer may be one or more words.\n\n"
                f"Think step-by-step using the textbook passage above, then on "
                f"the LAST line write ONLY:\n"
                f"ANSWER: <your answer>\n"
                f"Use the exact terminology from the textbook passage when possible."
            )

    elif q_type == "dropdown":
        dropdown_info = ""
        for i, c in enumerate(choices):
            opts = ", ".join(c.get("options", []))
            dropdown_info += f"Blank {i+1} options: {opts}\n"
        return (
            f"{context_block}"
            f"Sentence: {question}\n\n"
            f"{dropdown_info}\n"
            f"Fill in each blank with the correct option from the choices given. "
            f"Think step-by-step, then on the LAST line write ONLY:\n"
            f"ANSWER: 1: chosen_option; 2: chosen_option"
        )

    else:
        return (
            f"{context_block}"
            f"Question: {question}\n\n"
            f"Think step-by-step, then on the LAST line write ONLY:\n"
            f"ANSWER: <your answer>"
        )


def _extract_answer_line(response_text):
    """Extract the answer from the ANSWER: line at the end of a chain-of-thought response.

    Falls back to the full response text if no ANSWER: line is found (backwards
    compatible with models that ignore the reasoning instruction).
    """
    import re
    # Search for the last "ANSWER:" line (case-insensitive)
    match = re.search(r'(?i)^ANSWER:\s*(.+)$', response_text.strip(), re.MULTILINE)
    if match:
        return match.group(1).strip()
    # Fallback: return the last non-empty line
    lines = [l.strip() for l in response_text.strip().split("\n") if l.strip()]
    return lines[-1] if lines else response_text.strip()


def parse_gpt_response(response_text, question_data):
    """Parse the model's response into an action dict."""
    q_type = question_data["type"]
    choices = question_data.get("choices", [])

    if q_type == "ordering":
        import re
        # For ordering, we need the numbered list — look after "ANSWER:" or
        # "Correct order:" if present, otherwise use the full response.
        text = response_text.strip()
        # Try to find everything after the last ANSWER: marker
        answer_match = re.search(r'(?i)ANSWER:\s*\n?([\s\S]+)$', text)
        if answer_match:
            text = answer_match.group(1).strip()

        lines = text.split("\n")
        ordered_items = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            line = re.sub(r'^\d+[\.\)\:]\s*', '', line).strip()
            line = re.sub(r'^-\s*', '', line).strip()
            if line:
                ordered_items.append(line)

        return {
            "type": "ordering",
            "answer_text": " -> ".join(ordered_items),
            "ordered_items": ordered_items,
            "item_elements": question_data.get("item_elements", []),
            "original_items": question_data.get("items", []),
            "targets": [],
            "values": [],
        }

    elif q_type == "matching":
        import re
        text = response_text.strip()
        answer_match = re.search(r'(?i)ANSWER:\s*\n?([\s\S]+)$', text)
        if answer_match:
            text = answer_match.group(1).strip()

        lines = text.split("\n")
        matches = []
        for line in lines:
            line = line.strip()
            if "->" in line:
                parts = line.split("->", 1)
                left = parts[0].strip().lstrip("- ")
                right = parts[1].strip()
                matches.append({"source": left, "target": right})
            elif ":" in line and not line[0].isdigit():
                parts = line.split(":", 1)
                left = parts[0].strip().lstrip("- ")
                right = parts[1].strip()
                matches.append({"source": left, "target": right})

        return {
            "type": "matching",
            "answer_text": ", ".join(f"{m['source']}->{m['target']}" for m in matches),
            "matches": matches,
            "source_elements": question_data.get("source_elements", []),
            "target_elements": question_data.get("target_elements", []),
            "sources": question_data.get("sources", []),
            "targets_list": question_data.get("targets", []),
            "values": [],
        }

    elif q_type == "mc_single":
        answer = _extract_answer_line(response_text)
        letter = answer.upper().replace(")", "").replace(".", "").replace(":", "").strip()
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
        answer = _extract_answer_line(response_text)
        letters = [l.strip().upper().replace(")", "").replace(".", "")
                   for l in answer.split(",")]

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
        import re
        blank_count = question_data.get("blank_count", 1)
        inputs = question_data.get("input_elements", [])

        answer = _extract_answer_line(response_text)

        if blank_count > 1:
            raw = answer
            values = [v.strip() for v in raw.split(";") if v.strip()]

            if len(values) == 1 and len(inputs) > 1:
                values = [v.strip() for v in raw.split(",") if v.strip()]

            if len(values) == 1 and len(inputs) > 1:
                values = [v.strip() for v in raw.split("\n") if v.strip()]

            cleaned = []
            for v in values:
                v = re.sub(r'^\d+[\.:]\s*', '', v)
                cleaned.append(v)
            values = cleaned

            while len(values) < len(inputs):
                values.append("")
            values = values[:len(inputs)]
        else:
            values = [answer]

        return {
            "type": "multi_type",
            "answer_text": "; ".join(values),
            "targets": inputs,
            "values": values,
        }

    elif q_type == "dropdown":
        answer = _extract_answer_line(response_text)
        import re
        # Parse "1: value; 2: value" or "1: value\n2: value"
        parts = re.split(r';\s*|\n', answer)
        values = []
        for part in parts:
            part = part.strip()
            if ":" in part:
                val = part.split(":", 1)[1].strip()
                values.append(val)
            elif part:
                values.append(part)

        return {
            "type": "dropdown",
            "answer_text": ", ".join(values),
            "targets": question_data.get("input_elements", []),
            "values": values,
        }

    else:
        answer = _extract_answer_line(response_text)
        return {
            "type": "type",
            "answer_text": answer,
            "targets": question_data.get("input_elements", []),
            "values": [answer],
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
