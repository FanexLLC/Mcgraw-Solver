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

    # Confidence buttons (these act as submit + next)
    "confidence_container": "awd-confidence-buttons, .confidence-buttons-container",
    "confidence_high": "button.btn-confidence:nth-child(1)",
    "confidence_medium": "button.btn-confidence:nth-child(2)",
    "confidence_low": "button.btn-confidence:nth-child(3)",
    "confidence_any": "button.btn-confidence",

    # Reading button
    "reading_button": "button.reading-button",

    # Concept resource / recharge page (shown after too many wrong answers)
    "concept_resource": "[class*='concept-resource'], [class*='recharge'], "
                        "[class*='resource-select'], [class*='learning-resource']",
    "resource_link": "a[class*='resource'], a[class*='concept'], "
                     "button[class*='resource'], [class*='resource-card'] a, "
                     "[class*='resource-list'] a",
    "back_to_questions": "button[class*='back'], button[class*='return'], "
                         "button[class*='continue'], button[class*='close'], "
                         "a[class*='back'], a[class*='return']",

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

    # Check for concept resource / recharge page
    if _has_element(driver, SELECTORS["concept_resource"]):
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


def handle_recharge_page(driver):
    """Handle the concept resource / recharge page.

    When too many answers are wrong, SmartBook forces a reading detour.
    Strategy: click the first resource link to open it, wait briefly,
    then look for a back/continue/close button to return to questions.
    """
    import time

    # Step 1: Click the first resource link to "open" the reading
    resource_links = browser.find_elements_safe(driver, SELECTORS["resource_link"])
    if resource_links:
        human.random_delay(1.0, 2.0)
        browser.safe_click(driver, resource_links[0])
        logger.info("Clicked concept resource link")
        human.random_delay(2.0, 4.0)
    else:
        # Try clicking any visible link or button on the page as fallback
        fallback = browser.find_elements_safe(driver, "a, button")
        for el in fallback:
            try:
                text = el.text.strip().lower()
                if any(kw in text for kw in ["open", "read", "view", "start", "select"]):
                    human.random_delay(1.0, 2.0)
                    browser.safe_click(driver, el)
                    logger.info(f"Clicked fallback resource button: {text}")
                    human.random_delay(2.0, 4.0)
                    break
            except Exception:
                continue

    # Step 2: Try to close / go back to return to questions
    # Give page time to load the resource
    time.sleep(2)

    # Look for back/return/continue/close buttons
    back_btn = browser.wait_for_clickable(driver, SELECTORS["back_to_questions"], timeout=5)
    if back_btn:
        human.random_delay(0.5, 1.5)
        browser.safe_click(driver, back_btn)
        logger.info("Clicked back/continue button to return to questions")
        return True

    # Fallback: look for any button with relevant text
    buttons = browser.find_elements_safe(driver, "button, a")
    for btn in buttons:
        try:
            text = btn.text.strip().lower()
            if any(kw in text for kw in ["back", "return", "continue", "close",
                                          "done", "next", "finish"]):
                human.random_delay(0.5, 1.5)
                browser.safe_click(driver, btn)
                logger.info(f"Clicked '{text}' to return to questions")
                return True
        except Exception:
            continue

    logger.warning("Could not find a way to exit the recharge page")
    return False


def _has_element(driver, selector):
    """Check if an element matching the selector exists on the page."""
    elements = browser.find_elements_safe(driver, selector)
    return len(elements) > 0
