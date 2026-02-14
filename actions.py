"""Action executors — translate Action objects into Selenium interactions."""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
)

import browser
import human
from models import Action

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement

logger = logging.getLogger(__name__)


def execute(action: Action, driver: WebDriver) -> None:
    """Route an action to the appropriate handler."""
    handlers = {
        "click": _execute_click,
        "multi_click": _execute_multi_click,
        "type": _execute_type,
        "multi_type": _execute_multi_type,
        "dropdown": _execute_dropdown,
        "ordering": _execute_ordering,
        "matching": _execute_matching,
    }
    handler = handlers.get(action.type)
    if handler:
        handler(action, driver)
    else:
        logger.warning(f"Unknown action type: {action.type}")


# ── Single / Multi Click ──────────────────────────────────────────────

def _click_choice(driver: WebDriver, element: WebElement) -> None:
    """Click a MC / true-false option using JS to trigger Angular change detection."""
    human.random_delay(0.2, 0.5)
    driver.execute_script("""
        var el = arguments[0];
        var input = el;
        if (el.tagName !== 'INPUT') {
            input = el.querySelector('input[type="radio"], input[type="checkbox"]');
        }
        var label = null;
        if (input && input.id) {
            label = document.querySelector('label[for="' + input.id + '"]');
        }
        if (!label && input) {
            label = input.closest('label');
        }
        var choice = el.closest('.choice') || el.closest('.choice-row');
        var clickTarget = label || choice || input || el;

        function fireMouseSequence(target) {
            var rect = target.getBoundingClientRect();
            var cx = rect.left + rect.width / 2;
            var cy = rect.top + rect.height / 2;
            var opts = {bubbles: true, cancelable: true, view: window,
                        clientX: cx, clientY: cy, button: 0};
            target.dispatchEvent(new PointerEvent('pointerdown', opts));
            target.dispatchEvent(new MouseEvent('mousedown', opts));
            target.dispatchEvent(new PointerEvent('pointerup', opts));
            target.dispatchEvent(new MouseEvent('mouseup', opts));
            target.dispatchEvent(new MouseEvent('click', opts));
        }
        fireMouseSequence(clickTarget);

        if (input && !input.checked) {
            input.checked = true;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }
        try {
            var ngZone = window.getAllAngularTestabilities && window.getAllAngularTestabilities();
            if (ngZone && ngZone.length > 0) {
                ngZone[0]._ngZone.run(function(){});
            }
        } catch(e) {}
    """, element)


def _execute_click(action: Action, driver: WebDriver) -> None:
    if action.targets:
        _click_choice(driver, action.targets[0])


def _execute_multi_click(action: Action, driver: WebDriver) -> None:
    for target in action.targets:
        _click_choice(driver, target)
        human.random_delay(0.3, 0.8)


# ── Type / Multi-Type ─────────────────────────────────────────────────

def _execute_type(action: Action, driver: WebDriver) -> None:
    if action.targets and action.values:
        browser.safe_click(driver, action.targets[0])
        human.random_delay(0.2, 0.5)
        browser.safe_type(driver, action.targets[0], action.values[0])


def _execute_multi_type(action: Action, driver: WebDriver) -> None:
    for i, (target, value) in enumerate(zip(action.targets, action.values)):
        driver.execute_script("arguments[0].focus(); arguments[0].click();", target)
        human.random_delay(0.3, 0.6)

        driver.execute_script("""
            var el = arguments[0];
            var text = arguments[1];
            el.value = '';
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(el, text);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        """, target, value)

        if i < len(action.targets) - 1:
            human.random_delay(0.5, 1.2)


# ── Dropdown ──────────────────────────────────────────────────────────

def _execute_dropdown(action: Action, driver: WebDriver) -> None:
    for i, (target, value) in enumerate(zip(action.targets, action.values)):
        try:
            select = Select(target)
            select.select_by_visible_text(value)
        except (NoSuchElementException, StaleElementReferenceException):
            # Try partial match
            try:
                for option in target.find_elements(By.TAG_NAME, "option"):
                    if value.lower() in option.text.lower():
                        option.click()
                        break
            except StaleElementReferenceException:
                logger.warning(f"Dropdown element went stale for value '{value}'")
        if i < len(action.targets) - 1:
            human.random_delay(0.3, 0.8)


# ── Ordering ──────────────────────────────────────────────────────────

def _fuzzy_match(gpt_text: str, original_texts: list[str]) -> int:
    """Return index of best-matching original item, or -1."""
    gpt_lower = gpt_text.lower().strip()
    best_idx = -1
    best_ratio = 0.0

    for i, orig in enumerate(original_texts):
        orig_lower = orig.lower().strip()
        if gpt_lower == orig_lower:
            return i
        if gpt_lower in orig_lower or orig_lower in gpt_lower:
            ratio = min(len(gpt_lower), len(orig_lower)) / max(len(gpt_lower), len(orig_lower))
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i

    return best_idx if best_ratio > 0.5 else -1


def _execute_ordering(action: Action, driver: WebDriver) -> None:
    """Reorder sortable items using keyboard controls for react-beautiful-dnd."""
    ordered_items = action.ordered_items
    original_items = action.original_items

    if not ordered_items or not action.item_elements:
        logger.warning("Ordering: no items or elements to reorder")
        return

    # desired_order[i] = original index of item that should be at position i
    desired_order: list[int] = []
    for item_text in ordered_items:
        idx = _fuzzy_match(item_text, original_items)
        if idx >= 0 and idx not in desired_order:
            desired_order.append(idx)

    if len(desired_order) != len(original_items):
        logger.warning(f"Ordering: matched {len(desired_order)}/{len(original_items)} items")
        return

    if desired_order == list(range(len(original_items))):
        logger.info("Ordering: items already in correct order")
        return

    current_positions = list(range(len(original_items)))

    for target_pos in range(len(desired_order)):
        orig_idx = desired_order[target_pos]
        current_pos = current_positions[orig_idx]

        if current_pos == target_pos:
            continue

        moves = current_pos - target_pos
        if moves == 0:
            continue

        fresh_items = browser.find_elements_safe(
            driver, ".sortable-component .responses-container .choice-item")
        if current_pos >= len(fresh_items):
            logger.warning(f"Ordering: position {current_pos} out of range")
            continue

        item_el = fresh_items[current_pos]

        driver.execute_script("arguments[0].focus();", item_el)
        human.random_delay(0.2, 0.4)

        item_el.send_keys(Keys.SPACE)
        human.random_delay(0.3, 0.6)

        arrow_key = Keys.ARROW_UP if moves > 0 else Keys.ARROW_DOWN
        for _ in range(abs(moves)):
            item_el.send_keys(arrow_key)
            human.random_delay(0.15, 0.35)

        item_el.send_keys(Keys.SPACE)
        human.random_delay(0.3, 0.7)

        # Update position tracking
        if moves > 0:
            for idx in range(len(current_positions)):
                if target_pos <= current_positions[idx] < current_pos:
                    current_positions[idx] += 1
        else:
            for idx in range(len(current_positions)):
                if current_pos < current_positions[idx] <= target_pos:
                    current_positions[idx] -= 1
        current_positions[orig_idx] = target_pos

        logger.info(f"Ordering: moved item from position {current_pos} to {target_pos}")

    logger.info(f"Ordering: reordered {len(desired_order)} items")


# ── Matching ──────────────────────────────────────────────────────────

def _execute_matching(action: Action, driver: WebDriver) -> None:
    """Drag choice items to drop zones using Selenium ActionChains."""
    matches = action.matches
    drop_zones = action.source_elements
    labels = action.sources

    if not matches or not drop_zones:
        logger.warning("Matching: no matches or drop zones")
        return

    for match in matches:
        label_text = match["source"].lower().strip()
        choice_text = match["target"].lower().strip()

        # Find drop zone
        drop_idx = None
        for i, label in enumerate(labels):
            if label_text in label.lower() or label.lower() in label_text:
                drop_idx = i
                break

        if drop_idx is None or drop_idx >= len(drop_zones):
            logger.warning(f"Matching: no drop zone for '{match['source']}'")
            continue

        # Re-query choices (DOM changes after each drag)
        fresh_choices = browser.find_elements_safe(
            driver, ".matching-component .choices-container .choice-item-wrapper")

        choice_el = None
        for el in fresh_choices:
            try:
                text = el.find_element(By.CSS_SELECTOR, ".content p").text.strip().lower()
                if choice_text in text or text in choice_text:
                    choice_el = el
                    break
            except (StaleElementReferenceException, NoSuchElementException):
                continue

        if not choice_el:
            logger.warning(f"Matching: no choice element for '{match['target']}'")
            continue

        try:
            chain = ActionChains(driver)
            chain.move_to_element(choice_el)
            chain.pause(0.2)
            chain.click_and_hold(choice_el)
            chain.pause(0.4)
            chain.move_by_offset(0, -10)
            chain.pause(0.2)
            chain.move_to_element(drop_zones[drop_idx])
            chain.pause(0.3)
            chain.release()
            chain.perform()

            human.random_delay(0.5, 1.2)
            logger.info(f"Matching: dragged '{match['target']}' -> '{match['source']}'")
        except (StaleElementReferenceException, NoSuchElementException) as e:
            logger.warning(f"Matching: drag failed for '{match['source']}': {e}")

    logger.info(f"Matching: completed {len(matches)} matches")
