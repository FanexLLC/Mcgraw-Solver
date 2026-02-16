import os
import sys
import platform
from dotenv import load_dotenv


# App version - bump this before each new release
APP_VERSION = "1.0.6"

# GitHub repo for update checks
GITHUB_REPO = "FanexLLC/Mcgraw-Solver"


def _get_app_dir():
    """Get the directory where the app lives (works for both script and PyInstaller bundle)."""
    if getattr(sys, "frozen", False):
        if platform.system() == "Darwin":
            # macOS: use ~/Library/Application Support so it works from DMG/read-only volumes
            app_support = os.path.join(os.path.expanduser("~"), "Library",
                                       "Application Support", "SmartBook Solver")
            os.makedirs(app_support, exist_ok=True)
            return app_support
        # Windows: use the directory containing the .exe
        return os.path.dirname(sys.executable)
    return os.path.dirname(__file__)


# Load .env — check app dir first, fall back to bundled .env
_app_dir = _get_app_dir()
_env_path = os.path.join(_app_dir, ".env")
if not os.path.exists(_env_path) and getattr(sys, "frozen", False):
    # First launch: seed from the bundled .env next to the executable
    _bundled = os.path.join(os.path.dirname(sys.executable), ".env")
    if os.path.exists(_bundled):
        import shutil
        shutil.copy2(_bundled, _env_path)
load_dotenv(_env_path)

# Proxy server
SERVER_URL = os.getenv("SERVER_URL", "https://mcgraw-solver-production.up.railway.app")
ACCESS_KEY = os.getenv("ACCESS_KEY", "")

# AI model (sent to server — supports both OpenAI and Anthropic models)
GPT_MODEL = "claude-sonnet-4-5-20250929"
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

# ── AI Model Tiers ────────────────────────────────────────────────

# Model display names for the UI
MODEL_DISPLAY_NAMES = {
    "gpt-4o-mini": "GPT-4o Mini (Fast)",
    "gpt-4o": "GPT-4o (Balanced)",
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5 (Best)",
}

# Plan-based model access control
PLAN_MODEL_ACCESS = {
    "weekly": ["gpt-4o-mini"],
    "monthly": ["gpt-4o-mini", "gpt-4o"],
    "semester": ["gpt-4o-mini", "gpt-4o", "claude-sonnet-4-5-20250929"],
}


def get_default_model_for_plan(plan: str) -> str:
    """Get the default AI model for a given plan."""
    plan_defaults = {
        "weekly": "gpt-4o-mini",
        "monthly": "gpt-4o",
        "semester": "claude-sonnet-4-5-20250929",
    }
    return plan_defaults.get(plan, "gpt-4o-mini")


def get_available_models_for_plan(plan: str) -> list[str]:
    """Get list of models available for a given plan."""
    return PLAN_MODEL_ACCESS.get(plan, ["gpt-4o-mini"])


def is_model_allowed_for_plan(model: str, plan: str) -> bool:
    """Check if a model is allowed for a given plan."""
    return model in PLAN_MODEL_ACCESS.get(plan, [])
