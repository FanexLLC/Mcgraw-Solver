# McGraw-Hill SmartBook Solver - Step-by-Step Implementation Guide

## Goal
Build a Python tool with a GUI that automates McGraw-Hill SmartBook assignments. It controls a browser, reads questions, gets answers from GPT, selects them with human-like behavior, and clicks Next. Packaged as a shareable .exe.

---

## Phase 1: Project Foundation

### Task 1.1: Create project files and folder structure
Create the following files (all empty initially except where noted):
```
Mcgraw-Hill/
├── main.py
├── gui.py
├── browser.py
├── parser.py
├── solver.py
├── config.py
├── human.py
├── requirements.txt
├── setup.bat
├── .env
└── .gitignore
```

### Task 1.2: Write `requirements.txt`
```
selenium
undetected-chromedriver
openai
python-dotenv
```

### Task 1.3: Write `.gitignore`
```
.env
__pycache__/
dist/
build/
*.spec
*.exe
```

### Task 1.4: Write `.env` template
```
OPENAI_API_KEY=your-key-here
```

### Task 1.5: Write `setup.bat`
```bat
@echo off
echo ====================================
echo  McGraw-Hill SmartBook Solver Setup
echo ====================================
echo.
echo Installing Python dependencies...
pip install -r requirements.txt
echo.
echo Setup complete!
echo.
echo NEXT STEPS:
echo 1. Open .env and paste your OpenAI API key
echo 2. Run: python main.py
echo.
pause
```

**Checkpoint 1**: Run `pip install -r requirements.txt` and confirm all packages install without errors.

---

## Phase 2: Configuration

### Task 2.1: Write `config.py`
This file holds all tunable settings:
```python
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GPT_MODEL = "gpt-4o-mini"  # cheap + fast, switch to "gpt-4o" for harder subjects
GPT_TEMPERATURE = 0.1       # low = more deterministic answers

# Timing (seconds) - human-like delays
MIN_DELAY = 2.0             # minimum pause between actions
MAX_DELAY = 5.0             # maximum pause between actions
READING_WPM = 250           # simulated reading speed (words per minute)
READING_WPM_VARIANCE = 50   # +/- variance on reading speed
TYPE_MIN_DELAY = 0.05       # minimum delay between keystrokes (seconds)
TYPE_MAX_DELAY = 0.15       # maximum delay between keystrokes (seconds)
CLICK_HOVER_MIN = 0.2       # min delay between hover and click
CLICK_HOVER_MAX = 0.6       # max delay between hover and click

# Accuracy
TARGET_ACCURACY = 0.90      # intentionally miss ~10% of questions

# Browser
CHROME_PROFILE_DIR = os.path.join(os.path.expanduser("~"), ".smartbook_solver_profile")
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
```

**Checkpoint 2**: Import `config.py` in a Python shell and verify `OPENAI_API_KEY` loads from `.env`.

---

## Phase 3: Human-Like Behavior Module

### Task 3.1: Write `human.py`
Implements all human simulation functions:

**Functions to implement:**

1. `random_delay(min_s, max_s)` - Sleep for a random duration between min and max seconds.

2. `reading_delay(text)` - Calculate and sleep based on word count. Formula: `(word_count / reading_wpm) * 60` seconds, with random variance applied.

3. `human_type(element, text, driver)` - Type text character by character using ActionChains. For each character: random delay (TYPE_MIN_DELAY to TYPE_MAX_DELAY), occasionally insert a longer pause (300-600ms) every 5-10 characters to simulate thinking.

4. `human_click(element, driver)` - Move mouse to element with a random pixel offset (+/-5px from center on both axes), pause (CLICK_HOVER_MIN to CLICK_HOVER_MAX), then click.

5. `random_scroll(driver)` - 30% chance to scroll slightly up or down (50-150px) before interacting. Simulates looking around the page.

6. `should_miss()` - Returns True with probability `(1 - TARGET_ACCURACY)`. When True, the solver will intentionally pick a wrong answer.

**Checkpoint 3**: Test `human_type` and `human_click` on a simple test page (e.g., open google.com and type in the search box).

---

## Phase 4: Browser Module

### Task 4.1: Write `browser.py`
Uses `undetected_chromedriver` to launch a stealth Chrome instance.

**Functions to implement:**

1. `start_browser()` -> returns a Chrome WebDriver instance
   - Use `undetected_chromedriver.Chrome()` with options:
     - `--user-data-dir={CHROME_PROFILE_DIR}` (persistent login)
     - `--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}`
     - `--disable-blink-features=AutomationControlled`
     - `--no-first-run`, `--no-service-autorun`
   - Never use headless mode
   - Return the driver

2. `wait_for_element(driver, selector, timeout=15)` -> returns WebElement or None
   - Use `WebDriverWait(driver, timeout).until(EC.presence_of_element_located(...))`
   - Catch `TimeoutException` and return None

3. `wait_for_clickable(driver, selector, timeout=15)` -> returns WebElement or None
   - Same but with `EC.element_to_be_clickable(...)`

4. `is_page_ready(driver)` -> bool
   - Check `document.readyState === 'complete'` via JavaScript
   - Also check for absence of common loading spinner selectors

5. `safe_click(driver, element)` - Wrapper that calls `human_click` from `human.py`

6. `safe_type(driver, element, text)` - Wrapper that calls `human_type` from `human.py`

**Checkpoint 4**: Run `start_browser()`, verify Chrome opens without the "controlled by automated software" banner. Navigate to McGraw-Hill Connect manually and confirm you can log in and the session persists on next launch.

---

## Phase 5: Question Parser

### Task 5.1: Write `parser.py`
Extracts question data from the current SmartBook page.

**IMPORTANT**: The CSS selectors below are initial guesses. We MUST inspect the actual SmartBook HTML to get the real selectors. The first run will be a discovery session.

**Functions to implement:**

1. `detect_page_type(driver)` -> string
   Returns one of:
   - `"question"` - a question is displayed
   - `"reading"` - a reading/review screen (no question, just content)
   - `"complete"` - assignment is finished
   - `"confidence"` - confidence slider is showing
   - `"loading"` - page is still loading
   - `"unknown"` - can't determine

   Detection logic (check in order):
   - Look for completion indicators (score summary, "assignment complete" text)
   - Look for confidence slider elements
   - Look for question text containers
   - Look for reading passage without question elements
   - Default to "unknown"

2. `parse_question(driver)` -> dict
   Returns:
   ```python
   {
       "type": "mc_single" | "mc_multi" | "fill" | "dropdown" | "unknown",
       "question": "question text here",
       "choices": [
           {"label": "A", "text": "choice text", "element": WebElement},
           ...
       ],
       "context": "any passage or surrounding text",
       "input_elements": [WebElement, ...],  # for fill-in / dropdown
   }
   ```

   Detection logic:
   - If radio buttons or single-select list -> `mc_single`
   - If checkboxes or "select all" instructions -> `mc_multi`
   - If text input fields -> `fill`
   - If `<select>` dropdowns -> `dropdown`
   - Otherwise -> `unknown`

3. `handle_confidence(driver)` -> None
   - Randomly select "I know it" (70%) or "Think so" (30%)
   - Click the selected option with human-like behavior

4. `click_next_button(driver)` -> bool
   - Look for Next/Submit/Continue button (try multiple selectors)
   - Click it with human-like behavior
   - Return True if found and clicked, False otherwise

**Checkpoint 5**: Open a SmartBook assignment manually. Run `detect_page_type()` and `parse_question()` and print the results. Verify question text and choices are extracted correctly. **This is the most critical checkpoint** -- if selectors are wrong, fix them here before proceeding.

---

## Phase 6: GPT Solver

### Task 6.1: Write `solver.py`
Sends questions to GPT and parses the response.

**Functions to implement:**

1. `get_answer(question_data)` -> dict
   - Takes the dict from `parse_question()`
   - Builds a GPT prompt based on question type:

   **For `mc_single`:**
   ```
   Answer this multiple choice question. Reply with ONLY the letter (A, B, C, or D).

   Question: {question}
   Context: {context}

   A) {choice_a}
   B) {choice_b}
   C) {choice_c}
   D) {choice_d}

   Answer:
   ```

   **For `mc_multi`:**
   ```
   Answer this question by selecting ALL correct options. Reply with ONLY the letters separated by commas (e.g., "A, C").

   Question: {question}
   ...
   ```

   **For `fill`:**
   ```
   Answer this question with a short, precise answer. Reply with ONLY the answer text, nothing else.

   Question: {question}
   Context: {context}

   Answer:
   ```

   **For `dropdown`:**
   ```
   Fill in each blank with the correct option from the choices given. Reply as:
   1: chosen_option
   2: chosen_option

   Sentence: {question_with_blanks}
   Blank 1 options: {options}
   Blank 2 options: {options}
   ```

   - Call `openai.chat.completions.create(model=GPT_MODEL, temperature=GPT_TEMPERATURE, messages=[...])`
   - Parse the response text

2. `parse_gpt_response(response_text, question_data)` -> action dict
   Returns:
   ```python
   {
       "type": "click" | "type" | "multi_click" | "dropdown",
       "targets": [WebElement, ...],  # elements to click or type into
       "values": ["text", ...],        # text to type (for fill-in)
   }
   ```
   - For MC: match letter to the corresponding choice element
   - For fill-in: return the text answer
   - For multi-select: match each letter to its choice element

3. `maybe_inject_error(action, question_data)` -> action dict
   - Call `should_miss()` from `human.py`
   - If True, replace the correct answer with a random wrong choice
   - Log that an intentional miss was injected

**Checkpoint 6**: Manually copy a question from SmartBook, call `get_answer()` with it, and verify GPT returns a correct, properly formatted answer.

---

## Phase 7: GUI

### Task 7.1: Write `gui.py`
Simple tkinter window for easy use.

**Layout:**
```
+-------------------------------------+
|  McGraw-Hill SmartBook Solver       |
+-------------------------------------+
|  API Key: [____________________]    |
|                                     |
|  Speed:    [Slow] [Normal] [Fast]   |
|  Accuracy: [=======90%==========]   |
|  Model:    [gpt-4o-mini v]         |
+-------------------------------------+
|  [ Start]  [ Pause]  [ Stop]       |
+-------------------------------------+
|  Status Log:                        |
|  +-------------------------------+  |
|  | Q1: What is...  -> B          |  |
|  | Q2: Define...   -> Mitosis    |  |
|  | Q3: Select...   -> A, C (miss)|  |
|  | Waiting 3.4s...               |  |
|  +-------------------------------+  |
|                                     |
|  Questions: 3/27  |  Correct: 2/3  |
+-------------------------------------+
```

**Implementation details:**
- API key field saves to `.env` on change
- Start button launches `start_browser()` + solve loop in a background thread
- Pause sets a threading Event flag that the solve loop checks
- Stop signals the loop to exit and closes the browser
- Status log is a scrollable Text widget, auto-scrolls to bottom
- Bottom bar shows progress and score count
- Speed presets adjust MIN_DELAY/MAX_DELAY:
  - Slow: 4-8s
  - Normal: 2-5s (default)
  - Fast: 1-3s

**Checkpoint 7**: Launch the GUI. Verify all buttons render. Enter an API key, click Start, verify Chrome opens. Click Pause/Resume, verify the loop halts and continues. Click Stop, verify browser closes.

---

## Phase 8: Main Orchestration Loop

### Task 8.1: Write `main.py`
Ties everything together.

**Flow:**
```
main.py starts
  -> Launch GUI (gui.py)
  -> User enters API key, clicks Start
  -> GUI calls start_solver() in background thread
    -> start_browser() opens Chrome
    -> Log: "Browser opened. Navigate to your SmartBook assignment and start it."
    -> Poll loop: wait until SmartBook question page is detected
    -> SOLVE LOOP:
      |
      +-- Check if Stop was requested -> break
      +-- Check if Pause is active -> wait until resumed
      |
      +-- detect_page_type()
      |   +-- "loading" -> wait 1s, continue
      |   +-- "reading" -> click_next_button(), continue
      |   +-- "confidence" -> handle_confidence(), continue
      |   +-- "complete" -> log final score, break
      |   +-- "unknown" -> log warning, wait for manual input, continue
      |   +-- "question" -> proceed to parse
      |
      +-- parse_question()
      +-- reading_delay(question_text)     # simulate reading
      +-- random_scroll()                   # occasional scroll
      +-- get_answer(question_data)         # ask GPT
      +-- maybe_inject_error(action)        # intentional miss chance
      |
      +-- Execute answer:
      |   +-- "click" -> safe_click(target_element)
      |   +-- "type" -> safe_click(input) + safe_type(input, answer)
      |   +-- "multi_click" -> for each target: safe_click + random_delay
      |   +-- "dropdown" -> for each select: click + choose option
      |
      +-- random_delay(0.5, 1.5)           # pause before Next
      +-- click_next_button()
      +-- random_delay(MIN_DELAY, MAX_DELAY) # pause between questions
      +-- Update GUI log + counters
      +-- Loop back
```

**Error handling at each step:**
- If `parse_question()` fails -> log error, try to click Next, continue
- If `get_answer()` fails (API error) -> retry once after 3s, if still fails -> pause and alert
- If `click_next_button()` fails -> wait 2s, retry with alternative selectors
- If browser crashes -> log error, stop loop, alert user
- If page navigates away from SmartBook -> detect and pause, alert user

**Checkpoint 8**: Run full end-to-end test on a real SmartBook assignment. Verify:
- [ ] Questions are detected and parsed correctly
- [ ] GPT returns correct answers
- [ ] Answers are selected with human-like delays
- [ ] Next button is clicked and next question loads
- [ ] GUI log updates in real time
- [ ] Pause/Resume works mid-assignment
- [ ] Assignment completion is detected
- [ ] At least one intentional miss occurs (check score)

---

## Phase 9: Packaging for Sharing

### Task 9.1: Build .exe with PyInstaller
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name SmartBookSolver main.py
```
- Output: `dist/SmartBookSolver.exe`
- Friends need: Chrome installed + OpenAI API key
- The .exe opens the GUI directly, no Python needed

### Task 9.2: Create a share package
Bundle into a zip:
```
SmartBookSolver/
+-- SmartBookSolver.exe    # or main.py + all .py files
+-- setup.bat              # if not using .exe
+-- requirements.txt       # if not using .exe
+-- .env                   # template with placeholder key
+-- README.txt             # simple 5-step instructions
```

**README.txt content:**
```
HOW TO USE:
1. Make sure Google Chrome is installed
2. Get an OpenAI API key from https://platform.openai.com/api-keys
3. Run SmartBookSolver.exe (or: run setup.bat then python main.py)
4. Paste your API key into the app
5. Click Start, then go to your SmartBook assignment in the browser that opens
6. The solver handles the rest!

TIPS:
- First time: you'll need to log into McGraw-Hill Connect in the browser. Your login stays saved.
- Keep the speed on Normal or Slow for safety.
- Don't set accuracy above 95% - it looks suspicious.
```

**Checkpoint 9**: Send the zip to a test machine (or a friend). Verify they can run it from scratch with only Chrome + API key.

---

## Phase 10: Selector Discovery Session

### Task 10.1: Inspect SmartBook HTML (MUST DO BEFORE Phase 5 coding)
This is a live inspection session where we:
1. Open a real SmartBook assignment in Chrome DevTools
2. Identify the actual CSS selectors / XPaths for:
   - [ ] Question text container
   - [ ] Answer choice elements (MC)
   - [ ] Input fields (fill-in)
   - [ ] Dropdown selects
   - [ ] Next / Submit / Continue button
   - [ ] Confidence slider options
   - [ ] Loading spinner
   - [ ] Assignment complete indicator
   - [ ] Reading/review screen indicator
3. Record all selectors in a `SELECTORS` dict in `parser.py`
4. Test each selector with `driver.find_element()` to confirm it works

**This phase is blocking** -- all parser code depends on having the right selectors.

---

## Anti-Detection Summary

| Technique | Implementation |
|-----------|---------------|
| No automation flags | `undetected-chromedriver` patches these out |
| Human-like timing | Random delays, reading speed simulation |
| Imperfect accuracy | Configurable miss rate (default ~10%) |
| Real mouse movement | ActionChains with random offset |
| Character-by-character typing | Random per-keystroke delay |
| Persistent login | `--user-data-dir` (no automated login) |
| Real browser window | Never headless, normal window size |
| No rapid-fire requests | Minimum 2-5s between actions |

---

## Edge Cases Handled

1. **Reading/review screens** (no question) -> detect and click through
2. **Confidence sliders** -> randomize between "I know it" and "Think so"
3. **"Select all that apply"** -> GPT returns multiple letters, click each
4. **Dropdown blanks in sentences** -> parse each dropdown, fill each
5. **Image-based questions** -> extract alt text, warn if no text available
6. **Assignment complete screen** -> detect and stop gracefully
7. **Confirmation modals** -> auto-dismiss
8. **Page load delays / spinners** -> wait with timeout
9. **Session timeout** -> detect login page redirect, pause and alert user
10. **Unknown question type** -> pause for manual intervention, don't crash

---

## Execution Order Summary

| Order | Task | Depends On | Description |
|-------|------|-----------|-------------|
| 1 | Phase 1 | -- | Create files, install deps |
| 2 | Phase 2 | Phase 1 | Write config.py |
| 3 | Phase 3 | Phase 2 | Write human.py (behavior simulation) |
| 4 | Phase 4 | Phase 3 | Write browser.py (Selenium setup) |
| 5 | **Phase 10** | Phase 4 | **Inspect SmartBook HTML for selectors** |
| 6 | Phase 5 | Phase 10 | Write parser.py (with real selectors) |
| 7 | Phase 6 | Phase 2 | Write solver.py (GPT integration) |
| 8 | Phase 7 | -- | Write gui.py (tkinter interface) |
| 9 | Phase 8 | All above | Write main.py (orchestration) |
| 10 | Phase 9 | Phase 8 | Package as .exe for sharing |

Note: Phase 6 (solver) and Phase 7 (GUI) can be built in parallel with Phase 5 since they don't depend on selectors.
