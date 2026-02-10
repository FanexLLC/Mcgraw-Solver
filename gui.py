import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import os
import config


class SolverGUI:
    def __init__(self, on_start=None, on_pause=None, on_stop=None):
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_stop = on_stop

        self.is_running = False
        self.is_paused = False
        self.question_count = 0
        self.correct_count = 0

        self.root = tk.Tk()
        self.root.title("SmartBook Solver")
        self.root.geometry("520x600")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Title
        title = tk.Label(
            self.root, text="SmartBook Solver",
            font=("Segoe UI", 18, "bold"), fg="#cdd6f4", bg="#1e1e2e"
        )
        title.pack(pady=(15, 10))

        # Settings frame
        settings_frame = tk.Frame(self.root, bg="#313244", bd=1, relief="solid")
        settings_frame.pack(fill="x", padx=20, pady=5)

        # API Key
        api_frame = tk.Frame(settings_frame, bg="#313244")
        api_frame.pack(fill="x", padx=15, pady=(10, 5))
        tk.Label(api_frame, text="API Key:", fg="#cdd6f4", bg="#313244",
                 font=("Segoe UI", 10)).pack(side="left")
        self.api_key_var = tk.StringVar(value=config.OPENAI_API_KEY)
        self.api_key_entry = tk.Entry(
            api_frame, textvariable=self.api_key_var, show="*",
            width=35, bg="#45475a", fg="#cdd6f4", insertbackground="#cdd6f4",
            relief="flat", font=("Segoe UI", 10)
        )
        self.api_key_entry.pack(side="left", padx=(10, 0))

        # Speed
        speed_frame = tk.Frame(settings_frame, bg="#313244")
        speed_frame.pack(fill="x", padx=15, pady=5)
        tk.Label(speed_frame, text="Speed:", fg="#cdd6f4", bg="#313244",
                 font=("Segoe UI", 10)).pack(side="left")
        self.speed_var = tk.StringVar(value="Normal")
        for speed in ["Slow", "Normal", "Fast"]:
            rb = tk.Radiobutton(
                speed_frame, text=speed, variable=self.speed_var, value=speed,
                fg="#cdd6f4", bg="#313244", selectcolor="#45475a",
                activebackground="#313244", activeforeground="#cdd6f4",
                font=("Segoe UI", 10)
            )
            rb.pack(side="left", padx=8)

        # Accuracy
        acc_frame = tk.Frame(settings_frame, bg="#313244")
        acc_frame.pack(fill="x", padx=15, pady=5)
        tk.Label(acc_frame, text="Accuracy:", fg="#cdd6f4", bg="#313244",
                 font=("Segoe UI", 10)).pack(side="left")
        self.accuracy_var = tk.IntVar(value=int(config.TARGET_ACCURACY * 100))
        self.accuracy_slider = tk.Scale(
            acc_frame, from_=70, to=100, orient="horizontal",
            variable=self.accuracy_var, bg="#313244", fg="#cdd6f4",
            troughcolor="#45475a", highlightthickness=0, length=200,
            font=("Segoe UI", 9)
        )
        self.accuracy_slider.pack(side="left", padx=(10, 0))
        tk.Label(acc_frame, text="%", fg="#cdd6f4", bg="#313244",
                 font=("Segoe UI", 10)).pack(side="left")

        # Chrome Profile
        profile_frame = tk.Frame(settings_frame, bg="#313244")
        profile_frame.pack(fill="x", padx=15, pady=5)
        tk.Label(profile_frame, text="Chrome Profile:", fg="#cdd6f4", bg="#313244",
                 font=("Segoe UI", 10)).pack(side="left")
        self.profile_var = tk.StringVar(value=config.CHROME_PROFILE)
        profile_combo = ttk.Combobox(
            profile_frame, textvariable=self.profile_var,
            values=["Default", "Profile 1", "Profile 2", "Profile 3"],
            state="readonly", width=15
        )
        profile_combo.pack(side="left", padx=(10, 0))

        # Model
        model_frame = tk.Frame(settings_frame, bg="#313244")
        model_frame.pack(fill="x", padx=15, pady=(5, 10))
        tk.Label(model_frame, text="Model:", fg="#cdd6f4", bg="#313244",
                 font=("Segoe UI", 10)).pack(side="left")
        self.model_var = tk.StringVar(value=config.GPT_MODEL)
        model_combo = ttk.Combobox(
            model_frame, textvariable=self.model_var,
            values=["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
            state="readonly", width=15
        )
        model_combo.pack(side="left", padx=(10, 0))

        # Buttons frame
        btn_frame = tk.Frame(self.root, bg="#1e1e2e")
        btn_frame.pack(pady=10)

        self.start_btn = tk.Button(
            btn_frame, text="Start", command=self._on_start,
            bg="#a6e3a1", fg="#1e1e2e", font=("Segoe UI", 11, "bold"),
            width=10, relief="flat", cursor="hand2"
        )
        self.start_btn.pack(side="left", padx=5)

        self.pause_btn = tk.Button(
            btn_frame, text="Pause", command=self._on_pause,
            bg="#f9e2af", fg="#1e1e2e", font=("Segoe UI", 11, "bold"),
            width=10, relief="flat", cursor="hand2", state="disabled"
        )
        self.pause_btn.pack(side="left", padx=5)

        self.stop_btn = tk.Button(
            btn_frame, text="Stop", command=self._on_stop,
            bg="#f38ba8", fg="#1e1e2e", font=("Segoe UI", 11, "bold"),
            width=10, relief="flat", cursor="hand2", state="disabled"
        )
        self.stop_btn.pack(side="left", padx=5)

        # Status log
        log_label = tk.Label(
            self.root, text="Status Log:", fg="#cdd6f4", bg="#1e1e2e",
            font=("Segoe UI", 10), anchor="w"
        )
        log_label.pack(fill="x", padx=20, pady=(5, 0))

        self.log_text = scrolledtext.ScrolledText(
            self.root, height=12, bg="#181825", fg="#cdd6f4",
            insertbackground="#cdd6f4", font=("Consolas", 10),
            relief="flat", state="disabled", wrap="word"
        )
        self.log_text.pack(fill="both", padx=20, pady=5, expand=True)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(
            self.root, textvariable=self.status_var,
            fg="#a6adc8", bg="#11111b", font=("Segoe UI", 9),
            anchor="w", padx=10
        )
        status_bar.pack(fill="x", side="bottom")

    def log(self, message):
        """Add a message to the status log (thread-safe)."""
        self.root.after(0, self._append_log, message)

    def _append_log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def update_status(self, question_num=None, correct=None, total=None):
        """Update the status bar counters."""
        if question_num is not None:
            self.question_count = question_num
        if correct is not None:
            self.correct_count = correct
        if total is not None:
            total_q = total
        else:
            total_q = "?"
        self.root.after(0, lambda: self.status_var.set(
            f"Questions: {self.question_count}/{total_q}  |  "
            f"Correct: {self.correct_count}/{self.question_count}"
        ))

    def get_settings(self):
        """Return current settings from the GUI."""
        speed = self.speed_var.get()
        min_d, max_d = config.SPEED_PRESETS.get(speed, (2.0, 5.0))
        return {
            "api_key": self.api_key_var.get(),
            "speed": speed,
            "min_delay": min_d,
            "max_delay": max_d,
            "accuracy": self.accuracy_var.get() / 100.0,
            "model": self.model_var.get(),
            "chrome_profile": self.profile_var.get(),
        }

    def _save_api_key(self, key):
        """Save API key to .env file."""
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        with open(env_path, "w") as f:
            f.write(f"OPENAI_API_KEY={key}\n")

    def _on_start(self):
        settings = self.get_settings()
        if not settings["api_key"] or settings["api_key"] == "your-key-here":
            self.log("ERROR: Please enter your OpenAI API key first!")
            return

        self._save_api_key(settings["api_key"])
        self.is_running = True
        self.is_paused = False
        self.question_count = 0
        self.correct_count = 0

        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self.stop_btn.config(state="normal")

        self.log("Starting solver...")
        if self.on_start:
            thread = threading.Thread(target=self.on_start, args=(settings,), daemon=True)
            thread.start()

    def _on_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.config(text="Resume")
            self.log("Paused. Click Resume to continue.")
        else:
            self.pause_btn.config(text="Pause")
            self.log("Resumed.")
        if self.on_pause:
            self.on_pause(self.is_paused)

    def _on_stop(self):
        self.is_running = False
        self.is_paused = False
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="Pause")
        self.stop_btn.config(state="disabled")
        self.log("Stopped.")
        if self.on_stop:
            self.on_stop()

    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()
