import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "pipeline_config.json")
DISCOVER_SCRIPT = os.path.join(HERE, "discover.py")

BLUE = "#2E6FDB"
GREEN = "#2FA84F"
DARK = "#1F2A37"
GRAY = "#6B7280"
BG = "#FFFFFF"


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def newest_xlsx_in(folder, after_mtime):
    """Return the most recently modified .xlsx file created/touched after after_mtime, or None."""
    best_path, best_mtime = None, after_mtime
    for name in os.listdir(folder):
        if name.lower().endswith((".xlsx", ".xlsm")):
            path = os.path.join(folder, name)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime > best_mtime:
                best_mtime, best_path = mtime, path
    return best_path


class Spinner(tk.Canvas):
    """A simple rotating blue arc, drawn on a Canvas."""
    def __init__(self, master, size=64, **kw):
        super().__init__(master, width=size, height=size, bg=BG, highlightthickness=0, **kw)
        self.size = size
        self.angle = 0
        self._running = False
        self._job = None

    def start(self):
        self._running = True
        self._tick()

    def stop(self):
        self._running = False
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self.delete("all")

    def _tick(self):
        if not self._running:
            return
        self.delete("all")
        pad = 6
        self.create_arc(pad, pad, self.size - pad, self.size - pad,
                         start=self.angle, extent=100,
                         style="arc", outline=BLUE, width=6)
        self.create_arc(pad, pad, self.size - pad, self.size - pad,
                         start=self.angle + 180, extent=100,
                         style="arc", outline="#C7D8F7", width=6)
        self.angle = (self.angle - 10) % 360
        self._job = self.after(40, self._tick)


class CheckMark(tk.Canvas):
    """A simple green circle + checkmark, drawn on a Canvas."""
    def __init__(self, master, size=64, **kw):
        super().__init__(master, width=size, height=size, bg=BG, highlightthickness=0, **kw)
        pad = 4
        self.create_oval(pad, pad, size - pad, size - pad, outline=GREEN, width=4)
        self.create_line(size * 0.28, size * 0.52, size * 0.44, size * 0.70,
                          fill=GREEN, width=5, capstyle="round", joinstyle="round")
        self.create_line(size * 0.44, size * 0.70, size * 0.75, size * 0.30,
                          fill=GREEN, width=5, capstyle="round", joinstyle="round")


class App:
    def __init__(self, root):
        self.root = root
        root.title("LSMS Impact Measure Analysis")
        root.geometry("460x420")
        root.configure(bg=BG)
        root.resizable(False, False)

        self.cfg = load_config()
        self.output_path = None
        self.log_lines = []

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", pady=(28, 4))
        tk.Label(header, text="LSMS Impact Measure Analysis", font=("Segoe UI", 16, "bold"),
                 bg=BG, fg=DARK).pack()
        tk.Label(header, text="Automated research paper discovery & tracking", font=("Segoe UI", 9),
                 bg=BG, fg=GRAY).pack(pady=(2, 0))

        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True, pady=10)

        self.status_var = tk.StringVar(value="")
        tk.Label(root, textvariable=self.status_var, font=("Segoe UI", 8), bg=BG, fg=GRAY,
                 wraplength=420, justify="center").pack(side="bottom", pady=8)

        self.show_idle()

    def _clear_body(self):
        for w in self.body.winfo_children():
            w.destroy()

    def show_idle(self):
        self._clear_body()
        self.status_var.set("")

        frame = tk.Frame(self.body, bg=BG)
        frame.pack(pady=10)

        tk.Label(frame, text="OpenAlex API key", font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=DARK).pack(anchor="w")
        self.key_var = tk.StringVar(value=self.cfg.get("api_key", ""))
        tk.Entry(frame, textvariable=self.key_var, width=40, show="*",
                 font=("Segoe UI", 10)).pack(pady=(4, 2))
        tk.Label(frame, text="Get a free key at openalex.org/settings/api",
                 font=("Segoe UI", 8), bg=BG, fg=GRAY).pack(anchor="w")

        tk.Label(self.body, text="", bg=BG).pack(pady=2)

        # Update vs full. Default to update: it searches just as widely, it only
        # avoids paying again to re-check papers already scored.
        mode = tk.Frame(self.body, bg=BG)
        mode.pack(pady=(0, 2))
        self.update_var = tk.BooleanVar(value=bool(self.cfg.get("update_only", True)))
        tk.Checkbutton(mode, variable=self.update_var, bg=BG, activebackground=BG,
                       text="Update the existing results (recommended)",
                       font=("Segoe UI", 9, "bold"), fg=DARK, selectcolor=BG,
                       command=self._mode_changed).pack(anchor="w")
        self.mode_hint = tk.Label(mode, text="", font=("Segoe UI", 8), bg=BG, fg=GRAY,
                                  wraplength=360, justify="left")
        self.mode_hint.pack(anchor="w", padx=(22, 0))
        self._mode_changed()

        self.run_btn = tk.Button(self.body, text="Run analysis", font=("Segoe UI", 11, "bold"),
                                  bg=BLUE, fg="white", activebackground="#255BB5",
                                  activeforeground="white", relief="flat", padx=18, pady=8,
                                  command=self.start_run)
        self.run_btn.pack(pady=8)

    def _mode_changed(self):
        if self.update_var.get():
            self.mode_hint.config(
                text="Finds new papers and adds them to your latest results file. "
                     "New rows are highlighted. Faster, and costs a few cents.")
        else:
            self.mode_hint.config(
                text="Rebuilds and re-checks every paper from scratch. Takes about "
                     "5 minutes and costs roughly $1.60. Worth doing occasionally, "
                     "or after the matching rules change.")

    def show_running(self, update_only=True):
        self._clear_body()
        frame = tk.Frame(self.body, bg=BG)
        frame.pack(expand=True)

        self.spinner = Spinner(frame, size=72)
        self.spinner.pack(pady=(20, 14))
        self.spinner.start()

        tk.Label(frame, text="Updating results\u2026" if update_only else "Running full analysis\u2026",
                 font=("Segoe UI", 12, "bold"), bg=BG, fg=DARK).pack()
        tk.Label(frame,
                 text=("Searching OpenAlex for papers not already in your results."
                       if update_only else
                       "Searching OpenAlex and rebuilding the workbook from scratch. "
                       "Usually about 5 minutes."),
                 font=("Segoe UI", 8), bg=BG, fg=GRAY, wraplength=380, justify="center").pack(pady=(4, 0))

        self.status_var.set("Do not close this window while the analysis is running.")

    def show_done(self):
        self._clear_body()
        frame = tk.Frame(self.body, bg=BG)
        frame.pack(expand=True)

        CheckMark(frame, size=72).pack(pady=(16, 10))
        tk.Label(frame, text="Ready", font=("Segoe UI", 13, "bold"), bg=BG, fg=DARK).pack()

        fname = os.path.basename(self.output_path) if self.output_path else "the output workbook"
        tk.Label(frame, text=fname, font=("Segoe UI", 9), bg=BG, fg=GRAY,
                 wraplength=380, justify="center").pack(pady=(2, 14))

        tk.Button(frame, text="Open File", font=("Segoe UI", 11, "bold"),
                  bg=GREEN, fg="white", activebackground="#268A42", activeforeground="white",
                  relief="flat", padx=18, pady=8, command=self.open_output).pack(pady=(0, 8))

        tk.Button(frame, text="Run again", font=("Segoe UI", 9), bg=BG, fg=BLUE,
                  relief="flat", command=self.show_idle).pack()

        self.status_var.set("")

    def show_error(self, message):
        self._clear_body()
        frame = tk.Frame(self.body, bg=BG)
        frame.pack(expand=True)

        tk.Label(frame, text="\u26A0", font=("Segoe UI", 34), bg=BG, fg="#D9822B").pack(pady=(16, 6))
        tk.Label(frame, text="Something went wrong", font=("Segoe UI", 12, "bold"),
                 bg=BG, fg=DARK).pack()
        tk.Label(frame, text=message, font=("Segoe UI", 8), bg=BG, fg=GRAY,
                 wraplength=380, justify="center").pack(pady=(4, 14))

        tk.Button(frame, text="Try again", font=("Segoe UI", 10, "bold"),
                  bg=BLUE, fg="white", relief="flat", padx=16, pady=6,
                  command=self.show_idle).pack()

    def start_run(self):
        key = self.key_var.get().strip()
        if not key:
            messagebox.showerror("Missing API key",
                                  "Paste your free OpenAlex API key first "
                                  "(get one at openalex.org/settings/api).")
            return
        if not os.path.exists(DISCOVER_SCRIPT):
            messagebox.showerror("discover.py not found",
                                  f"Expected to find discover.py in:\n{HERE}\n\n"
                                  "Make sure this launcher sits in the same folder as discover.py.")
            return

        update_only = bool(self.update_var.get())
        save_config({"api_key": key, "update_only": update_only})
        self.show_running(update_only)

        cmd = [sys.executable, DISCOVER_SCRIPT, "--api-key", key]
        if update_only:
            cmd.append("--update")
        threading.Thread(target=self._run_subprocess, args=(cmd,), daemon=True).start()

    def _run_subprocess(self, cmd):
        start_time = time.time()
        self.log_lines = []
        try:
            # Create a copy of current environment variables and explicitly force UTF-8 modes
            custom_env = os.environ.copy()
            custom_env["PYTHONUTF8"] = "1"
            custom_env["PYTHONIOENCODING"] = "utf-8"

            # Added encoding="utf-8" and env=custom_env to handle the subprocess stream safely
            proc = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, 
                                     encoding="utf-8", env=custom_env, bufsize=1)
            for line in proc.stdout:
                self.log_lines.append(line.rstrip())
            proc.wait()

            if proc.returncode == 0:
                found = newest_xlsx_in(HERE, start_time)
                self.output_path = found
                self.root.after(0, self.show_done)
            else:
                tail = "\n".join(self.log_lines[-6:]) or "No output captured."
                self.root.after(0, lambda: self.show_error(
                    f"The pipeline exited with an error (code {proc.returncode}).\n\n{tail}"))
        except Exception as e:
            self.root.after(0, lambda: self.show_error(f"Failed to launch discover.py:\n{e}"))
        finally:
            if hasattr(self, "spinner"):
                self.root.after(0, self.spinner.stop)

    def open_output(self):
        if not self.output_path or not os.path.exists(self.output_path):
            messagebox.showwarning("File not found",
                                    "Couldn't locate the finished workbook automatically. "
                                    "Check this folder for the newest .xlsx file.")
            return
        try:
            if os.name == "nt":
                os.startfile(self.output_path)
            elif sys.platform == "darwin":
                subprocess.call(["open", self.output_path])
            else:
                subprocess.call(["xdg-open", self.output_path])
        except Exception as e:
            messagebox.showerror("Couldn't open file", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()