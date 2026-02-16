from __future__ import annotations
import time
import logging
import sys
from typing import Any
from datetime import datetime

import config
import browser
import parser
import solver
import human
import actions
from gui import SolverGUI
from models import Action

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class SolverApp:
    """Top-level orchestrator that ties the GUI, browser, and solver together."""

    def __init__(self) -> None:
        self.driver = None
        self.pause_flag = False
        self.stop_flag = False
        self.session_start_time = None
        self.gui = SolverGUI(
            on_start=self.on_start,
            on_pause=self.on_pause,
            on_stop=self.on_stop,
        )

    # ── Settings ──────────────────────────────────────────────────

    def _apply_settings(self, settings: dict[str, Any]) -> None:
        config.MIN_DELAY = settings["min_delay"]
        config.MAX_DELAY = settings["max_delay"]
        config.TARGET_ACCURACY = settings["accuracy"]
        config.GPT_MODEL = settings["model"]

    # ── Callbacks ─────────────────────────────────────────────────

    def on_start(self, settings: dict[str, Any]) -> None:
        try:
            self.stop_flag = False
            self.pause_flag = False
            self._apply_settings(settings)

            # Capture session start time for grace period logic
            self.session_start_time = datetime.utcnow().isoformat()

            try:
                solver.init_client(settings["access_key"], self.session_start_time)
                self.gui.log("Connected to server.")
            except (ConnectionError, ValueError) as e:
                self.gui.log(f"ERROR: {e}")
                self.gui.root.after(0, self.gui._on_stop)
                return

            try:
                self.gui.log("Connecting to Chrome (make sure you clicked Launch Chrome first)...")
                self.driver = browser.connect_to_browser()
                self.gui.log("Connected to Chrome!")
                self.gui.log("Make sure you're on a SmartBook question page.")
                self.gui.log("The solver will start answering automatically.")
            except ConnectionError as e:
                self.gui.log(f"ERROR launching browser: {e}")
                self.gui.root.after(0, self.gui._on_stop)
                return

            self.gui.log("Waiting for SmartBook question page...")
            self._solve_loop()

        except Exception as e:
            logger.exception("Unexpected error in on_start")
            self.gui.log(f"ERROR: {e}")
            self.gui.root.after(0, self.gui._on_stop)

    def on_pause(self, is_paused: bool) -> None:
        self.pause_flag = is_paused

    def on_stop(self) -> None:
        self.stop_flag = True
        self.driver = None

    # ── Main Loop ─────────────────────────────────────────────────

    def _solve_loop(self) -> None:
        question_num = 0
        correct_num = 0
        consecutive_unknown = 0

        while not self.stop_flag:
            while self.pause_flag and not self.stop_flag:
                time.sleep(0.5)
            if self.stop_flag:
                break

            try:
                if not browser.is_page_ready(self.driver):
                    time.sleep(1)
                    continue

                page_type = parser.detect_page_type(self.driver)
                logger.info(f"Page type: {page_type}")

                if page_type == "loading":
                    time.sleep(1)
                    consecutive_unknown = 0
                    continue

                if page_type == "complete":
                    self.gui.log(f"Assignment complete! {correct_num}/{question_num} answered.")
                    self.gui.update_status(question_num, correct_num, question_num)
                    break

                if page_type == "recharge":
                    self._handle_recharge()
                    consecutive_unknown = 0
                    continue

                if page_type == "reading":
                    self.gui.log("Reading screen detected, clicking Next...")
                    human.random_delay(1.0, 3.0)
                    parser.click_next_button(self.driver)
                    human.random_delay(config.MIN_DELAY, config.MAX_DELAY)
                    consecutive_unknown = 0
                    continue

                if page_type == "unknown":
                    consecutive_unknown += 1
                    if consecutive_unknown > 10:
                        self.gui.log("No SmartBook content detected. Waiting...")
                        consecutive_unknown = 0
                    time.sleep(2)
                    continue

                if page_type == "question":
                    consecutive_unknown = 0
                    question_num += 1
                    was_correct = self._handle_question(question_num)
                    if was_correct:
                        correct_num += 1
                    self.gui.update_status(question_num, correct_num)

            except Exception as e:
                logger.exception("Error in solve loop")
                self.gui.log(f"Error: {e}")
                time.sleep(3)

        self.gui.log("Solve loop ended.")
        self.driver = None
        self.gui.root.after(0, self.gui._on_stop)

    # ── Question Handling ─────────────────────────────────────────

    def _handle_question(self, question_num: int) -> bool:
        """Parse, solve, and execute a single question. Returns True if answered correctly."""
        question_data = parser.parse_question(self.driver)

        if question_data.type == "unknown":
            self.gui.log(f"Q{question_num}: Unknown question type. Skipping...")
            human.random_delay(2.0, 4.0)
            parser.click_next_button(self.driver)
            human.random_delay(config.MIN_DELAY, config.MAX_DELAY)
            return False

        q_preview = question_data.question[:60]
        self.gui.log(f"Q{question_num}: {q_preview}...")

        human.reading_delay(question_data.question)
        human.random_scroll(self.driver)

        # Get answer (with one retry)
        action = self._get_answer_with_retry(question_data)
        if action is None:
            parser.click_next_button(self.driver)
            human.random_delay(config.MIN_DELAY, config.MAX_DELAY)
            return False

        action, was_miss = solver.maybe_inject_error(action, question_data)
        miss_tag = " (intentional miss)" if was_miss else ""

        try:
            actions.execute(action, self.driver)
            self.gui.log(f"  -> {action.answer_text}{miss_tag}")
        except Exception as e:
            self.gui.log(f"  Error executing answer: {e}")
            return False

        human.random_delay(0.5, 1.5)
        parser.submit_with_confidence(self.driver)

        human.random_delay(1.5, 2.5)
        if parser.needs_resource_review(self.driver):
            self.gui.log("  Resource review required — reading concept...")
            parser.handle_recharge_page(self.driver)
            human.random_delay(1.0, 2.0)

        human.random_delay(1.0, 2.0)
        parser.click_next_question(self.driver)

        delay = human.random_delay(config.MIN_DELAY, config.MAX_DELAY)
        self.gui.log(f"  Waiting {delay:.1f}s...")

        return not was_miss

    def _get_answer_with_retry(self, question_data) -> Action | None:
        """Try to get an answer, retry once on failure."""
        try:
            return solver.get_answer(question_data)
        except PermissionError as e:
            self.gui.log(f"  {e}")
            return None
        except Exception as e:
            self.gui.log(f"  Server error: {e}. Retrying...")
            time.sleep(3)
            try:
                return solver.get_answer(question_data)
            except Exception as e2:
                self.gui.log(f"  Server error again: {e2}. Skipping question.")
                return None

    def _handle_recharge(self) -> None:
        self.gui.log("Concept resource page detected — opening and closing reading...")
        parser.handle_recharge_page(self.driver)
        human.random_delay(1.0, 2.0)
        self.gui.log("Clicking Next Question...")
        parser.click_next_question(self.driver)
        human.random_delay(config.MIN_DELAY, config.MAX_DELAY)

    # ── Entry Point ───────────────────────────────────────────────

    def run(self) -> None:
        self.gui.log("Welcome to SmartBook Solver!")
        self.gui.log("1. Click 'Launch Chrome' to open Chrome")
        self.gui.log("2. Navigate to your SmartBook assignment")
        self.gui.log("3. Enter your access key and click Start")
        self.gui.run()


if __name__ == "__main__":
    app = SolverApp()
    app.run()
