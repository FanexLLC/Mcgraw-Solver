import tkinter as tk
from tkinter import ttk
import threading
import webbrowser
import os
import sys
import time
import requests
import config
import browser
import updater


# ---------------------------------------------------------------------------
# Color palette — dark, muted tones matching the app icon
# ---------------------------------------------------------------------------
_C = {
    "bg":          "#0c0c14",
    "bg_card":     "#12121c",
    "bg_input":    "#181824",
    "border":      "#222233",
    "text":        "#b8b8cc",
    "text_dim":    "#505068",
    "cyan":        "#4a9cb8",
    "magenta":     "#8a4466",
    "green":       "#3a8a5c",
    "yellow":      "#9a8a3a",
    "red":         "#8a3a44",
    "log_bg":      "#0a0a10",
}

_FONT       = "Helvetica"
_FONT_MONO  = "Menlo"


class SolverGUI:
    def __init__(self, on_start=None, on_pause=None, on_stop=None):
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_stop = on_stop

        self.is_running = False
        self.is_paused = False
        self.question_count = 0
        self.correct_count = 0
        self._validated_key = None
        self._user_plan = None
        self._allowed_models = []
        self._preferred_model = None
        self._model_names = {}

        self.root = tk.Tk()
        self.root.title("SmartBook Solver")
        self.root.geometry("540x700")
        self.root.resizable(True, True)
        self.root.minsize(420, 520)
        self.root.configure(bg=_C["bg"])

        # Load icon
        self._icon_img = None
        self._header_icon = None
        if getattr(sys, "frozen", False):
            icon_path = os.path.join(sys._MEIPASS, "Icon.png")
        else:
            icon_path = os.path.join(os.path.dirname(__file__), "Icon.png")
        if os.path.exists(icon_path):
            try:
                self._icon_img = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, self._icon_img)
                factor = max(1, self._icon_img.width() // 40)
                self._header_icon = self._icon_img.subsample(factor, factor)
            except Exception:
                pass

        # Container for page switching
        self._container = tk.Frame(self.root, bg=_C["bg"])
        self._container.pack(fill="both", expand=True)

        # Build both pages
        self._login_frame = tk.Frame(self._container, bg=_C["bg"])
        self._solver_frame = tk.Frame(self._container, bg=_C["bg"])

        self._build_login_page()
        self._build_solver_page()

        # Start on login page
        self._show_login()

        self._check_for_update()

    # ==================================================================
    # PAGE SWITCHING
    # ==================================================================
    def _show_login(self):
        self._solver_frame.pack_forget()
        self._login_frame.pack(fill="both", expand=True)
        self.root.geometry("420x520")

    def _show_solver(self):
        self._login_frame.pack_forget()
        self._solver_frame.pack(fill="both", expand=True)
        self.root.geometry("540x700")

    # ==================================================================
    # UPDATE BANNER
    # ==================================================================
    def _check_for_update(self):
        def _check():
            result = updater.check_for_update()
            if result:
                version, url = result
                self.root.after(0, self._show_update_banner, version, url)
        threading.Thread(target=_check, daemon=True).start()

    def _show_update_banner(self, version, url):
        banner = tk.Frame(self.root, bg=_C["cyan"])
        banner.pack(fill="x", padx=0, pady=0, before=self._container)

        tk.Label(
            banner, text=f"  Update v{version} available",
            fg=_C["bg"], bg=_C["cyan"], font=(_FONT, 11, "bold"),
        ).pack(side="left", padx=(12, 4), pady=6)

        tk.Button(
            banner, text="Download", command=lambda: webbrowser.open(url),
            bg=_C["bg"], fg=_C["cyan"], font=(_FONT, 10, "bold"),
            relief="flat", cursor="hand2", padx=10, pady=2,
        ).pack(side="left", pady=4)

        tk.Button(
            banner, text="X", command=banner.destroy,
            bg=_C["cyan"], fg=_C["bg"], font=(_FONT, 10, "bold"),
            relief="flat", cursor="hand2", width=3,
        ).pack(side="right", pady=4, padx=6)

    # ==================================================================
    # PAGE 1 — LOGIN
    # ==================================================================
    def _build_login_page(self):
        page = self._login_frame

        # Spacer to push content toward center
        tk.Frame(page, bg=_C["bg"], height=40).pack()

        # Icon (larger on login)
        if self._icon_img:
            try:
                factor = max(1, self._icon_img.width() // 80)
                self._login_icon = self._icon_img.subsample(factor, factor)
                tk.Label(page, image=self._login_icon, bg=_C["bg"]).pack(pady=(0, 16))
            except Exception:
                pass

        # Title
        tk.Label(
            page, text="SmartBook Solver",
            font=(_FONT, 22, "bold"), fg=_C["cyan"], bg=_C["bg"],
        ).pack()
        tk.Label(
            page, text=f"v{config.APP_VERSION}",
            font=(_FONT, 10), fg=_C["text_dim"], bg=_C["bg"],
        ).pack(pady=(0, 28))

        # Key entry card
        card = tk.Frame(page, bg=_C["bg_card"], highlightbackground=_C["border"],
                        highlightthickness=1)
        card.pack(padx=40, fill="x")

        tk.Label(card, text="Enter your access key to continue",
                 font=(_FONT, 10), fg=_C["text_dim"], bg=_C["bg_card"],
                 ).pack(padx=20, pady=(18, 10))

        self._login_key_var = tk.StringVar(value=config.ACCESS_KEY)
        self._login_entry = tk.Entry(
            card, textvariable=self._login_key_var, show="*", width=32,
            bg=_C["bg_input"], fg=_C["text"], insertbackground=_C["cyan"],
            relief="flat", font=(_FONT_MONO, 12), highlightthickness=1,
            highlightbackground=_C["border"], highlightcolor=_C["cyan"],
            justify="center",
        )
        self._login_entry.pack(padx=20, pady=(0, 14))
        self._login_entry.bind("<Return>", lambda _e: self._on_validate_key())

        self._login_btn = tk.Button(
            card, text="Continue", command=self._on_validate_key,
            bg=_C["cyan"], fg=_C["bg"], font=(_FONT, 12, "bold"),
            relief="flat", cursor="hand2", padx=24, pady=6,
            activebackground="#5aacca", activeforeground=_C["bg"],
        )
        self._login_btn.pack(pady=(0, 18))

        # Error/status label
        self._login_status = tk.Label(
            page, text="", font=(_FONT, 10), fg=_C["red"], bg=_C["bg"],
        )
        self._login_status.pack(pady=(12, 0))

    def _on_validate_key(self):
        key = self._login_key_var.get().strip()
        if not key:
            self._login_status.config(text="Please enter your access key.", fg=_C["red"])
            return

        # Disable button while validating
        self._login_btn.config(state="disabled", text="Validating...")
        self._login_status.config(text="", fg=_C["text_dim"])

        def _validate():
            try:
                resp = requests.post(
                    f"{config.SERVER_URL}/api/validate",
                    json={"access_key": key},
                    timeout=10,
                )
                try:
                    data = resp.json()
                except ValueError:
                    self.root.after(0, self._on_key_invalid, f"Server error ({resp.status_code}). Try again later.")
                    return
                if resp.status_code == 200 and data.get("valid"):
                    self._validated_key = key
                    # Store plan and model information
                    self._user_plan = data.get("plan", "monthly")
                    self._allowed_models = data.get("allowed_models", ["gpt-4o-mini"])
                    self._preferred_model = data.get("preferred_model", self._allowed_models[0])
                    self._model_names = data.get("model_names", {})
                    self._save_access_key(key)
                    self.root.after(0, self._on_key_valid)
                else:
                    error = data.get("error", "Invalid access key")
                    self.root.after(0, self._on_key_invalid, error)
            except requests.ConnectionError:
                self.root.after(0, self._on_key_invalid, "Cannot reach server. Check your connection.")
            except Exception as e:
                self.root.after(0, self._on_key_invalid, str(e))

        threading.Thread(target=_validate, daemon=True).start()

    def _on_key_valid(self):
        self._login_status.config(text="Access granted", fg=_C["green"])
        self._login_btn.config(state="normal", text="Continue")
        # Set the key on the solver page too
        self.access_key_var.set(self._validated_key)
        # Transition after a brief moment
        self.root.after(400, self._show_solver)

    def _on_key_invalid(self, error):
        self._login_status.config(text=error, fg=_C["red"])
        self._login_btn.config(state="normal", text="Continue")

    # ==================================================================
    # PAGE 2 — SOLVER
    # ==================================================================
    def _build_solver_page(self):
        page = self._solver_frame

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TCombobox",
                        fieldbackground=_C["bg_input"],
                        background=_C["bg_input"],
                        foreground=_C["text"],
                        borderwidth=0,
                        arrowcolor=_C["cyan"])
        style.map("Dark.TCombobox",
                   fieldbackground=[("readonly", _C["bg_input"])],
                   selectbackground=[("readonly", _C["bg_input"])],
                   selectforeground=[("readonly", _C["text"])])

        # ── Header ────────────────────────────────────────────────────
        header = tk.Frame(page, bg=_C["bg"])
        header.pack(fill="x", padx=24, pady=(20, 4))

        if self._header_icon:
            tk.Label(header, image=self._header_icon, bg=_C["bg"]).pack(side="left", padx=(0, 12))

        title_block = tk.Frame(header, bg=_C["bg"])
        title_block.pack(side="left")
        tk.Label(
            title_block, text="SmartBook Solver",
            font=(_FONT, 20, "bold"), fg=_C["cyan"], bg=_C["bg"],
        ).pack(anchor="w")
        tk.Label(
            title_block, text=f"v{config.APP_VERSION}",
            font=(_FONT, 10), fg=_C["text_dim"], bg=_C["bg"],
        ).pack(anchor="w")

        # Logout button
        tk.Button(
            header, text="Logout", command=self._on_logout,
            bg=_C["bg_input"], fg=_C["text_dim"], font=(_FONT, 9),
            relief="flat", cursor="hand2", padx=8, pady=2,
            activebackground=_C["border"], activeforeground=_C["text"],
        ).pack(side="right", pady=8)

        tk.Frame(page, bg=_C["border"], height=1).pack(fill="x", padx=24, pady=(12, 0))

        # ── Settings card ─────────────────────────────────────────────
        card = tk.Frame(page, bg=_C["bg_card"], highlightbackground=_C["border"],
                        highlightthickness=1)
        card.pack(fill="x", padx=24, pady=(14, 0))

        tk.Label(card, text="SETTINGS", font=(_FONT, 9, "bold"),
                 fg=_C["text_dim"], bg=_C["bg_card"]).pack(anchor="w", padx=16, pady=(12, 6))

        # Hidden access key var (carries over from login)
        self.access_key_var = tk.StringVar(value=config.ACCESS_KEY)

        # Model selection - only show if user has multiple models
        # Build allowed models list based on user's plan
        if self._allowed_models and len(self._allowed_models) > 1:
            self._setting_row(card, "AI Model")

            # Create display names from allowed models
            model_display_options = [self._model_names.get(m, m) for m in self._allowed_models]
            default_display = self._model_names.get(self._preferred_model, model_display_options[0])

            self.model_var = tk.StringVar(value=default_display)
            self.model_combo = ttk.Combobox(
                card, textvariable=self.model_var,
                values=model_display_options,
                state="readonly", width=30, style="Dark.TCombobox",
                font=(_FONT, 11),
            )
            self.model_combo.pack(padx=16, pady=(0, 10), anchor="w")
            self.model_combo.bind("<<ComboboxSelected>>", self._on_model_changed)
        elif self._allowed_models:
            # Single model - just show which one
            self._setting_row(card, "AI Model")
            model_name = self._model_names.get(self._allowed_models[0], self._allowed_models[0])
            tk.Label(
                card, text=model_name,
                font=(_FONT, 11), fg=_C["text"], bg=_C["bg_card"]
            ).pack(padx=16, pady=(0, 10), anchor="w")

        # Speed + Accuracy row
        row = tk.Frame(card, bg=_C["bg_card"])
        row.pack(fill="x", padx=16, pady=(0, 14))

        # Speed
        speed_col = tk.Frame(row, bg=_C["bg_card"])
        speed_col.pack(side="left", fill="x", expand=True)
        tk.Label(speed_col, text="Speed", font=(_FONT, 9, "bold"),
                 fg=_C["text_dim"], bg=_C["bg_card"]).pack(anchor="w", pady=(0, 4))
        speed_btn_frame = tk.Frame(speed_col, bg=_C["bg_card"])
        speed_btn_frame.pack(anchor="w")
        self.speed_var = tk.StringVar(value="Normal")
        self._speed_buttons = {}
        for speed in ["Slow", "Normal", "Fast"]:
            btn = tk.Button(
                speed_btn_frame, text=speed, width=6,
                font=(_FONT, 10), relief="flat", cursor="hand2",
                bg=_C["bg_input"], fg=_C["text_dim"],
                activebackground="#5aacca", activeforeground=_C["bg"],
                command=lambda s=speed: self._set_speed(s),
            )
            btn.pack(side="left", padx=(0, 4))
            self._speed_buttons[speed] = btn
        self._set_speed("Normal")

        # Accuracy
        acc_col = tk.Frame(row, bg=_C["bg_card"])
        acc_col.pack(side="right")
        tk.Label(acc_col, text="Accuracy", font=(_FONT, 9, "bold"),
                 fg=_C["text_dim"], bg=_C["bg_card"]).pack(anchor="w", pady=(0, 4))
        acc_inner = tk.Frame(acc_col, bg=_C["bg_card"])
        acc_inner.pack(anchor="w")
        self.accuracy_var = tk.IntVar(value=int(config.TARGET_ACCURACY * 100))
        self.accuracy_slider = tk.Scale(
            acc_inner, from_=70, to=100, orient="horizontal",
            variable=self.accuracy_var, bg=_C["bg_card"], fg=_C["cyan"],
            troughcolor=_C["border"], highlightthickness=0, length=130,
            font=(_FONT, 9), activebackground=_C["cyan"], sliderrelief="raised",
            showvalue=False, bd=0, sliderlength=18,
        )
        self.accuracy_slider.pack(side="left")
        self._acc_label = tk.Label(
            acc_inner, text=f"{self.accuracy_var.get()}%",
            font=(_FONT, 12, "bold"), fg=_C["cyan"], bg=_C["bg_card"], width=4,
        )
        self._acc_label.pack(side="left", padx=(4, 0))
        self.accuracy_var.trace_add("write", self._on_accuracy_change)

        # ── Action buttons ────────────────────────────────────────────
        # Row 1: Launch Chrome + Start Solving
        btn_row1 = tk.Frame(page, bg=_C["bg"])
        btn_row1.pack(fill="x", padx=24, pady=(14, 0))

        self.chrome_btn = tk.Button(
            btn_row1, text="Launch Chrome", command=self._on_launch_chrome,
            bg=_C["bg_input"], fg=_C["cyan"], font=(_FONT, 11, "bold"),
            relief="flat", cursor="hand2", padx=16, pady=8,
            activebackground=_C["cyan"], activeforeground=_C["bg"],
            highlightthickness=1, highlightbackground=_C["cyan"],
        )
        self.chrome_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.start_btn = tk.Button(
            btn_row1, text="Start Solving", command=self._on_start,
            bg=_C["green"], fg=_C["bg"], font=(_FONT, 11, "bold"),
            relief="flat", cursor="hand2", padx=20, pady=8,
            activebackground="#4a9a6c", activeforeground=_C["bg"],
        )
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Row 2: Pause + Stop
        btn_row2 = tk.Frame(page, bg=_C["bg"])
        btn_row2.pack(fill="x", padx=24, pady=(6, 0))

        self.pause_btn = tk.Button(
            btn_row2, text="Pause", command=self._on_pause,
            bg=_C["yellow"], fg=_C["bg"], font=(_FONT, 11, "bold"),
            relief="flat", cursor="hand2", padx=14, pady=8, state="disabled",
            activebackground="#aa9a4a", activeforeground=_C["bg"],
        )
        self.pause_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.stop_btn = tk.Button(
            btn_row2, text="Stop", command=self._on_stop,
            bg=_C["red"], fg="#cccccc", font=(_FONT, 11, "bold"),
            relief="flat", cursor="hand2", padx=14, pady=8, state="disabled",
            activebackground="#9a4a55", activeforeground="#cccccc",
        )
        self.stop_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # ── Stats bar ─────────────────────────────────────────────────
        stats_frame = tk.Frame(page, bg=_C["bg"])
        stats_frame.pack(fill="x", padx=24, pady=(14, 0))

        self._stat_questions = self._stat_card(stats_frame, "Questions", "0 / ?")
        self._stat_questions.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._stat_correct = self._stat_card(stats_frame, "Correct", "0 / 0")
        self._stat_correct.pack(side="left", fill="x", expand=True, padx=(4, 4))
        self._stat_accuracy = self._stat_card(stats_frame, "Rate", "--")
        self._stat_accuracy.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # ── Live log ──────────────────────────────────────────────────
        log_header = tk.Frame(page, bg=_C["bg"])
        log_header.pack(fill="x", padx=24, pady=(14, 4))
        tk.Label(log_header, text="LIVE LOG", font=(_FONT, 9, "bold"),
                 fg=_C["text_dim"], bg=_C["bg"]).pack(side="left")

        log_border = tk.Frame(page, bg=_C["border"], highlightthickness=0)
        log_border.pack(fill="both", padx=24, pady=(0, 0), expand=True)

        self.log_text = tk.Text(
            log_border, height=10, bg=_C["log_bg"], fg=_C["text_dim"],
            insertbackground=_C["cyan"], font=(_FONT_MONO, 10),
            relief="flat", state="disabled", wrap="word",
            padx=12, pady=8, spacing1=2, spacing3=2,
            selectbackground=_C["cyan"], selectforeground=_C["bg"],
            highlightthickness=0, borderwidth=0,
        )
        self.log_text.pack(fill="both", expand=True, padx=1, pady=1)

        self.log_text.tag_configure("info", foreground=_C["text_dim"])
        self.log_text.tag_configure("success", foreground=_C["green"])
        self.log_text.tag_configure("error", foreground=_C["red"])
        self.log_text.tag_configure("warn", foreground=_C["yellow"])
        self.log_text.tag_configure("accent", foreground=_C["cyan"])
        self.log_text.tag_configure("timestamp", foreground="#3a3a50")

        # ── Bottom status ─────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(
            page, textvariable=self.status_var,
            fg=_C["text_dim"], bg=_C["bg"], font=(_FONT, 9),
            anchor="w", padx=26, pady=6,
        ).pack(fill="x", side="bottom")

    # ==================================================================
    # HELPERS
    # ==================================================================
    def _setting_row(self, parent, label):
        tk.Label(parent, text=label, font=(_FONT, 9, "bold"),
                 fg=_C["text_dim"], bg=_C["bg_card"]).pack(anchor="w", padx=16, pady=(6, 3))

    def _stat_card(self, parent, title, value):
        frame = tk.Frame(parent, bg=_C["bg_card"], highlightbackground=_C["border"],
                         highlightthickness=1)
        tk.Label(frame, text=title.upper(), font=(_FONT, 8, "bold"),
                 fg=_C["text_dim"], bg=_C["bg_card"]).pack(pady=(8, 0))
        val_label = tk.Label(frame, text=value, font=(_FONT, 16, "bold"),
                             fg=_C["text"], bg=_C["bg_card"])
        val_label.pack(pady=(0, 8))
        frame._val_label = val_label
        return frame

    def _set_speed(self, speed):
        self.speed_var.set(speed)
        for name, btn in self._speed_buttons.items():
            if name == speed:
                btn.config(bg=_C["cyan"], fg=_C["bg"])
            else:
                btn.config(bg=_C["bg_input"], fg=_C["text_dim"])

    def _on_accuracy_change(self, *_args):
        self._acc_label.config(text=f"{self.accuracy_var.get()}%")

    def _on_model_changed(self, event=None):
        """Handle model selection change - save preference to server."""
        if not hasattr(self, 'model_var') or not hasattr(self, '_validated_key'):
            return

        selected_display = self.model_var.get()

        # Reverse lookup to get model ID from display name
        model_id = None
        for mid in self._allowed_models:
            if self._model_names.get(mid, mid) == selected_display:
                model_id = mid
                break

        if not model_id or model_id not in self._allowed_models:
            return

        # Save preference to server
        def _save_preference():
            try:
                resp = requests.post(
                    f"{config.SERVER_URL}/api/model/preference",
                    json={
                        "access_key": self._validated_key,
                        "model": model_id
                    },
                    timeout=10
                )

                if resp.status_code == 200:
                    self._preferred_model = model_id
                    self.root.after(0, lambda: self.log(f"AI model changed to {selected_display}"))
                else:
                    error_data = resp.json()
                    self.root.after(0, lambda: self.log(f"Failed to save model preference: {error_data.get('error', 'Unknown error')}"))

            except Exception as e:
                self.root.after(0, lambda: self.log(f"Error saving model preference: {e}"))

        threading.Thread(target=_save_preference, daemon=True).start()

    def _save_access_key(self, key):
        env_path = os.path.join(config._get_app_dir(), ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if not line.startswith("ACCESS_KEY="):
                        lines.append(line)
        lines.append(f"ACCESS_KEY={key}\n")
        with open(env_path, "w") as f:
            f.writelines(lines)

    # ==================================================================
    # LOGGING
    # ==================================================================
    def log(self, message, tag="info"):
        self.root.after(0, self._append_log, message, tag)

    def _append_log(self, message, tag="info"):
        self.log_text.config(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"{ts}  ", "timestamp")
        if tag == "info":
            msg_lower = message.lower()
            if "error" in msg_lower or "fail" in msg_lower:
                tag = "error"
            elif "correct" in msg_lower or "success" in msg_lower or "started" in msg_lower:
                tag = "success"
            elif "warn" in msg_lower or "skip" in msg_lower or "miss" in msg_lower:
                tag = "warn"
            elif "question" in msg_lower or "solving" in msg_lower or "answer" in msg_lower:
                tag = "accent"
        self.log_text.insert("end", message + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ==================================================================
    # STATUS UPDATES
    # ==================================================================
    def update_status(self, question_num=None, correct=None, total=None):
        if question_num is not None:
            self.question_count = question_num
        if correct is not None:
            self.correct_count = correct
        total_q = total if total is not None else "?"

        def _update():
            self._stat_questions._val_label.config(text=f"{self.question_count} / {total_q}")
            self._stat_correct._val_label.config(text=f"{self.correct_count} / {self.question_count}")
            if self.question_count > 0:
                rate = int(round(self.correct_count / self.question_count * 100))
                self._stat_accuracy._val_label.config(text=f"{rate}%")
                if rate >= 90:
                    self._stat_accuracy._val_label.config(fg=_C["green"])
                elif rate >= 75:
                    self._stat_accuracy._val_label.config(fg=_C["yellow"])
                else:
                    self._stat_accuracy._val_label.config(fg=_C["red"])
            self.status_var.set(
                f"Questions: {self.question_count}/{total_q}  |  "
                f"Correct: {self.correct_count}/{self.question_count}"
            )
        self.root.after(0, _update)

    # ==================================================================
    # SETTINGS GETTER
    # ==================================================================
    def get_settings(self):
        speed = self.speed_var.get()
        min_d, max_d = config.SPEED_PRESETS.get(speed, (2.0, 5.0))

        # Get current model selection
        if hasattr(self, 'model_var'):
            # Reverse lookup from display name to model ID
            display_name = self.model_var.get()
            model_id = self._preferred_model  # Default to preferred
            for mid in self._allowed_models:
                if self._model_names.get(mid, mid) == display_name:
                    model_id = mid
                    break
        else:
            # Fallback if no model selector (shouldn't happen after login)
            model_id = self._preferred_model if hasattr(self, '_preferred_model') else "gpt-4o-mini"

        return {
            "access_key": self.access_key_var.get(),
            "speed": speed,
            "min_delay": min_d,
            "max_delay": max_d,
            "accuracy": self.accuracy_var.get() / 100.0,
            "model": model_id,
        }

    # ==================================================================
    # BUTTON HANDLERS
    # ==================================================================
    def _on_logout(self):
        if self.is_running:
            self._on_stop()
        self._validated_key = None
        self._login_key_var.set("")
        self._login_status.config(text="")
        self._show_login()

    def _on_launch_chrome(self):
        self.log("Launching Chrome with debug mode...")
        try:
            browser.launch_chrome()
            self.log("Chrome launched! Navigate to your SmartBook assignment.", "success")
        except Exception as e:
            self.log(f"ERROR launching Chrome: {e}", "error")

    def _on_start(self):
        settings = self.get_settings()
        self.is_running = True
        self.is_paused = False
        self.question_count = 0
        self.correct_count = 0

        self.start_btn.config(state="disabled", bg=_C["bg_input"], fg=_C["text_dim"])
        self.pause_btn.config(state="normal")
        self.stop_btn.config(state="normal")

        self._stat_questions._val_label.config(text="0 / ?")
        self._stat_correct._val_label.config(text="0 / 0")
        self._stat_accuracy._val_label.config(text="--", fg=_C["text"])

        self.log("Solver started", "success")
        if self.on_start:
            thread = threading.Thread(target=self.on_start, args=(settings,), daemon=True)
            thread.start()

    def _on_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.config(text="Resume", bg=_C["green"], fg=_C["bg"])
            self.log("Paused. Click Resume to continue.", "warn")
        else:
            self.pause_btn.config(text="Pause", bg=_C["yellow"], fg=_C["bg"])
            self.log("Resumed.", "success")
        if self.on_pause:
            self.on_pause(self.is_paused)

    def _on_stop(self):
        self.is_running = False
        self.is_paused = False
        self.start_btn.config(state="normal", bg=_C["green"], fg=_C["bg"])
        self.pause_btn.config(state="disabled", text="Pause", bg=_C["yellow"], fg=_C["bg"])
        self.stop_btn.config(state="disabled")
        self.log("Stopped.", "warn")
        if self.on_stop:
            self.on_stop()

    def run(self):
        self.root.mainloop()
