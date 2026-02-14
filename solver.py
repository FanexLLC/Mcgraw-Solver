from __future__ import annotations
import re
import random
import logging
import requests

import config
import human
from models import QuestionData, Action

logger = logging.getLogger(__name__)

_access_key: str | None = None
_server_url: str | None = None


def init_client(access_key: str | None = None) -> None:
    """Store the access key and verify the server is reachable."""
    global _access_key, _server_url
    _access_key = access_key or config.ACCESS_KEY
    _server_url = config.SERVER_URL

    if not _access_key:
        raise ValueError("Access key not set. Please enter your access key.")

    try:
        resp = requests.get(f"{_server_url}/health", timeout=5)
        resp.raise_for_status()
    except requests.ConnectionError:
        raise ConnectionError(f"Cannot reach server at {_server_url}. Is it running?")
    except requests.HTTPError as e:
        raise ConnectionError(f"Server error: {e}")


def get_answer(question_data: QuestionData) -> Action:
    """Send a question to the server and return a parsed Action."""
    if _access_key is None:
        init_client()

    prompt = _build_prompt(question_data)

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
    elif resp.status_code == 429:
        raise RuntimeError("Rate limit exceeded. Try again later.")
    elif resp.status_code != 200:
        error_msg = resp.json().get("error", "Unknown server error")
        raise RuntimeError(f"Server error: {error_msg}")

    answer_text = resp.json()["answer"]
    logger.info(f"Server response: {answer_text}")

    return parse_gpt_response(answer_text, question_data)


# ── Prompt Building ───────────────────────────────────────────────

def _build_prompt(qd: QuestionData) -> str:
    """Build the prompt based on question type."""
    ctx = ""
    if qd.context:
        ctx = (
            f"The following passage is from the textbook. Use it as your PRIMARY "
            f"source when answering:\n\n{qd.context}\n\n"
        )

    if qd.type == "ordering":
        items_text = "\n".join(f"- {item}" for item in qd.items)
        return (
            f"{ctx}"
            f"Put the following items in the correct order.\n\n"
            f"Question: {qd.question}\n\n"
            f"Items (currently in this order):\n{items_text}\n\n"
            f"Reply with ONLY the items in the correct order, one per line, "
            f"numbered 1, 2, 3, etc. Use the EXACT text of each item.\n\n"
            f"Correct order:"
        )

    if qd.type == "matching":
        sources_text = "\n".join(f"- {s}" for s in qd.sources)
        targets_text = "\n".join(f"- {t}" for t in qd.targets)
        return (
            f"{ctx}"
            f"Match each item on the left with the correct item on the right.\n\n"
            f"Question: {qd.question}\n\n"
            f"Left items:\n{sources_text}\n\n"
            f"Right items:\n{targets_text}\n\n"
            f"Reply with each match on its own line in the format:\n"
            f"Left Item -> Right Item\n"
            f"Use the EXACT text of each item.\n\n"
            f"Matches:"
        )

    if qd.type == "mc_single":
        choices_text = "\n".join(f"{c['label']}) {c['text']}" for c in qd.choices)
        labels = ", ".join(c["label"] for c in qd.choices)
        return (
            f"{ctx}"
            f"Question: {qd.question}\n\n"
            f"{choices_text}\n\n"
            f"Think step-by-step, then on the LAST line write ONLY:\n"
            f"ANSWER: <letter>\n"
            f"where <letter> is one of {labels}."
        )

    if qd.type == "mc_multi":
        choices_text = "\n".join(f"{c['label']}) {c['text']}" for c in qd.choices)
        return (
            f"{ctx}"
            f"Question: {qd.question}\n\n"
            f"{choices_text}\n\n"
            f"Select ALL correct options. Think step-by-step, then on the LAST "
            f"line write ONLY:\n"
            f"ANSWER: <letters separated by commas>\n"
            f"Example: ANSWER: A, C"
        )

    if qd.type == "fill":
        if qd.blank_count > 1:
            return (
                f"{ctx}"
                f"Question: {qd.question}\n\n"
                f"This question has exactly {qd.blank_count} blanks to fill in. "
                f"Each blank may require one or more words.\n\n"
                f"Think step-by-step using the textbook passage above, then on "
                f"the LAST line write ONLY:\n"
                f"ANSWER: answer1; answer2; answer3\n"
                f"Separate each blank's answer with a semicolon. Use the exact "
                f"terminology from the textbook passage when possible."
            )
        return (
            f"{ctx}"
            f"Question: {qd.question}\n\n"
            f"Fill in the blank. The answer may be one or more words.\n\n"
            f"Think step-by-step using the textbook passage above, then on "
            f"the LAST line write ONLY:\n"
            f"ANSWER: <your answer>\n"
            f"Use the exact terminology from the textbook passage when possible."
        )

    if qd.type == "dropdown":
        dropdown_info = ""
        for i, c in enumerate(qd.choices):
            opts = ", ".join(c.get("options", []))
            dropdown_info += f"Blank {i+1} options: {opts}\n"
        return (
            f"{ctx}"
            f"Sentence: {qd.question}\n\n"
            f"{dropdown_info}\n"
            f"Fill in each blank with the correct option from the choices given. "
            f"Think step-by-step, then on the LAST line write ONLY:\n"
            f"ANSWER: 1: chosen_option; 2: chosen_option"
        )

    # Fallback
    return (
        f"{ctx}"
        f"Question: {qd.question}\n\n"
        f"Think step-by-step, then on the LAST line write ONLY:\n"
        f"ANSWER: <your answer>"
    )


# ── Response Parsing ──────────────────────────────────────────────

def _extract_answer_line(response_text: str) -> str:
    """Extract the answer from the ANSWER: line at the end of a chain-of-thought response."""
    match = re.search(r'(?i)^ANSWER:\s*(.+)$', response_text.strip(), re.MULTILINE)
    if match:
        return match.group(1).strip()
    lines = [l.strip() for l in response_text.strip().split("\n") if l.strip()]
    return lines[-1] if lines else response_text.strip()


def parse_gpt_response(response_text: str, qd: QuestionData) -> Action:
    """Parse the model's response into an Action."""

    if qd.type == "ordering":
        text = response_text.strip()
        answer_match = re.search(r'(?i)ANSWER:\s*\n?([\s\S]+)$', text)
        if answer_match:
            text = answer_match.group(1).strip()

        ordered_items = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            line = re.sub(r'^\d+[\.\)\:]\s*', '', line).strip()
            line = re.sub(r'^-\s*', '', line).strip()
            if line:
                ordered_items.append(line)

        return Action(
            type="ordering",
            answer_text=" -> ".join(ordered_items),
            ordered_items=ordered_items,
            item_elements=qd.item_elements,
            original_items=qd.items,
        )

    if qd.type == "matching":
        text = response_text.strip()
        answer_match = re.search(r'(?i)ANSWER:\s*\n?([\s\S]+)$', text)
        if answer_match:
            text = answer_match.group(1).strip()

        matches = []
        for line in text.split("\n"):
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

        return Action(
            type="matching",
            answer_text=", ".join(f"{m['source']}->{m['target']}" for m in matches),
            matches=matches,
            source_elements=qd.source_elements,
            target_elements=qd.target_elements,
            sources=qd.sources,
            targets_list=qd.targets,
        )

    if qd.type == "mc_single":
        answer = _extract_answer_line(response_text)
        letter = answer.upper().replace(")", "").replace(".", "").replace(":", "").strip()
        if len(letter) > 1:
            letter = letter[0]

        target = None
        for c in qd.choices:
            if c["label"].upper() == letter:
                target = c.get("element")
                break

        return Action(
            type="click",
            answer_text=letter,
            targets=[target] if target else [],
        )

    if qd.type == "mc_multi":
        answer = _extract_answer_line(response_text)
        letters = [l.strip().upper().replace(")", "").replace(".", "")
                   for l in answer.split(",")]

        targets = []
        for letter in letters:
            for c in qd.choices:
                if c["label"].upper() == letter:
                    el = c.get("element")
                    if el:
                        targets.append(el)
                    break

        return Action(
            type="multi_click",
            answer_text=", ".join(letters),
            targets=targets,
        )

    if qd.type == "fill":
        inputs = qd.input_elements
        answer = _extract_answer_line(response_text)

        if qd.blank_count > 1:
            values = [v.strip() for v in answer.split(";") if v.strip()]
            if len(values) == 1 and len(inputs) > 1:
                values = [v.strip() for v in answer.split(",") if v.strip()]
            if len(values) == 1 and len(inputs) > 1:
                values = [v.strip() for v in answer.split("\n") if v.strip()]
            values = [re.sub(r'^\d+[\.:]\s*', '', v) for v in values]
            while len(values) < len(inputs):
                values.append("")
            values = values[:len(inputs)]
        else:
            values = [answer]

        return Action(
            type="multi_type",
            answer_text="; ".join(values),
            targets=inputs,
            values=values,
        )

    if qd.type == "dropdown":
        answer = _extract_answer_line(response_text)
        parts = re.split(r';\s*|\n', answer)
        values = []
        for part in parts:
            part = part.strip()
            if ":" in part:
                val = part.split(":", 1)[1].strip()
                values.append(val)
            elif part:
                values.append(part)

        return Action(
            type="dropdown",
            answer_text=", ".join(values),
            targets=qd.input_elements,
            values=values,
        )

    # Fallback
    answer = _extract_answer_line(response_text)
    return Action(
        type="type",
        answer_text=answer,
        targets=qd.input_elements,
        values=[answer],
    )


# ── Intentional Error Injection ───────────────────────────────────

def maybe_inject_error(action: Action, qd: QuestionData) -> tuple[Action, bool]:
    """Possibly replace the correct answer with a wrong one to look human."""
    if not human.should_miss():
        return action, False

    if qd.type == "mc_single" and len(qd.choices) > 1:
        correct_letter = action.answer_text
        wrong_choices = [c for c in qd.choices if c["label"].upper() != correct_letter]
        if wrong_choices:
            wrong = random.choice(wrong_choices)
            action.answer_text = wrong["label"]
            action.targets = [wrong.get("element")] if wrong.get("element") else []
            logger.info(f"Intentional miss: changed {correct_letter} -> {wrong['label']}")
            return action, True

    elif qd.type == "mc_multi" and len(qd.choices) > 1:
        if random.random() < 0.5 and len(action.targets) > 1:
            idx = random.randint(0, len(action.targets) - 1)
            action.targets.pop(idx)
            logger.info("Intentional miss: removed one correct answer from multi-select")
            return action, True

    return action, False
