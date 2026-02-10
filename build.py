"""Build standalone app with PyInstaller."""
import subprocess
import sys
import os

os.chdir(os.path.dirname(__file__))

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "SmartBook Solver",
    "main.py",
]

print(f"Running: {' '.join(cmd)}")
subprocess.run(cmd, check=True)
print("\nBuild complete! Your app is in the dist/ folder.")
