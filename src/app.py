"""Tkinter GUI for recording open windows/browser tabs and exporting a
restore script.

Window enumeration (``win32gui``/``psutil``) and especially UI Automation
browser-tab inspection can take anywhere from tens of milliseconds to a few
seconds per window. Running that work directly on Tkinter's event-handling
thread would freeze the whole UI for the duration of the scan, so
:meth:`SessionRecorderApp.record_windows` instead dispatches it to a
background thread.

Tkinter widgets must only ever be touched from the main thread, so the
worker thread never calls into Tk directly: it posts its result onto a
``queue.Queue``, which the main thread drains via a periodic ``after()``
poll. This avoids relying on ``root.after()`` itself being safe to call
from another thread, which is not guaranteed across all Tcl/Tk builds.
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Union

# Add src to python path for package resolution
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from browser_inspector import extract_browser_url, uia_thread_session
from exporter import SessionItem, generate_batch_file
from window_scanner import scan_open_windows

logger = logging.getLogger(__name__)

WINDOW_TITLE = "Workspace Session Recorder"
WINDOW_GEOMETRY = "700x520"
WINDOW_MIN_SIZE = (580, 400)

# How often (ms) the main thread polls for a finished background scan.
SCAN_POLL_INTERVAL_MS = 100

# Messages placed on the scan result queue by the worker thread.
ScanResult = Union[List[SessionItem], Exception]

CHECKBOX_CHECKED = "☑"
CHECKBOX_UNCHECKED = "☐"

COLUMNS = ("include", "type", "name", "target")


class SessionRecorderApp:
    """Main application window: record open windows and export a .bat file."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_GEOMETRY)
        self.root.minsize(*WINDOW_MIN_SIZE)

        self.recorded_items: List[SessionItem] = []
        self._scanning = False
        self._scan_queue: "queue.Queue[ScanResult]" = queue.Queue()

        self.btn_record: ttk.Button
        self.tree: ttk.Treeview
        self.status_var: tk.StringVar

        self.create_widgets()

    def create_widgets(self) -> None:
        # Controls Frame
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(fill=tk.X)

        self.btn_record = ttk.Button(
            control_frame, text="🔍 Record Current Windows", command=self.record_windows
        )
        self.btn_record.pack(side=tk.LEFT, padx=5)

        btn_select_all = ttk.Button(control_frame, text="Select All", command=self.select_all)
        btn_select_all.pack(side=tk.LEFT, padx=5)

        btn_deselect_all = ttk.Button(control_frame, text="Deselect All", command=self.deselect_all)
        btn_deselect_all.pack(side=tk.LEFT, padx=5)

        # Treeview / Data Grid Frame
        list_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(list_frame, columns=COLUMNS, show="headings", selectmode="browse")

        self.tree.heading("include", text="Include?")
        self.tree.heading("type", text="Type")
        self.tree.heading("name", text="Window Title / App Name")
        self.tree.heading("target", text="Executable Path / URL")

        self.tree.column("include", width=70, anchor="center")
        self.tree.column("type", width=90, anchor="center")
        self.tree.column("name", width=230, anchor="w")
        self.tree.column("target", width=290, anchor="w")

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Button-1>", self.on_tree_click)

        # Bottom Frame
        bottom_frame = ttk.Frame(self.root, padding=10)
        bottom_frame.pack(fill=tk.X)

        btn_export = ttk.Button(bottom_frame, text="💾 Export to .BAT File", command=self.export_batch)
        btn_export.pack(side=tk.RIGHT, padx=5)

        self.status_var = tk.StringVar(value="Click 'Record Current Windows' to scan active apps.")
        status_label = ttk.Label(bottom_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w")
        status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    @staticmethod
    def _row_values(item: SessionItem) -> tuple:
        """Builds the Treeview values tuple for a single recorded item."""
        check_str = CHECKBOX_CHECKED if item["include"] else CHECKBOX_UNCHECKED
        return (check_str, item["type"], item["name"], item["target"])

    def record_windows(self) -> None:
        """Kicks off a background scan of open windows and browser tabs.

        The actual Win32/psutil/UI-Automation work runs on a daemon thread
        so the GUI stays responsive. The worker never touches Tkinter
        directly; it posts its outcome onto ``self._scan_queue``, which the
        main thread drains via :meth:`_poll_scan_queue`.
        """
        if self._scanning:
            return

        self._scanning = True
        self.btn_record.state(["disabled"])
        self.tree.delete(*self.tree.get_children())
        self.recorded_items.clear()
        self.status_var.set("Scanning active windows... this may take a few seconds.")

        ignore_hwnd = self.root.winfo_id()
        thread = threading.Thread(target=self._scan_worker, args=(ignore_hwnd,), daemon=True)
        thread.start()
        self.root.after(SCAN_POLL_INTERVAL_MS, self._poll_scan_queue)

    def _scan_worker(self, ignore_hwnd: int) -> None:
        """Background-thread body: never touches Tkinter widgets directly."""
        try:
            raw_windows = scan_open_windows(ignore_hwnd=ignore_hwnd)

            items: List[SessionItem] = []
            seen_targets = set()

            with uia_thread_session():
                for win in raw_windows:
                    url = extract_browser_url(win["hwnd"], win["proc_name"])

                    if url:
                        item_type, target = "Browser URL", url
                    else:
                        item_type, target = "Application", win["exe_path"]

                    # Deduplicate by target destination.
                    if target in seen_targets:
                        continue
                    seen_targets.add(target)

                    items.append({
                        "include": True,
                        "type": item_type,
                        "name": win["title"],
                        "target": target,
                    })
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            logger.exception("Window scan failed")
            self._scan_queue.put(exc)
            return

        self._scan_queue.put(items)

    def _poll_scan_queue(self) -> None:
        """Main-thread poller: drains the scan result queue when ready."""
        try:
            result = self._scan_queue.get_nowait()
        except queue.Empty:
            if self._scanning:
                self.root.after(SCAN_POLL_INTERVAL_MS, self._poll_scan_queue)
            return

        if isinstance(result, Exception):
            self._on_scan_error(result)
        else:
            self._on_scan_complete(result)

    def _on_scan_complete(self, items: List[SessionItem]) -> None:
        """Main-thread callback: applies scan results to the Treeview."""
        self.recorded_items = items

        for idx, item in enumerate(self.recorded_items):
            self.tree.insert("", tk.END, iid=str(idx), values=self._row_values(item))

        self.status_var.set(f"Recorded {len(self.recorded_items)} active items.")
        self.btn_record.state(["!disabled"])
        self._scanning = False

    def _on_scan_error(self, exc: Exception) -> None:
        """Main-thread callback: reports a failed scan without crashing."""
        messagebox.showerror("Scan Failed", f"Could not scan open windows:\n{exc}")
        self.status_var.set("Scan failed. Click 'Record Current Windows' to try again.")
        self.btn_record.state(["!disabled"])
        self._scanning = False

    def on_tree_click(self, event: tk.Event) -> None:
        """Toggles the Include checkbox for the row under the cursor."""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell" or self.tree.identify_column(event.x) != "#1":
            return

        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        idx = int(item_id)
        self.recorded_items[idx]["include"] = not self.recorded_items[idx]["include"]
        self.tree.item(item_id, values=self._row_values(self.recorded_items[idx]))

    def select_all(self) -> None:
        for idx, item in enumerate(self.recorded_items):
            item["include"] = True
            self.tree.item(str(idx), values=self._row_values(item))

    def deselect_all(self) -> None:
        for idx, item in enumerate(self.recorded_items):
            item["include"] = False
            self.tree.item(str(idx), values=self._row_values(item))

    def export_batch(self) -> None:
        selected_items = [item for item in self.recorded_items if item["include"]]

        if not selected_items:
            messagebox.showwarning("No Selection", "Please select at least one application or URL to export.")
            return

        file_path: Optional[str] = filedialog.asksaveasfilename(
            defaultextension=".bat",
            filetypes=[("Batch File", "*.bat"), ("All Files", "*.*")],
            initialfile="RestoreSession.bat",
            title="Save Batch Script",
        )

        if not file_path:
            return

        try:
            generate_batch_file(file_path, selected_items)
            messagebox.showinfo("Success", f"Batch file generated successfully:\n{file_path}")
            self.status_var.set("Export complete.")
        except OSError as exc:
            logger.exception("Failed to write batch file")
            messagebox.showerror("Export Failed", f"An error occurred: {exc}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    root = tk.Tk()
    app = SessionRecorderApp(root)
    root.mainloop()
