from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
import config
import human


def connect_to_browser():
    """Connect to an already-running Chrome instance on debug port 9222."""
    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    driver = webdriver.Chrome(options=options)
    return driver


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
