from __future__ import annotations
import random
import time
import logging
from typing import TYPE_CHECKING

from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
    WebDriverException,
)

import browser
import human
from page_selectors import SELECTORS
from models import QuestionData

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver

logger = logging.getLogger(__name__)


# ── Page Detection ────────────────────────────────────────────────

def detect_page_type(driver: WebDriver) -> str:
    """Detect what type of page is currently showing.

    Returns one of: "loading", "complete", "recharge", "reading", "content", "question", "unknown".
    """
    if not browser.is_page_ready(driver):
        return "loading"

    if _has_element(driver, SELECTORS["loading_spinner"]):
        return "loading"

    if _has_element(driver, SELECTORS["complete_indicator"]):
        return "complete"

    if _is_recharge_page(driver):
        return "recharge"

    if _has_element(driver, SELECTORS["responses_container"]):
        return "question"

    if _has_element(driver, SELECTORS["question_fieldset"]):
        return "question"

    if _has_element(driver, SELECTORS["text_input"]):
        return "question"

    if (_has_element(driver, "input[type='radio']") or
            _has_element(driver, "input[type='checkbox']")):
        return "question"

    if _has_element(driver, SELECTORS["nav_bar"]):
        if _has_element(driver, SELECTORS["reading_button"]):
            return "reading"

    # Check for intermediate content pages (video/intro pages with Continue button)
    if _is_content_page(driver):
        return "content"

    # Try switching into iframes as a last resort
    if _try_switch_to_question_frame(driver):
        result = detect_page_type(driver)
        if result != "unknown":
            return result
        # Nothing found inside iframe either, go back
        driver.switch_to.default_content()

    _debug_page_elements(driver)
    return "unknown"


# ── Question Parsing ──────────────────────────────────────────────

def parse_question(driver: WebDriver) -> QuestionData:
    """Extract question data from the current page."""
    qd = QuestionData()

    qd.question = _extract_question_text(driver)
    qd.context = _extract_page_context(driver)

    # Check ordering first
    sortable = browser.find_elements_safe(driver, SELECTORS["sortable_component"])
    if sortable:
        qd.type = "ordering"
        qd.items = _extract_sortable_items(driver)
        qd.item_elements = browser.find_elements_safe(driver, SELECTORS["sortable_item"])
        logger.info(f"Parsed: type=ordering, q='{qd.question[:60]}...', items={len(qd.items)}")
        return qd

    # Check matching
    matching = browser.find_elements_safe(driver, SELECTORS["matching_component"])
    if matching:
        qd.type = "matching"
        match_data = _extract_matching_data(driver)
        qd.sources = match_data["sources"]
        qd.targets = match_data["targets"]
        qd.source_elements = match_data["source_elements"]
        qd.target_elements = match_data["target_elements"]
        logger.info(f"Parsed: type=matching, q='{qd.question[:60]}...', "
                    f"sources={len(qd.sources)}, targets={len(qd.targets)}")
        return qd

    # Standard question types
    choice_rows = browser.find_elements_safe(driver, SELECTORS["choice_row"])
    radios = browser.find_elements_safe(driver, SELECTORS["choice_radio"])
    checkboxes = browser.find_elements_safe(driver, SELECTORS["choice_checkbox"])
    text_inputs = browser.find_elements_safe(driver, SELECTORS["text_input"])
    dropdowns = browser.find_elements_safe(driver, SELECTORS["dropdown_select"])

    if checkboxes:
        qd.type = "mc_multi"
        if choice_rows:
            qd.choices = _extract_choices_from_rows(choice_rows, checkboxes)
        else:
            qd.choices = _extract_choices_generic(driver, checkboxes)

    elif radios:
        qd.type = "mc_single"
        if choice_rows:
            qd.choices = _extract_choices_from_rows(choice_rows, radios)
        else:
            qd.choices = _extract_choices_generic(driver, radios)

    elif text_inputs:
        qd.type = "fill"
        qd.input_elements = text_inputs
        qd.blank_count = len(text_inputs)

    elif dropdowns:
        qd.type = "dropdown"
        qd.input_elements = dropdowns
        qd.choices = _extract_dropdown_options(dropdowns)

    logger.info(f"Parsed: type={qd.type}, q='{qd.question[:60]}...', choices={len(qd.choices)}")
    return qd


# ── Navigation ────────────────────────────────────────────────────

def submit_with_confidence(driver: WebDriver) -> bool:
    """Click a confidence button to submit the answer.

    Randomly picks High (60%), Medium (30%), or Low (10%).
    """
    roll = random.random()
    if roll < 0.6:
        selector, level = SELECTORS["confidence_high"], "High"
    elif roll < 0.9:
        selector, level = SELECTORS["confidence_medium"], "Medium"
    else:
        selector, level = SELECTORS["confidence_low"], "Low"

    el = browser.wait_for_clickable(driver, selector, timeout=10)
    if el:
        human.random_delay(0.3, 1.0)
        browser.safe_click(driver, el)
        logger.info(f"Submitted with {level} confidence")
        return True

    el = browser.wait_for_clickable(driver, SELECTORS["confidence_any"], timeout=5)
    if el:
        human.random_delay(0.3, 1.0)
        browser.safe_click(driver, el)
        logger.info("Submitted with confidence button (fallback)")
        return True

    logger.warning("Could not find any confidence button to submit")
    return False


def click_next_button(driver: WebDriver) -> bool:
    """Try to advance the page."""
    if submit_with_confidence(driver):
        return True

    buttons = browser.find_elements_safe(driver, "button")
    for btn in buttons:
        try:
            text = btn.text.strip().lower()
            if text in ("next", "continue", "submit", "done", "ok",
                        "check my work", "check answer", "check"):
                human.random_delay(0.3, 1.0)
                browser.safe_click(driver, btn)
                logger.info(f"Clicked button: {text}")
                return True
        except StaleElementReferenceException:
            continue

    logger.warning("Could not find any button to advance")
    return False


def click_next_question(driver: WebDriver) -> bool:
    """Click the 'Next Question' button that appears after answering."""
    el = browser.wait_for_clickable(driver, SELECTORS["next_question"], timeout=10)
    if el:
        human.random_delay(0.3, 1.0)
        browser.safe_click(driver, el)
        logger.info("Clicked 'Next Question' button")
        return True

    buttons = browser.find_elements_safe(driver, "a, button")
    for btn in buttons:
        try:
            text = btn.text.strip().lower()
            if text in ("next", "next question", "next >", ">"):
                if btn.is_displayed() and btn.is_enabled():
                    human.random_delay(0.3, 1.0)
                    browser.safe_click(driver, btn)
                    logger.info(f"Clicked next navigation: '{btn.text.strip()}'")
                    return True
        except StaleElementReferenceException:
            continue

    logger.warning("Could not find 'Next Question' button")
    return False


def click_continue_button(driver: WebDriver) -> bool:
    """Click the Continue button on intermediate content pages."""
    # Try to find and click Continue button (check buttons, links, and clickable divs)
    elements = browser.find_elements_safe(driver, "button, a, div[role='button']")
    for el in elements:
        try:
            text = el.text.strip().lower()
            # Check for "continue" - could be "Continue", "Continue →", etc.
            if "continue" in text and len(text) < 50:
                if el.is_displayed() and el.is_enabled():
                    human.random_delay(0.5, 1.5)
                    browser.safe_click(driver, el)
                    logger.info(f"Clicked Continue button: '{el.text.strip()}'")
                    return True
        except StaleElementReferenceException:
            continue

    # Fallback: try JavaScript click on any element with "continue" text
    try:
        result = driver.execute_script("""
            var buttons = document.querySelectorAll('button, a, [role="button"]');
            for (var i = 0; i < buttons.length; i++) {
                var btn = buttons[i];
                var text = btn.textContent.trim().toLowerCase();
                if (text.includes('continue') && text.length < 50) {
                    if (btn.offsetParent !== null) {  // Check if visible
                        btn.click();
                        return true;
                    }
                }
            }
            return false;
        """)
        if result:
            logger.info("Clicked Continue button via JavaScript fallback")
            return True
    except WebDriverException as e:
        logger.debug(f"JavaScript Continue click failed: {e}")

    logger.warning("Could not find 'Continue' button")
    return False


def needs_resource_review(driver: WebDriver) -> bool:
    """Check if the current page requires reviewing a concept resource."""
    return _is_recharge_page(driver)


def handle_recharge_page(driver: WebDriver) -> bool:
    """Handle the concept resource / recharge page."""
    # Step 1: Click "Read About the Concept"
    clicked = False
    read_links = browser.find_elements_safe(driver, SELECTORS["read_about_concept"])
    for el in read_links:
        try:
            if "read about" in el.text.strip().lower():
                human.random_delay(1.0, 2.0)
                try:
                    parent = el.find_element(By.XPATH, "./..")
                    browser.safe_click(driver, parent)
                except (NoSuchElementException, StaleElementReferenceException):
                    browser.safe_click(driver, el)
                logger.info("Clicked 'Read About the Concept'")
                clicked = True
                break
        except StaleElementReferenceException:
            continue

    if not clicked:
        buttons = browser.find_elements_safe(driver, "a, button, span")
        for btn in buttons:
            try:
                if "read about" in btn.text.strip().lower():
                    human.random_delay(1.0, 2.0)
                    browser.safe_click(driver, btn)
                    logger.info(f"Clicked fallback: '{btn.text.strip()}'")
                    clicked = True
                    break
            except StaleElementReferenceException:
                continue

    if not clicked:
        logger.warning("Could not find 'Read About the Concept' link")
        return False

    # Step 2: Wait for reading page
    time.sleep(3)

    # Step 3: Simulate reading with scrolling
    try:
        driver.execute_script("window.scrollBy(0, 400);")
        human.random_delay(2.0, 4.0)
        driver.execute_script("window.scrollBy(0, 400);")
        human.random_delay(1.0, 3.0)
    except WebDriverException:
        logger.debug("Scroll during recharge failed")

    # Step 4: Click "To Questions" to return
    to_questions = browser.wait_for_clickable(
        driver, SELECTORS["to_questions_button"], timeout=10)
    if to_questions:
        human.random_delay(1.0, 2.0)
        browser.safe_click(driver, to_questions)
        logger.info("Clicked 'To Questions' to return")
        time.sleep(2)
        return True

    buttons = browser.find_elements_safe(driver, "button")
    for btn in buttons:
        try:
            if "question" in btn.text.strip().lower():
                human.random_delay(1.0, 2.0)
                browser.safe_click(driver, btn)
                logger.info(f"Clicked fallback: '{btn.text.strip()}'")
                time.sleep(2)
                return True
        except StaleElementReferenceException:
            continue

    logger.warning("Could not find 'To Questions' button")
    return False


# ── Internal Helpers ──────────────────────────────────────────────

def _has_element(driver: WebDriver, selector: str) -> bool:
    return len(browser.find_elements_safe(driver, selector)) > 0


def _is_recharge_page(driver: WebDriver) -> bool:
    """Check if the recharge tray button is present with 'continue' text."""
    tray_buttons = browser.find_elements_safe(driver, SELECTORS["recharge_tray_button"])
    for btn in tray_buttons:
        try:
            if "continue" in btn.text.strip().lower():
                return True
        except StaleElementReferenceException:
            continue
    return False


def _is_content_page(driver: WebDriver) -> bool:
    """Check if this is an intermediate content page (video/intro) with a Continue button.

    These pages appear between questions and contain content like videos or key terms.
    They don't have question elements but have a Continue button to proceed.
    """
    # Look for Continue button (check both regular buttons and links)
    elements = browser.find_elements_safe(driver, "button, a, div[role='button']")
    has_continue = False
    for el in elements:
        try:
            text = el.text.strip().lower()
            # Check for "continue" text (exact match or with extra text like "Continue →")
            if "continue" in text and el.is_displayed() and el.is_enabled():
                # Make sure it's a prominent button (not nested in small text)
                if len(text) < 50:  # Avoid matching long paragraphs
                    has_continue = True
                    logger.debug(f"Found potential Continue button: '{el.text.strip()}'")
                    break
        except StaleElementReferenceException:
            continue

    if not has_continue:
        return False

    # Make sure it's NOT a question page (no question elements)
    has_question_elements = (
        _has_element(driver, SELECTORS["responses_container"]) or
        _has_element(driver, SELECTORS["question_fieldset"]) or
        _has_element(driver, "input[type='radio']") or
        _has_element(driver, "input[type='checkbox']") or
        _has_element(driver, SELECTORS["text_input"])
    )

    # This is a content page if it has Continue but no question elements
    is_content = has_continue and not has_question_elements
    if is_content:
        logger.info("Detected intermediate content page with Continue button")
    return is_content


def _try_switch_to_question_frame(driver: WebDriver) -> bool:
    """Try to switch into an iframe that contains question content."""
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if not iframes:
            return False

        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                if (_has_element(driver, SELECTORS["responses_container"]) or
                    _has_element(driver, SELECTORS["question_fieldset"]) or
                    _has_element(driver, "input[type='radio']") or
                    _has_element(driver, "input[type='checkbox']") or
                    _has_element(driver, SELECTORS["text_input"])):
                    logger.info("Switched to iframe containing question content")
                    return True

                # Check nested iframes
                nested = driver.find_elements(By.TAG_NAME, "iframe")
                for nested_frame in nested:
                    try:
                        driver.switch_to.frame(nested_frame)
                        if (_has_element(driver, SELECTORS["responses_container"]) or
                            _has_element(driver, "input[type='radio']")):
                            logger.info("Switched to nested iframe")
                            return True
                        driver.switch_to.parent_frame()
                    except WebDriverException:
                        driver.switch_to.parent_frame()

                driver.switch_to.default_content()
            except WebDriverException:
                driver.switch_to.default_content()

    except WebDriverException as e:
        logger.debug(f"iframe check failed: {e}")
        driver.switch_to.default_content()

    return False


def _debug_page_elements(driver: WebDriver) -> None:
    """Log what elements exist on the page for debugging."""
    try:
        info = driver.execute_script("""
            var info = {};
            info.url = window.location.href;
            info.iframes = document.querySelectorAll('iframe').length;
            info.radios = document.querySelectorAll('input[type="radio"]').length;
            info.checkboxes = document.querySelectorAll('input[type="checkbox"]').length;
            info.textInputs = document.querySelectorAll('input[type="text"]').length;
            info.buttons = document.querySelectorAll('button').length;
            info.responsesContainer = document.querySelectorAll('.responses-container').length;
            info.choiceRow = document.querySelectorAll('.choice-row').length;
            info.prompt = document.querySelectorAll('.prompt').length;
            info.title = document.title;
            return JSON.stringify(info);
        """)
        logger.info(f"Page debug: {info}")
    except WebDriverException as e:
        logger.debug(f"Debug script failed: {e}")


# ── Text Extraction ───────────────────────────────────────────────

def _extract_question_text(driver: WebDriver) -> str:
    """Extract the question text from the page."""
    try:
        prompts = browser.find_elements_safe(driver, SELECTORS["question_prompt"])
        if prompts:
            text = prompts[0].text.strip()
            if text:
                return text

        # Fallback: grab <p> tags above .responses-container
        body_text = driver.execute_script("""
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
        """)
        if body_text:
            return body_text.strip()

        # Broader fallback: find question text near radio/checkbox inputs
        fallback_text = driver.execute_script("""
        var radios = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
        if (radios.length === 0) return '';
        var container = radios[0].closest('form') || radios[0].closest('[class*="question"]')
                        || radios[0].closest('fieldset') || radios[0].parentElement.parentElement.parentElement;
        if (!container) return '';
        var selectors = ['.question-text', '.question-stem', 'legend', '.stem',
                         '[class*="question-prompt"]', '[class*="stem"]',
                         '.question_text', 'h3', 'h4'];
        for (var i = 0; i < selectors.length; i++) {
            var el = document.querySelector(selectors[i]);
            if (el) {
                var t = el.textContent.trim();
                if (t && t.length > 10) return t;
            }
        }
        return '';
        """)
        if fallback_text:
            return fallback_text.strip()

        return ""

    except WebDriverException as e:
        logger.warning(f"Error extracting question text: {e}")
        return ""


def _extract_page_context(driver: WebDriver) -> str:
    """Extract reading/textbook context visible on the page."""
    context_parts: list[str] = []

    try:
        highlighted = driver.execute_script("""
        var texts = [];
        var marks = document.querySelectorAll('mark, .highlight, [class*="highlight"], .marked-text');
        marks.forEach(function(el) {
            var t = el.textContent.trim();
            if (t && t.length > 10) texts.push(t);
        });
        var readingPane = document.querySelector('.reading-pane, .reader-content, [class*="reader"], [class*="reading-content"]');
        if (readingPane) {
            var pTags = readingPane.querySelectorAll('p');
            pTags.forEach(function(p) {
                var t = p.textContent.trim();
                if (t && t.length > 20) texts.push(t);
            });
        }
        return texts;
        """)
        if highlighted:
            context_parts.extend(highlighted)

        dlc_text = driver.execute_script("""
        var texts = [];
        var viewContainer = document.querySelector('.view-container');
        if (viewContainer) {
            var dlcContent = viewContainer.querySelector('.dlc_question');
            if (dlcContent) {
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
        """)
        if dlc_text:
            context_parts.extend(dlc_text)

    except WebDriverException as e:
        logger.warning(f"Error extracting page context: {e}")

    # Deduplicate and limit length
    seen: set[str] = set()
    unique_parts: list[str] = []
    for part in context_parts:
        if part not in seen:
            seen.add(part)
            unique_parts.append(part)

    context = "\n".join(unique_parts)
    if len(context) > 2000:
        context = context[:2000] + "..."

    if context:
        logger.info(f"Extracted {len(context)} chars of page context")
    return context


# ── Choice Extraction ─────────────────────────────────────────────

def _extract_choices_from_rows(choice_rows, input_elements) -> list[dict]:
    """Extract choices from .choice-row elements."""
    choices = []
    labels = "ABCDEFGHIJ"

    for i, row in enumerate(choice_rows):
        label = labels[i] if i < len(labels) else str(i + 1)

        text = ""
        try:
            text_el = row.find_element(By.CSS_SELECTOR, SELECTORS["choice_text"])
            text = text_el.text.strip()
        except (NoSuchElementException, StaleElementReferenceException):
            text = row.text.strip()

        clickable = input_elements[i] if i < len(input_elements) else None
        if not clickable:
            try:
                clickable = row.find_element(
                    By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
            except NoSuchElementException:
                try:
                    clickable = row.find_element(By.CSS_SELECTOR, "label.form-check-label")
                except NoSuchElementException:
                    clickable = row

        choices.append({"label": label, "text": text, "element": clickable})

    return choices


def _extract_choices_generic(driver: WebDriver, input_elements) -> list[dict]:
    """Fallback: extract choices by finding labels associated with inputs."""
    choices = []
    labels = "ABCDEFGHIJ"

    for i, inp in enumerate(input_elements):
        label = labels[i] if i < len(labels) else str(i + 1)
        text = ""

        try:
            inp_id = inp.get_attribute("id")
            if inp_id:
                label_els = browser.find_elements_safe(driver, f"label[for='{inp_id}']")
                if label_els:
                    text = label_els[0].text.strip()

            if not text:
                text = driver.execute_script("""
                    var el = arguments[0];
                    var parent = el.closest('label') || el.parentElement;
                    if (!parent) return '';
                    var clone = parent.cloneNode(true);
                    var hidden = clone.querySelectorAll('[style*="display:none"], [style*="display: none"], ._visuallyHidden');
                    hidden.forEach(function(h) { h.remove(); });
                    return clone.textContent.trim();
                """, inp)

            if not text:
                text = driver.execute_script("""
                    var el = arguments[0];
                    var sibling = el.nextElementSibling;
                    while (sibling) {
                        var t = sibling.textContent.trim();
                        if (t) return t;
                        sibling = sibling.nextElementSibling;
                    }
                    return '';
                """, inp)

        except (WebDriverException, StaleElementReferenceException) as e:
            logger.debug(f"Error extracting choice text: {e}")

        choices.append({"label": label, "text": text, "element": inp})

    return choices


def _extract_dropdown_options(dropdowns) -> list[dict]:
    """Extract options from dropdown select elements."""
    choices = []
    for dropdown in dropdowns:
        try:
            options = dropdown.find_elements(By.TAG_NAME, "option")
            opt_texts = [o.text.strip() for o in options if o.text.strip()]
            choices.append({"options": opt_texts, "element": dropdown})
        except (StaleElementReferenceException, NoSuchElementException):
            choices.append({"options": [], "element": dropdown})
    return choices


def _extract_sortable_items(driver: WebDriver) -> list[str]:
    """Extract item texts from a sortable/ordering question."""
    items = []
    elements = browser.find_elements_safe(driver, SELECTORS["sortable_item"])
    for el in elements:
        try:
            text_el = el.find_element(By.CSS_SELECTOR, SELECTORS["sortable_item_text"])
            text = text_el.text.strip()
        except (NoSuchElementException, StaleElementReferenceException):
            text = el.text.strip()
        if text:
            items.append(text)
    return items


def _extract_matching_data(driver: WebDriver) -> dict:
    """Extract matching question data: labels, drop zones, and choices."""
    labels = []
    choices = []

    label_elements = browser.find_elements_safe(driver, SELECTORS["matching_label"])
    for el in label_elements:
        try:
            text = el.text.strip()
            if text:
                labels.append(text)
        except StaleElementReferenceException:
            pass

    drop_zone_elements = browser.find_elements_safe(driver, SELECTORS["matching_drop_zone"])

    choice_elements = browser.find_elements_safe(driver, SELECTORS["matching_choice"])
    for el in choice_elements:
        try:
            text_el = el.find_element(By.CSS_SELECTOR, SELECTORS["matching_choice_text"])
            choices.append(text_el.text.strip())
        except (NoSuchElementException, StaleElementReferenceException):
            choices.append(el.text.strip())

    logger.info(f"Matching: {len(labels)} labels, {len(choices)} choices, "
                f"{len(drop_zone_elements)} drop zones")

    return {
        "sources": labels,
        "targets": choices,
        "source_elements": drop_zone_elements,
        "target_elements": choice_elements,
    }
