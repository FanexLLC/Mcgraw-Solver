import random
import logging
from openai import OpenAI
import config
import human

logger = logging.getLogger(__name__)

client = None


def init_client(api_key=None):
    """Initialize the OpenAI client."""
    global client
    key = api_key or config.OPENAI_API_KEY
    if not key or key == "your-key-here":
        raise ValueError("OpenAI API key not set. Please enter your API key.")
    client = OpenAI(api_key=key)


def get_answer(question_data):
    """Send a question to GPT and get the answer back."""
    if client is None:
        init_client()

    q_type = question_data["type"]
    question = question_data["question"]
    context = question_data.get("context", "")
    choices = question_data.get("choices", [])

    blank_count = question_data.get("blank_count", 1)
    prompt = _build_prompt(q_type, question, context, choices, blank_count)

    response = client.chat.completions.create(
        model=config.GPT_MODEL,
        temperature=config.GPT_TEMPERATURE,
        messages=[
            {"role": "system", "content": "You are a knowledgeable academic assistant. Answer precisely and concisely."},
            {"role": "user", "content": prompt},
        ],
    )

    answer_text = response.choices[0].message.content.strip()
    logger.info(f"GPT response: {answer_text}")

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
                f"Reply with ONLY the answers separated by semicolons. "
                f"Do NOT use 'and' or any other words between answers. "
                f"Format: answer1; answer2; answer3\n"
                f"Each answer should be a single word or short phrase for one blank.\n\n"
                f"Question: {question}\n"
                f"{context_section}\n"
                f"Answer:"
            )
        else:
            return (
                f"Answer this question with a short, precise answer. "
                f"Reply with ONLY the answer text, nothing else.\n\n"
                f"Question: {question}\n"
                f"{context_section}\n"
                f"Answer:"
            )

    elif q_type == "dropdown":
        # For dropdown, choices contains per-dropdown options
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
        # Extract the letter from the response
        letter = response_text.strip().upper()
        # Handle responses like "A)" or "A." or just "A"
        letter = letter.replace(")", "").replace(".", "").replace(":", "").strip()
        if len(letter) > 1:
            letter = letter[0]

        # Find the matching choice element
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
        # Extract multiple letters
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
            # Parse "answer1; answer2" format
            raw = response_text.strip()
            # Remove any "and" connectors
            raw = raw.replace(" and ", "; ")
            values = [v.strip() for v in raw.split(";") if v.strip()]

            # Fallback: try comma separation if semicolons didn't work
            if len(values) == 1 and len(inputs) > 1:
                values = [v.strip() for v in raw.split(",") if v.strip()]

            # Fallback: try newline separation
            if len(values) == 1 and len(inputs) > 1:
                values = [v.strip() for v in raw.split("\n") if v.strip()]

            # Strip numbering like "1:" or "1."
            cleaned = []
            for v in values:
                import re
                v = re.sub(r'^\d+[\.:]\s*', '', v)
                cleaned.append(v)
            values = cleaned

            # Pad or trim to match input count
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
        # Parse "1: option\n2: option" format
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
        # Pick a random wrong choice
        correct_letter = action.get("answer_text", "")
        wrong_choices = [c for c in choices if c["label"].upper() != correct_letter]
        if wrong_choices:
            wrong = random.choice(wrong_choices)
            action["answer_text"] = wrong["label"]
            action["targets"] = [wrong.get("element")] if wrong.get("element") else []
            logger.info(f"Intentional miss: changed {correct_letter} -> {wrong['label']}")
            return action, True

    elif q_type == "mc_multi" and len(choices) > 1:
        # Remove one correct answer or add a wrong one
        if random.random() < 0.5 and len(action["targets"]) > 1:
            # Remove a random correct answer
            idx = random.randint(0, len(action["targets"]) - 1)
            action["targets"].pop(idx)
            logger.info("Intentional miss: removed one correct answer from multi-select")
            return action, True

    return action, False
