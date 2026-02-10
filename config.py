import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
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
TARGET_ACCURACY = 0.90

# Browser - Use your real Chrome profile so you stay logged in
CHROME_USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data")
CHROME_PROFILE = "Default"  # Change to "Profile 1", "Profile 2", etc. if needed
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080

# Speed presets (min_delay, max_delay)
SPEED_PRESETS = {
    "Slow": (4.0, 8.0),
    "Normal": (2.0, 5.0),
    "Fast": (1.0, 3.0),
}
