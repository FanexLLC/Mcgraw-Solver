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
from selenium.webdriver.chrome.service import Service as ChromeService
import selenium.webdriver.chrome.webdriver  # noqa: F401 - required for PyInstaller
import config
import human

logger = logging.getLogger(__name__)


def launch_chrome():
    """Launch Chrome with remote debugging enabled. Works on Windows, macOS, and Linux."""
    system = platform.system()

    import os

    chrome_path = _find_chrome_binary()

    if system == "Darwin":
        if chrome_path is None:
            chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        kill_cmd = ["pkill", "-f", "Google Chrome"]
        data_dir = "/tmp/chrome-debug"
    elif system == "Windows":
        if chrome_path is None:
            raise FileNotFoundError(
                "Google Chrome not found. Please install Chrome and try again.\n"
                "Download from: https://www.google.com/chrome"
            )
        kill_cmd = ["taskkill", "/F", "/IM", "chrome.exe"]
        # Kill Edge so it doesn't hold port 9222 — Edge auto-restarts,
        # so also disable its startup boost via taskkill on all edge processes
        for edge_proc in ["msedge.exe", "msedgewebview2.exe"]:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", edge_proc],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
        data_dir = os.path.expandvars(r"%TEMP%\chrome-debug")
    else:
        if chrome_path is None:
            chrome_path = "google-chrome"
        kill_cmd = ["pkill", "-f", "chrome"]
        data_dir = "/tmp/chrome-debug"

    # Kill existing Chrome
    try:
        subprocess.run(kill_cmd, capture_output=True, timeout=5)
    except Exception:
        pass

    # Wait for port 9222 to be free (Edge can take a moment to fully die)
    import socket
    for _ in range(10):
        time.sleep(1)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sock.connect_ex(("127.0.0.1", 9222)) != 0:
                break  # Port is free
        finally:
            sock.close()
    else:
        logger.warning("Port 9222 still in use after waiting — another browser may be holding it")

    # Launch Chrome with debug port
    subprocess.Popen(
        [
            chrome_path,
            f"--remote-debugging-port=9222",
            f"--user-data-dir={data_dir}",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for Chrome to actually start listening on 9222
    for _ in range(10):
        time.sleep(1)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sock.connect_ex(("127.0.0.1", 9222)) == 0:
                break  # Chrome is ready
        finally:
            sock.close()

    logger.info("Chrome launched with debug port 9222")


def _find_chrome_binary():
    """Find the Google Chrome binary on the system."""
    import os
    system = platform.system()

    if system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        ]
    elif system == "Darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        candidates = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"]

    return next((p for p in candidates if os.path.exists(p)), None)


def _verify_debug_port_is_chrome():
    """Check that port 9222 is served by Chrome, not Edge or another browser."""
    import json
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5)
        info = json.loads(resp.read())
        browser = info.get("Browser", "")
        user_agent = info.get("User-Agent", "")
        logger.info(f"Debug port browser: {browser}")
        if "Edg/" in browser or "Edg/" in user_agent:
            raise ConnectionError(
                "Microsoft Edge is running on debug port 9222 instead of Chrome.\n"
                "Please close Edge completely, then click 'Launch Chrome' again."
            )
        return info
    except (ConnectionError, json.JSONDecodeError):
        raise
    except Exception:
        # Can't verify — proceed anyway
        return None


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

    # Verify it's actually Chrome on the debug port, not Edge
    _verify_debug_port_is_chrome()

    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    # Explicitly point to Chrome so Selenium doesn't pick up Edge
    chrome_binary = _find_chrome_binary()
    if chrome_binary:
        options.binary_location = chrome_binary

    # Defensive flags that help prevent ChromeDriver crashes on some Windows systems
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")

    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        error_msg = str(e).lower()
        if "edg" in error_msg or "edge" in error_msg:
            raise ConnectionError(
                "Microsoft Edge is interfering with ChromeDriver.\n"
                "Please close Edge completely, then click 'Launch Chrome' again.\n"
                "If the problem persists, delete the ChromeDriver cache:\n"
                '   rmdir /s /q "%USERPROFILE%\\.cache\\selenium"'
            ) from e
        elif "chromedriver" in error_msg or "session not created" in error_msg:
            raise ConnectionError(
                "ChromeDriver failed to start. This is usually a version mismatch.\n"
                "Try: 1) Update Chrome  2) Delete ChromeDriver cache:\n"
                '   rmdir /s /q "%USERPROFILE%\\.cache\\selenium"\n'
                "Then re-run the app."
            ) from e
        raise

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
