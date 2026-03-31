"""
Lightweight tkinter chat window for the AlchemyAI relay.

Launch:
    .venv/bin/python3 chat_gui.py
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from llm_client import (
    MODEL_CATALOG,
    CompletionConfig,
    RelayClient,
    list_models,
)

# ── Theme ──────────────────────────────────────────────────────────────────
BG = "#1e1e2e"
BG_INPUT = "#2a2a3c"
FG = "#cdd6f4"
FG_DIM = "#6c7086"
FG_USER = "#89b4fa"
FG_BOT = "#a6e3a1"
FG_ERR = "#f38ba8"
FONT = ("Menlo", 13)
FONT_SMALL = ("Menlo", 11)


class ChatWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Relay Chat")
        self.root.configure(bg=BG)
        self.root.geometry("700x560")
        self.root.minsize(480, 340)

        self.client = RelayClient()
        self.history: list[dict[str, str]] = []
        self._streaming = False

        self._build_ui()
        self._bind_keys()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Top bar: model selector + clear button
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill=tk.X, padx=8, pady=(8, 0))

        tk.Label(top, text="Model", bg=BG, fg=FG_DIM, font=FONT_SMALL).pack(
            side=tk.LEFT, padx=(0, 4)
        )

        available = [m.id for m in list_models(chat_only=True)]
        if not available:
            available = [m.id for m in list_models()]

        self.model_var = tk.StringVar(value=available[0] if available else "")
        self.model_combo = ttk.Combobox(
            top,
            textvariable=self.model_var,
            values=available,
            state="readonly",
            width=30,
            font=FONT_SMALL,
        )
        self.model_combo.pack(side=tk.LEFT, padx=(0, 8))

        self.stream_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            top,
            text="Stream",
            variable=self.stream_var,
            bg=BG,
            fg=FG_DIM,
            selectcolor=BG_INPUT,
            activebackground=BG,
            activeforeground=FG,
            font=FONT_SMALL,
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            top,
            text="Clear",
            command=self._clear,
            bg=BG_INPUT,
            fg=FG_DIM,
            activebackground=BG,
            activeforeground=FG,
            font=FONT_SMALL,
            relief=tk.FLAT,
            cursor="hand2",
        ).pack(side=tk.RIGHT)

        # Chat display
        self.chat = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            bg=BG,
            fg=FG,
            insertbackground=FG,
            font=FONT,
            relief=tk.FLAT,
            borderwidth=0,
            padx=10,
            pady=8,
            state=tk.DISABLED,
        )
        self.chat.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.chat.tag_configure("user", foreground=FG_USER)
        self.chat.tag_configure("bot", foreground=FG_BOT)
        self.chat.tag_configure("err", foreground=FG_ERR)
        self.chat.tag_configure("dim", foreground=FG_DIM)

        # Input row
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.entry = tk.Text(
            bottom,
            height=2,
            bg=BG_INPUT,
            fg=FG,
            insertbackground=FG,
            font=FONT,
            relief=tk.FLAT,
            borderwidth=4,
            padx=6,
            pady=6,
            wrap=tk.WORD,
        )
        self.entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        self.entry.focus_set()

        self.send_btn = tk.Button(
            bottom,
            text="Send",
            command=self._on_send,
            bg="#89b4fa",
            fg=BG,
            activebackground="#74c7ec",
            activeforeground=BG,
            font=FONT_SMALL,
            relief=tk.FLAT,
            cursor="hand2",
            width=6,
        )
        self.send_btn.pack(side=tk.RIGHT, fill=tk.Y)

        # Status bar
        self.status_var = tk.StringVar(value=f"relay: {self.client.relay_url}")
        tk.Label(
            self.root,
            textvariable=self.status_var,
            bg=BG,
            fg=FG_DIM,
            font=("Menlo", 10),
            anchor=tk.W,
        ).pack(fill=tk.X, padx=10, pady=(0, 4))

    def _bind_keys(self) -> None:
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Shift-Return>", lambda e: None)  # allow newlines
        self.root.bind("<Command-k>", lambda e: self._clear())

    # ── Chat logic ─────────────────────────────────────────────────────────

    def _on_enter(self, event: tk.Event) -> str:
        if not self._streaming:
            self.root.after(1, self._on_send)
        return "break"  # suppress the newline from Enter key

    def _on_send(self) -> None:
        text = self.entry.get("1.0", tk.END).strip()
        if not text or self._streaming:
            return

        self.entry.delete("1.0", tk.END)
        self._append(f"You: {text}\n", "user")

        self.history.append({"role": "user", "content": text})
        self._streaming = True
        self.send_btn.configure(state=tk.DISABLED)
        self.status_var.set(f"⏳  {self.model_var.get()} …")

        thread = threading.Thread(target=self._run_completion, daemon=True)
        thread.start()

    def _run_completion(self) -> None:
        model = self.model_var.get()
        use_stream = self.stream_var.get()

        try:
            if use_stream:
                self.root.after(0, self._append, "Bot: ", "bot")
                full = []
                for chunk in self.client.stream(
                    messages=self.history, model=model
                ):
                    full.append(chunk)
                    self.root.after(0, self._append, chunk, "bot")
                reply = "".join(full)
                self.root.after(0, self._append, "\n", "bot")
            else:
                reply = self.client.complete(messages=self.history, model=model)
                self.root.after(0, self._append, f"Bot: {reply}\n", "bot")

            self.history.append({"role": "assistant", "content": reply})
            self.root.after(0, self.status_var.set, f"✓  {model}")
        except Exception as exc:
            err_msg = str(exc).split("\n")[0][:200]
            self.root.after(0, self._append, f"Error: {err_msg}\n", "err")
            self.root.after(0, self.status_var.set, f"✗  {model}")
        finally:
            self.root.after(0, self._done_streaming)

    def _done_streaming(self) -> None:
        self._streaming = False
        self.send_btn.configure(state=tk.NORMAL)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _append(self, text: str, tag: str = "") -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, text, tag)
        self.chat.see(tk.END)
        self.chat.configure(state=tk.DISABLED)

    def _clear(self) -> None:
        self.history.clear()
        self.chat.configure(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.configure(state=tk.DISABLED)
        self.status_var.set(f"relay: {self.client.relay_url}")

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    ChatWindow().run()
