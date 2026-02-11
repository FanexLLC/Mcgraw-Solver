import random
import logging
from selenium.webdriver.common.by import By
import browser
import human

logger = logging.getLogger(__name__)

# ============================================================================
# SELECTORS - Updated from actual SmartBook HTML inspection
# ============================================================================
SELECTORS = {
    # Question elements
    "question_prompt": ".prompt",
    "responses_container": ".responses-container",
    "question_fieldset": ".multiple-choice-fieldset, .true-false-fieldset",
    "choice_row": ".choice-row",
    "choice_radio": "input.form-check-input[type='radio']",
    "choice_checkbox": "input.form-check-input[type='checkbox']",
    "choice_text": ".choiceText",
    "choice_clickable": ".choice",

    # Fill-in-the-blank
    "text_input": "input[type='text'], textarea, input.form-control, input.fitb-input",
    "dropdown_select": "select, select.form-select",
    "blank_indicator": "span._visuallyHidden",

    # Ordering (sortable) questions — uses react-beautiful-dnd
    "sortable_component": ".sortable-component, [class*='probe-type-sortable']",
    "sortable_item": ".sortable-component .responses-container .choice-item[data-react-beautiful-dnd-draggable]",
    "sortable_item_text": ".content p",

    # Matching (drag-to-match) questions
    "matching_component": ".matching-component, [class*='probe-type-matching'], "
                          "[class*='probe-type-categorize']",
    "matching_label": ".matching-component .match-row .match-prompt-label .content p",
    "matching_drop_zone": ".matching-component .match-row .match-single-response-wrapper",
    "matching_choice": ".matching-component .choices-container .choice-item-wrapper",
    "matching_choice_text": ".content p",

    # Confidence buttons (these act as submit + next)
    "confidence_container": "awd-confidence-buttons, .confidence-buttons-container",
    "confidence_high": "button.btn-confidence:nth-child(1)",
    "confidence_medium": "button.btn-confidence:nth-child(2)",
    "confidence_low": "button.btn-confidence:nth-child(3)",
    "confidence_any": "button.btn-confidence",

    # Reading button
    "reading_button": "button.reading-button",

    # Concept resource / recharge page (shown after wrong answers)
    # NOTE: .lr__action-label appears on ALL pages ("Need help?"), so don't use it for detection.
    # The recharge-specific element is the lr-tray button with "continue" text.
    "recharge_tray_button": "button[data-automation-id='lr-tray_button'], "
                            "button.lr-tray-expand-button",
    "read_about_concept": ".lr__action-label",
    "to_questions_button": "button[data-automation-id='reading-questions-button']",

    # Page type indicators
    "complete_indicator": "[class*='score-summary'], [class*='assignment-complete'], "
                          "[class*='completion'], [class*='results-container']",
    "loading_spinner": "[class*='spinner'], .loader, [class*='loading-indicator']",

    # Navigation bar (always present during questions)
    "nav_bar": "awd-navigation-bar, .main-container__navigation-bar",

    # Next Question button (appears after answering)
    "next_question": "button.next-button, button.btn-primary.next-button",
}


def detect_page_type(driver):
    """Detect what type of page is currently showing."""
    # Check if page is still loading
    if not browser.is_page_ready(driver):
        return "loading"

    # Check loading spinner
    if _has_element(driver, SELECTORS["loading_spinner"]):
        return "loading"

    # Check completion
    if _has_element(driver, SELECTORS["complete_indicator"]):
        return "complete"

    # Check for concept resource / recharge page (mandatory "Select a concept resource to continue")
    if _is_recharge_page(driver):
        return "recharge"

    # Check for question (responses container or fieldset = question is showing)
    if _has_element(driver, SELECTORS["responses_container"]):
        return "question"

    # Check for true/false or MC fieldset
    if _has_element(driver, SELECTORS["question_fieldset"]):
        return "question"

    # Check for text inputs (fill-in-the-blank question)
    if _has_element(driver, SELECTORS["text_input"]):
        return "question"

    # Check if nav bar is present but no question (reading screen)
    if _has_element(driver, SELECTORS["nav_bar"]):
        # Nav bar exists but no question content - likely a reading/review screen
        if _has_element(driver, SELECTORS["reading_button"]):
            return "reading"

    return "unknown"


def parse_question(driver):
    """Extract question data from the current page."""
    result = {
        "type": "unknown",
        "question": "",
        "choices": [],
        "context": "",
        "input_elements": [],
    }

    # Get question text - look for text content above the responses container
    # SmartBook puts question text in the content area before responses
    question_text = _extract_question_text(driver)
    result["question"] = question_text

    # Extract any reading/textbook context from the page
    result["context"] = extract_page_context(driver)

    # Check for ordering (sortable) question first
    sortable = browser.find_elements_safe(driver, SELECTORS["sortable_component"])
    if sortable:
        result["type"] = "ordering"
        result["items"] = _extract_sortable_items(driver)
        result["item_elements"] = browser.find_elements_safe(
            driver, SELECTORS["sortable_item"])
        logger.info(f"Parsed question: type=ordering, "
                    f"question='{result['question'][:60]}...', "
                    f"items={len(result['items'])}")
        return result

    # Check for matching question
    matching = browser.find_elements_safe(driver, SELECTORS["matching_component"])
    if matching:
        result["type"] = "matching"
        match_data = _extract_matching_data(driver)
        result["sources"] = match_data["sources"]
        result["targets"] = match_data["targets"]
        result["source_elements"] = match_data["source_elements"]
        result["target_elements"] = match_data["target_elements"]
        logger.info(f"Parsed question: type=matching, "
                    f"question='{result['question'][:60]}...', "
                    f"sources={len(result['sources'])}, targets={len(result['targets'])}")
        return result

    # Detect question type and extract choices
    choice_rows = browser.find_elements_safe(driver, SELECTORS["choice_row"])
    radios = browser.find_elements_safe(driver, SELECTORS["choice_radio"])
    checkboxes = browser.find_elements_safe(driver, SELECTORS["choice_checkbox"])
    text_inputs = browser.find_elements_safe(driver, SELECTORS["text_input"])
    dropdowns = browser.find_elements_safe(driver, SELECTORS["dropdown_select"])

    if checkboxes and len(checkboxes) > 0:
        result["type"] = "mc_multi"
        result["choices"] = _extract_choices_from_rows(choice_rows, checkboxes)

    elif radios and len(radios) > 0:
        result["type"] = "mc_single"
        result["choices"] = _extract_choices_from_rows(choice_rows, radios)

    elif text_inputs:
        result["type"] = "fill"
        result["input_elements"] = text_inputs
        result["blank_count"] = len(text_inputs)

    elif dropdowns:
        result["type"] = "dropdown"
        result["input_elements"] = dropdowns
        result["choices"] = _extract_dropdown_options(dropdowns)

    logger.info(f"Parsed question: type={result['type']}, "
                f"question='{result['question'][:60]}...', "
                f"choices={len(result['choices'])}")
    return result


def _extract_question_text(driver):
    """Extract the question text from the .prompt element."""
    try:
        # Primary: the question text lives in div.prompt
        prompts = browser.find_elements_safe(driver, SELECTORS["question_prompt"])
        if prompts:
            # Get the visible text (blanks show as ______)
            text = prompts[0].text.strip()
            if text:
                return text

        # Fallback: grab <p> tags above .responses-container via JS
        script = """
        var responses = document.querySelector('.responses-container');
        if (!responses) return '';
        var parent = responses.parentElement;
        var texts = [];
        var allP = parent.querySelectorAll('p');
        for (var i = 0; i < allP.length; i++) {
            var p = allP[i];
            if (responses.contains(p)) continue;
            if (p.classList.contains('_visuallyHidden')) continue;
            var text = p.textContent.trim();
            if (text) texts.push(text);
        }
        return texts.join(' ');
        """
        body_text = driver.execute_script(script)
        if body_text:
            return body_text.strip()

        return ""

    except Exception as e:
        logger.warning(f"Error extracting question text: {e}")
        return ""


def extract_page_context(driver):
    """Extract any reading/textbook context visible on the page.

    SmartBook often shows highlighted passages, reading panes, or concept
    text alongside questions. This context helps GPT answer more accurately.
    """
    context_parts = []

    try:
        # 1. Check for highlighted/marked text on the page (SmartBook highlights relevant passages)
        script = """
        var texts = [];
        // Highlighted/marked text
        var marks = document.querySelectorAll('mark, .highlight, [class*="highlight"], .marked-text');
        marks.forEach(function(el) {
            var t = el.textContent.trim();
            if (t && t.length > 10) texts.push(t);
        });
        // Reading pane content (if open)
        var readingPane = document.querySelector('.reading-pane, .reader-content, [class*="reader"], [class*="reading-content"]');
        if (readingPane) {
            var pTags = readingPane.querySelectorAll('p');
            pTags.forEach(function(p) {
                var t = p.textContent.trim();
                if (t && t.length > 20) texts.push(t);
            });
        }
        return texts;
        """
        highlighted = driver.execute_script(script)
        if highlighted:
            context_parts.extend(highlighted)

        # 2. Extract the DLC (Digital Learning Content) view container text
        # This contains the question context area above the responses
        script2 = """
        var texts = [];
        var viewContainer = document.querySelector('.view-container');
        if (viewContainer) {
            var dlcContent = viewContainer.querySelector('.dlc_question');
            if (dlcContent) {
                // Get all paragraph text that's NOT inside responses
                var responses = dlcContent.querySelector('.responses-container');
                var allP = dlcContent.querySelectorAll('p');
                for (var i = 0; i < allP.length; i++) {
                    var p = allP[i];
                    if (responses && responses.contains(p)) continue;
                    if (p.classList.contains('_visuallyHidden')) continue;
                    if (p.closest('.responses-container')) continue;
                    if (p.closest('.choices-container')) continue;
                    var t = p.textContent.trim();
                    if (t && t.length > 15) texts.push(t);
                }
            }
        }
        return texts;
        """
        dlc_text = driver.execute_script(script2)
        if dlc_text:
            context_parts.extend(dlc_text)

    except Exception as e:
        logger.warning(f"Error extracting page context: {e}")

    # Deduplicate and limit length
    seen = set()
    unique_parts = []
    for part in context_parts:
        if part not in seen:
            seen.add(part)
            unique_parts.append(part)

    context = "\n".join(unique_parts)
    # Limit to ~2000 chars to avoid bloating the prompt
    if len(context) > 2000:
        context = context[:2000] + "..."

    if context:
        logger.info(f"Extracted {len(context)} chars of page context")

    return context


def _extract_choices_from_rows(choice_rows, input_elements):
    """Extract choice labels and text from choice rows."""
    choices = []
    labels = "ABCDEFGHIJ"

    for i, row in enumerate(choice_rows):
        label = labels[i] if i < len(labels) else str(i + 1)

        # Get the choice text from .choiceText inside this row
        text = ""
        try:
            text_el = row.find_element(By.CSS_SELECTOR, SELECTORS["choice_text"])
            text = text_el.text.strip()
        except Exception:
            text = row.text.strip()

        # The clickable element — use the radio/checkbox input directly for Angular
        clickable = input_elements[i] if i < len(input_elements) else None
        if not clickable:
            try:
                clickable = row.find_element(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
            except Exception:
                try:
                    clickable = row.find_element(By.CSS_SELECTOR, "label.form-check-label")
                except Exception:
                    clickable = row

        choices.append({
            "label": label,
            "text": text,
            "element": clickable,
        })

    return choices


def _extract_dropdown_options(dropdowns):
    """Extract options from dropdown select elements."""
    choices = []
    for dropdown in dropdowns:
        try:
            options = dropdown.find_elements(By.TAG_NAME, "option")
            opt_texts = [o.text.strip() for o in options if o.text.strip()]
            choices.append({"options": opt_texts, "element": dropdown})
        except Exception:
            choices.append({"options": [], "element": dropdown})
    return choices


def _extract_sortable_items(driver):
    """Extract item texts from a sortable/ordering question."""
    items = []
    elements = browser.find_elements_safe(driver, SELECTORS["sortable_item"])
    for el in elements:
        try:
            text_el = el.find_element(By.CSS_SELECTOR, SELECTORS["sortable_item_text"])
            text = text_el.text.strip()
        except Exception:
            text = el.text.strip()
        if text:
            items.append(text)
    return items


def _extract_matching_data(driver):
    """Extract matching question data: labels, drop zones, and draggable choices."""
    labels = []
    choices = []

    # Left-side labels (fixed prompts like "Initiator", "Influencer", etc.)
    label_elements = browser.find_elements_safe(driver, SELECTORS["matching_label"])
    for el in label_elements:
        text = el.text.strip()
        if text:
            labels.append(text)

    # Drop zones (one per label, same order as labels)
    drop_zone_elements = browser.find_elements_safe(driver, SELECTORS["matching_drop_zone"])

    # Draggable choice items (descriptions to drag into drop zones)
    choice_elements = browser.find_elements_safe(driver, SELECTORS["matching_choice"])
    for el in choice_elements:
        try:
            text_el = el.find_element(By.CSS_SELECTOR, SELECTORS["matching_choice_text"])
            choices.append(text_el.text.strip())
        except Exception:
            choices.append(el.text.strip())

    logger.info(f"Matching: found {len(labels)} labels, {len(choices)} choices, "
                f"{len(drop_zone_elements)} drop zones")

    return {
        "sources": labels,                    # Left items (for GPT prompt)
        "targets": choices,                   # Right items (for GPT prompt)
        "source_elements": drop_zone_elements,  # Drop zones (indexed same as labels)
        "target_elements": choice_elements,     # Draggable choices (indexed same as choices)
    }


def submit_with_confidence(driver):
    """Click a confidence button to submit the answer and advance.

    In SmartBook, confidence buttons act as the submit/next button.
    Randomly picks High (60%), Medium (30%), or Low (10%).
    """
    roll = random.random()
    if roll < 0.6:
        selector = SELECTORS["confidence_high"]
        level = "High"
    elif roll < 0.9:
        selector = SELECTORS["confidence_medium"]
        level = "Medium"
    else:
        selector = SELECTORS["confidence_low"]
        level = "Low"

    el = browser.wait_for_clickable(driver, selector, timeout=10)
    if el:
        human.random_delay(0.3, 1.0)
        browser.safe_click(driver, el)
        logger.info(f"Submitted with {level} confidence")
        return True

    # Fallback: try any confidence button
    el = browser.wait_for_clickable(driver, SELECTORS["confidence_any"], timeout=5)
    if el:
        human.random_delay(0.3, 1.0)
        browser.safe_click(driver, el)
        logger.info("Submitted with confidence button (fallback)")
        return True

    logger.warning("Could not find any confidence button to submit")
    return False


def click_next_button(driver):
    """Try to advance the page. First tries confidence buttons, then other buttons."""
    # Primary: confidence buttons (the main submit mechanism)
    if submit_with_confidence(driver):
        return True

    # Fallback: look for any Next/Continue/Submit buttons
    buttons = browser.find_elements_safe(driver, "button")
    for btn in buttons:
        try:
            text = btn.text.strip().lower()
            if text in ("next", "continue", "submit", "done", "ok"):
                human.random_delay(0.3, 1.0)
                browser.safe_click(driver, btn)
                logger.info(f"Clicked button: {text}")
                return True
        except Exception:
            continue

    logger.warning("Could not find any button to advance")
    return False


def click_next_question(driver):
    """Click the 'Next Question' button that appears after answering."""
    el = browser.wait_for_clickable(driver, SELECTORS["next_question"], timeout=10)
    if el:
        human.random_delay(0.3, 1.0)
        browser.safe_click(driver, el)
        logger.info("Clicked 'Next Question' button")
        return True
    logger.warning("Could not find 'Next Question' button")
    return False


def _is_recharge_page(driver):
    """Check if the recharge tray button is present with 'continue' text.

    The tray button on normal pages says 'Need help? Review these concept resources.'
    The tray button on recharge pages says 'Select a concept resource to continue.'
    """
    tray_buttons = browser.find_elements_safe(driver, SELECTORS["recharge_tray_button"])
    for btn in tray_buttons:
        try:
            text = btn.text.strip().lower()
            if "continue" in text:
                return True
        except Exception:
            continue
    return False


def needs_resource_review(driver):
    """Check if the current page requires reviewing a concept resource before continuing.

    This happens after wrong answers — SmartBook shows 'Select a concept resource to continue'
    with a 'Read About the Concept' link.
    """
    return _is_recharge_page(driver)


def handle_recharge_page(driver):
    """Handle the concept resource / recharge page.

    When answers are wrong, SmartBook forces a reading detour:
    1. Click 'Read About the Concept'
    2. Reading page opens with textbook content
    3. Scroll down to simulate reading
    4. Click 'To Questions' to return
    """
    import time

    # Step 1: Click "Read About the Concept"
    read_links = browser.find_elements_safe(driver, SELECTORS["read_about_concept"])
    clicked = False
    for el in read_links:
        try:
            if "read about" in el.text.strip().lower():
                human.random_delay(1.0, 2.0)
                # Click the parent element (the span is inside a clickable container)
                try:
                    parent = el.find_element(By.XPATH, "./..")
                    browser.safe_click(driver, parent)
                except Exception:
                    browser.safe_click(driver, el)
                logger.info("Clicked 'Read About the Concept'")
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        # Fallback: look for any element with "read about" text
        buttons = browser.find_elements_safe(driver, "a, button, span")
        for btn in buttons:
            try:
                text = btn.text.strip().lower()
                if "read about" in text:
                    human.random_delay(1.0, 2.0)
                    browser.safe_click(driver, btn)
                    logger.info(f"Clicked fallback: '{btn.text.strip()}'")
                    clicked = True
                    break
            except Exception:
                continue

    if not clicked:
        logger.warning("Could not find 'Read About the Concept' link")
        return False

    # Step 2: Wait for reading page to load
    time.sleep(3)

    # Step 3: Scroll down to simulate reading
    try:
        driver.execute_script("window.scrollBy(0, 400);")
        human.random_delay(2.0, 4.0)
        driver.execute_script("window.scrollBy(0, 400);")
        human.random_delay(1.0, 3.0)
    except Exception:
        pass

    # Step 4: Click "To Questions" button to return
    to_questions = browser.wait_for_clickable(
        driver, SELECTORS["to_questions_button"], timeout=10)
    if to_questions:
        human.random_delay(1.0, 2.0)
        browser.safe_click(driver, to_questions)
        logger.info("Clicked 'To Questions' to return")
        time.sleep(2)
        return True

    # Fallback: look for any button with "questions" text
    buttons = browser.find_elements_safe(driver, "button")
    for btn in buttons:
        try:
            text = btn.text.strip().lower()
            if "question" in text:
                human.random_delay(1.0, 2.0)
                browser.safe_click(driver, btn)
                logger.info(f"Clicked fallback: '{btn.text.strip()}'")
                time.sleep(2)
                return True
        except Exception:
            continue

    logger.warning("Could not find 'To Questions' button")
    return False


def _has_element(driver, selector):
    """Check if an element matching the selector exists on the page."""
    elements = browser.find_elements_safe(driver, selector)
    return len(elements) > 0
