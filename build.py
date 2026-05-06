"""Build standalone .exe with PyInstaller (all dependencies bundled)."""
import subprocess
import sys
import os

os.chdir(os.path.dirname(__file__))

# All local modules that PyInstaller needs to find
hidden_imports = [
    "selenium",
    "selenium.webdriver",
    "selenium.webdriver.chrome",
    "selenium.webdriver.chrome.service",
    "selenium.webdriver.chrome.options",
    "selenium.webdriver.chrome.webdriver",
    "selenium.webdriver.common.by",
    "selenium.webdriver.common.keys",
    "selenium.webdriver.common.action_chains",
    "selenium.webdriver.support",
    "selenium.webdriver.support.ui",
    "selenium.webdriver.support.expected_conditions",
    "selenium.common.exceptions",
    "requests",
    "dotenv",
    "urllib3",
    "certifi",
    "charset_normalizer",
    "idna",
    "config",
    "browser",
    "parser",
    "solver",
    "human",
    "actions",
    "gui",
    "models",
    "page_selectors",
    "updater",
]

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "SmartBook Solver",
    "--icon", "Icon.ico",
]

# Add all hidden imports
for imp in hidden_imports:
    cmd += ["--hidden-import", imp]

# Bundle selenium's internal data (includes selenium-manager for auto chromedriver)
try:
    import selenium
    selenium_dir = os.path.dirname(selenium.__file__)
    cmd += ["--collect-all", "selenium"]
except ImportError:
    print("WARNING: selenium not installed in this env, build may fail")

# Bundle certifi CA certs so HTTPS works
try:
    import certifi
    cmd += ["--collect-data", "certifi"]
except ImportError:
    pass

# Include .env template if it exists
if os.path.exists(".env"):
    cmd += ["--add-data", ".env;."]

# Include launch_chrome.bat so it can be extracted if needed
if os.path.exists("launch_chrome.bat"):
    cmd += ["--add-data", "launch_chrome.bat;."]

# Include app icon
if os.path.exists("Icon.png"):
    cmd += ["--add-data", "Icon.png;."]

cmd.append("main.py")

print(f"Running PyInstaller build...")
print(f"Command: {' '.join(cmd)}\n")
subprocess.run(cmd, check=True)
print("\nBuild complete! Your .exe is in the dist/ folder.")
print("Upload 'dist/SmartBook Solver.exe' to GitHub Releases.")
