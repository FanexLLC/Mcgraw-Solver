import time
import logging
import sys
import config
import browser
import parser
import solver
import human
from gui import SolverGUI

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Global state
driver = None
gui = None
pause_flag = False
stop_flag = False


def apply_settings(settings):
    """Apply GUI settings to config."""
    config.MIN_DELAY = settings["min_delay"]
    config.MAX_DELAY = settings["max_delay"]
    config.TARGET_ACCURACY = settings["accuracy"]
    config.GPT_MODEL = settings["model"]
    config.CHROME_PROFILE = settings.get("chrome_profile", "Default")


def on_start(settings):
    """Called when user clicks Start."""
    global driver, stop_flag, pause_flag
    stop_flag = False
    pause_flag = False

    apply_settings(settings)

    # Connect to proxy server
    try:
        solver.init_client(settings["access_key"])
        gui.log("Connected to server.")
    except Exception as e:
        gui.log(f"ERROR: {e}")
        gui.root.after(0, gui._on_stop)
        return

    # Connect to existing browser
    try:
        gui.log("Connecting to Chrome (make sure you clicked Launch Chrome first)...")
        driver = browser.connect_to_browser()
        gui.log("Connected to Chrome!")
        gui.log("Make sure you're on a SmartBook question page.")
        gui.log("The solver will start answering automatically.")
    except Exception as e:
        gui.log(f"ERROR launching browser: {e}")
        gui.root.after(0, gui._on_stop)
        return

    # Wait for user to navigate to SmartBook
    gui.log("Waiting for SmartBook question page...")
    solve_loop()


def solve_loop():
    """Main solve loop."""
    global stop_flag, pause_flag, driver

    question_num = 0
    correct_num = 0
    consecutive_unknown = 0

    while not stop_flag:
        # Check pause
        while pause_flag and not stop_flag:
            time.sleep(0.5)

        if stop_flag:
            break

        try:
            # Wait for page to be ready
            if not browser.is_page_ready(driver):
                time.sleep(1)
                continue

            # Detect page type
            page_type = parser.detect_page_type(driver)
            logger.info(f"Page type: {page_type}")

            if page_type == "loading":
                time.sleep(1)
                consecutive_unknown = 0
                continue

            elif page_type == "complete":
                gui.log(f"Assignment complete! {correct_num}/{question_num} answered.")
                gui.update_status(question_num, correct_num, question_num)
                break

            elif page_type == "recharge":
                gui.log("Concept resource page detected — opening and closing reading...")
                parser.handle_recharge_page(driver)
                human.random_delay(config.MIN_DELAY, config.MAX_DELAY)
                consecutive_unknown = 0
                continue

            elif page_type == "reading":
                gui.log("Reading screen detected, clicking Next...")
                human.random_delay(1.0, 3.0)
                parser.click_next_button(driver)
                human.random_delay(config.MIN_DELAY, config.MAX_DELAY)
                consecutive_unknown = 0
                continue

            elif page_type == "unknown":
                consecutive_unknown += 1
                if consecutive_unknown > 10:
                    gui.log("No SmartBook content detected. Waiting...")
                    consecutive_unknown = 0
                time.sleep(2)
                continue

            elif page_type == "question":
                consecutive_unknown = 0
                question_num += 1

                # Parse the question
                question_data = parser.parse_question(driver)
                if question_data["type"] == "unknown":
                    gui.log(f"Q{question_num}: Unknown question type. Skipping...")
                    human.random_delay(2.0, 4.0)
                    parser.click_next_button(driver)
                    human.random_delay(config.MIN_DELAY, config.MAX_DELAY)
                    continue

                q_preview = question_data["question"][:60]
                gui.log(f"Q{question_num}: {q_preview}...")

                # Simulate reading the question
                human.reading_delay(question_data["question"])

                # Occasional scroll
                human.random_scroll(driver)

                # Get answer from GPT
                try:
                    action = solver.get_answer(question_data)
                except Exception as e:
                    gui.log(f"  Server error: {e}. Retrying...")
                    time.sleep(3)
                    try:
                        action = solver.get_answer(question_data)
                    except Exception as e2:
                        gui.log(f"  Server error again: {e2}. Skipping question.")
                        parser.click_next_button(driver)
                        human.random_delay(config.MIN_DELAY, config.MAX_DELAY)
                        continue

                # Maybe inject intentional error
                action, was_miss = solver.maybe_inject_error(action, question_data)
                miss_tag = " (intentional miss)" if was_miss else ""

                # Execute the answer
                try:
                    _execute_action(action, driver)
                    if not was_miss:
                        correct_num += 1
                    gui.log(f"  -> {action['answer_text']}{miss_tag}")
                except Exception as e:
                    gui.log(f"  Error executing answer: {e}")

                gui.update_status(question_num, correct_num)

                # Pause before submitting
                human.random_delay(0.5, 1.5)

                # Submit answer via confidence button
                parser.submit_with_confidence(driver)

                # Click "Next Question" button if it appears
                human.random_delay(1.0, 2.0)
                parser.click_next_question(driver)

                # Wait between questions
                delay = human.random_delay(config.MIN_DELAY, config.MAX_DELAY)
                gui.log(f"  Waiting {delay:.1f}s...")

        except Exception as e:
            logger.exception("Error in solve loop")
            gui.log(f"Error: {e}")
            time.sleep(3)

    # Cleanup - don't close Chrome, just disconnect
    gui.log("Solve loop ended.")
    driver = None
    gui.root.after(0, gui._on_stop)


def _click_choice(drv, element):
    """Click a multiple choice / true-false option using JS to ensure Angular registers it."""
    human.random_delay(0.2, 0.5)
    drv.execute_script("""
        var el = arguments[0];

        // Find the radio/checkbox input — could be the element itself or inside it
        var input = el;
        if (el.tagName !== 'INPUT') {
            input = el.querySelector('input[type="radio"], input[type="checkbox"]');
        }

        // Find the label associated with this input (Angular often binds click on label)
        var label = null;
        if (input && input.id) {
            label = document.querySelector('label[for="' + input.id + '"]');
        }
        if (!label && input) {
            label = input.closest('label');
        }

        // Find the parent .choice or .choice-row div where Angular may bind handlers
        var choice = el.closest('.choice') || el.closest('.choice-row');

        // The click target: prefer label, then choice container, then the input
        var clickTarget = label || choice || input || el;

        // Dispatch the full mouse event sequence that Zone.js intercepts
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

        // Fire on the click target (label or choice container)
        fireMouseSequence(clickTarget);

        // If the input still isn't checked, force it and fire change
        if (input && !input.checked) {
            input.checked = true;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // Nudge Angular's change detection if available
        try {
            var ngZone = window.getAllAngularTestabilities && window.getAllAngularTestabilities();
            if (ngZone && ngZone.length > 0) {
                ngZone[0]._ngZone.run(function(){});
            }
        } catch(e) {}
    """, element)


def _execute_action(action, drv):
    """Execute an answer action on the page."""
    action_type = action["type"]
    targets = action.get("targets", [])
    values = action.get("values", [])

    if action_type == "click" and targets:
        _click_choice(drv, targets[0])

    elif action_type == "multi_click":
        for target in targets:
            _click_choice(drv, target)
            human.random_delay(0.3, 0.8)

    elif action_type == "type" and targets and values:
        browser.safe_click(drv, targets[0])
        human.random_delay(0.2, 0.5)
        browser.safe_type(drv, targets[0], values[0])

    elif action_type == "multi_type" and targets and values:
        for i, (target, value) in enumerate(zip(targets, values)):
            # Click the specific input to focus it
            drv.execute_script("arguments[0].focus(); arguments[0].click();", target)
            human.random_delay(0.3, 0.6)

            # Clear and set value via JS with native setter for Angular
            drv.execute_script("""
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

            if i < len(targets) - 1:
                human.random_delay(0.5, 1.2)

    elif action_type == "dropdown" and targets and values:
        from selenium.webdriver.support.ui import Select
        for i, (target, value) in enumerate(zip(targets, values)):
            try:
                select = Select(target)
                select.select_by_visible_text(value)
            except Exception:
                # Try partial match
                for option in target.find_elements_by_tag_name("option"):
                    if value.lower() in option.text.lower():
                        option.click()
                        break
            if i < len(targets) - 1:
                human.random_delay(0.3, 0.8)


def on_pause(is_paused):
    """Called when user clicks Pause/Resume."""
    global pause_flag
    pause_flag = is_paused


def on_stop():
    """Called when user clicks Stop."""
    global stop_flag, driver
    stop_flag = True
    driver = None  # disconnect without closing Chrome


if __name__ == "__main__":
    gui = SolverGUI(on_start=on_start, on_pause=on_pause, on_stop=on_stop)
    gui.log("Welcome to SmartBook Solver!")
    gui.log("1. Click 'Launch Chrome' to open Chrome")
    gui.log("2. Navigate to your SmartBook assignment")
    gui.log("3. Enter your access key and click Start")
    gui.run()
