import logging
import platform
import subprocess
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
import config
import human

logger = logging.getLogger(__name__)


def launch_chrome():
    """Launch Chrome with remote debugging enabled. Works on Windows, macOS, and Linux."""
    system = platform.system()

    if system == "Darwin":
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        kill_cmd = ["pkill", "-f", "Google Chrome"]
        data_dir = "/tmp/chrome-debug"
    elif system == "Windows":
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        kill_cmd = ["taskkill", "/F", "/IM", "chrome.exe"]
        data_dir = r"C:\temp\chrome-debug"
    else:
        chrome_path = "google-chrome"
        kill_cmd = ["pkill", "-f", "chrome"]
        data_dir = "/tmp/chrome-debug"

    # Kill existing Chrome
    try:
        subprocess.run(kill_cmd, capture_output=True, timeout=5)
    except Exception:
        pass

    time.sleep(2)

    # Launch Chrome with debug port
    subprocess.Popen(
        [chrome_path, f"--remote-debugging-port=9222", f"--user-data-dir={data_dir}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("Chrome launched with debug port 9222")


def connect_to_browser():
    """Connect to an already-running Chrome instance on debug port 9222."""
    import socket

    # Quick check that something is listening on port 9222
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex(("127.0.0.1", 9222))
        if result != 0:
            raise ConnectionError(
                "Chrome is not running on debug port 9222. "
                "Click 'Launch Chrome' first, then try again."
            )
    finally:
        sock.close()

    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    driver = webdriver.Chrome(options=options)

    # Switch to the SmartBook tab if we're on the wrong one
    switch_to_smartbook_tab(driver)
    return driver


def switch_to_smartbook_tab(driver):
    """Find and switch to the tab containing SmartBook content."""
    import logging
    logger = logging.getLogger(__name__)

    handles = driver.window_handles
    logger.info(f"Found {len(handles)} tab(s)")

    for handle in handles:
        driver.switch_to.window(handle)
        try:
            url = driver.current_url
            title = driver.title
            logger.info(f"Tab: {title} | {url}")
            # Look for McGraw-Hill / SmartBook URLs
            if any(kw in url.lower() for kw in ["mcgraw", "smartbook", "connect", "mheducation"]):
                logger.info(f"Switched to SmartBook tab: {title}")
                return
        except Exception:
            continue

    # If no SmartBook tab found, stay on current tab
    logger.warning("No SmartBook tab found — staying on current tab")


def wait_for_element(driver, selector, by=By.CSS_SELECTOR, timeout=15):
    """Wait for an element to be present and return it, or None on timeout."""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        return element
    except TimeoutException:
        return None


def wait_for_clickable(driver, selector, by=By.CSS_SELECTOR, timeout=15):
    """Wait for an element to be clickable and return it, or None on timeout."""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, selector))
        )
        return element
    except TimeoutException:
        return None


def is_page_ready(driver):
    """Check if the page has finished loading."""
    try:
        ready_state = driver.execute_script("return document.readyState")
        return ready_state == "complete"
    except Exception:
        return False


def safe_click(driver, element):
    """Click an element with human-like behavior."""
    human.human_click(element, driver)


def safe_type(driver, element, text):
    """Type into an element with human-like behavior."""
    human.human_type(element, text, driver)


def find_elements_safe(driver, selector, by=By.CSS_SELECTOR):
    """Find elements without throwing if none found."""
    try:
        return driver.find_elements(by, selector)
    except Exception:
        return []
