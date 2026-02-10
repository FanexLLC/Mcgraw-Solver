import time
import random
from selenium.webdriver.common.action_chains import ActionChains
import config


def random_delay(min_s=None, max_s=None):
    """Sleep for a random duration between min and max seconds."""
    if min_s is None:
        min_s = config.MIN_DELAY
    if max_s is None:
        max_s = config.MAX_DELAY
    delay = random.uniform(min_s, max_s)
    time.sleep(delay)
    return delay


def reading_delay(text):
    """Simulate reading time based on word count."""
    words = len(text.split())
    wpm = config.READING_WPM + random.randint(-config.READING_WPM_VARIANCE, config.READING_WPM_VARIANCE)
    wpm = max(wpm, 100)  # floor at 100 WPM
    delay = (words / wpm) * 60
    # Add slight random variance
    delay *= random.uniform(0.8, 1.2)
    # Minimum 1 second, maximum 15 seconds
    delay = max(1.0, min(delay, 15.0))
    time.sleep(delay)
    return delay


def human_type(element, text, driver):
    """Type text into an input element, with JS fallback for Angular apps."""
    actions = ActionChains(driver)
    actions.click(element)
    actions.perform()
    time.sleep(random.uniform(0.2, 0.5))

    # Try send_keys first
    try:
        element.clear()
        time.sleep(random.uniform(0.1, 0.3))

        for i, char in enumerate(text):
            element.send_keys(char)
            time.sleep(random.uniform(config.TYPE_MIN_DELAY, config.TYPE_MAX_DELAY))
            if i > 0 and i % random.randint(5, 10) == 0:
                time.sleep(random.uniform(0.3, 0.6))
    except Exception:
        pass

    # Always set value via JS and fire all relevant events for Angular
    driver.execute_script("""
        var el = arguments[0];
        var text = arguments[1];

        // Set value using native setter to bypass Angular's wrapper
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(el, text);

        // Fire events Angular listens for
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
    """, element, text)


def human_click(element, driver):
    """Click an element with slight random offset and hover delay."""
    actions = ActionChains(driver)
    # Move to element with random offset from center
    x_offset = random.randint(-5, 5)
    y_offset = random.randint(-5, 5)
    actions.move_to_element_with_offset(element, x_offset, y_offset)
    actions.perform()
    # Pause between hover and click
    time.sleep(random.uniform(config.CLICK_HOVER_MIN, config.CLICK_HOVER_MAX))
    # Click
    actions = ActionChains(driver)
    actions.click()
    actions.perform()

    # Fire change event for Angular — needed for radio buttons, checkboxes, etc.
    try:
        driver.execute_script("""
            var el = arguments[0];
            var input = el.querySelector('input[type="radio"], input[type="checkbox"]');
            if (!input && el.tagName === 'LABEL') {
                input = el.querySelector('input');
            }
            if (!input && (el.tagName === 'INPUT')) {
                input = el;
            }
            if (input && !input.checked) {
                input.checked = true;
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
        """, element)
    except Exception:
        pass


def random_scroll(driver):
    """30% chance to scroll slightly before interacting."""
    if random.random() < 0.3:
        scroll_amount = random.randint(-150, 150)
        if scroll_amount == 0:
            scroll_amount = 50
        driver.execute_script(f"window.scrollBy(0, {scroll_amount})")
        time.sleep(random.uniform(0.3, 0.8))


def should_miss():
    """Returns True if we should intentionally pick a wrong answer."""
    return random.random() > config.TARGET_ACCURACY
