import os
import sys
import platform
from dotenv import load_dotenv


# App version - bump this before each new release
APP_VERSION = "1.0.0"

# GitHub repo for update checks
GITHUB_REPO = "FanexLLC/Mcgraw-Solver"


def _get_app_dir():
    """Get the directory where the app lives (works for both script and PyInstaller bundle)."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle — use the directory containing the .exe/.app
        return os.path.dirname(sys.executable)
    return os.path.dirname(__file__)


# Load .env from the app directory
load_dotenv(os.path.join(_get_app_dir(), ".env"))

# Proxy server
SERVER_URL = os.getenv("SERVER_URL", "https://mcgraw-solver-production.up.railway.app")
ACCESS_KEY = os.getenv("ACCESS_KEY", "")

# OpenAI model (sent to server so it knows which model to use)
GPT_MODEL = "gpt-4o"
GPT_TEMPERATURE = 0.0

# Timing (seconds) - human-like delays
MIN_DELAY = 2.0
MAX_DELAY = 5.0
READING_WPM = 250
READING_WPM_VARIANCE = 50
TYPE_MIN_DELAY = 0.05
TYPE_MAX_DELAY = 0.15
CLICK_HOVER_MIN = 0.2
CLICK_HOVER_MAX = 0.6

# Accuracy - intentionally miss some questions to look human
TARGET_ACCURACY = 0.95

# Browser - detect OS for correct Chrome path
_system = platform.system()
if _system == "Darwin":
    CHROME_USER_DATA_DIR = os.path.expanduser("~/Library/Application Support/Google/Chrome")
elif _system == "Windows":
    CHROME_USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data")
else:
    CHROME_USER_DATA_DIR = os.path.expanduser("~/.config/google-chrome")

CHROME_PROFILE = "Default"
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080

# Speed presets (min_delay, max_delay)
SPEED_PRESETS = {
    "Slow": (4.0, 8.0),
    "Normal": (2.0, 5.0),
    "Fast": (1.0, 3.0),
}
