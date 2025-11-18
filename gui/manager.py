"""Interfaccia grafica Tkinter"""

import threading
import tkinter as tk
from tkinter import ttk
from typing import Dict
from typing import cast
from concurrent.futures import ThreadPoolExecutor

from core.mongo_sync import MongoSyncManager
from core.window_detector import WindowDetector
from config.settings import Config


class GUIManager:
    """Gestisce l'interfaccia grafica Tkinter"""

    def __init__(self, config: Config, mongo_manager: MongoSyncManager):
        self.config = config
        self.mongo_manager = mongo_manager
        self.indicators = {}
        self.executor = ThreadPoolExecutor(max_workers=2)
        self._last_timer = {}
        self.root = None
        self.root = tk.Tk()
        self.root.withdraw()

    def create_window(self):
        """Crea la finestra principale"""
        self.root = tk.Tk()
        self.root.title("Livelli di attenzione")
        self.root.geometry("800x640")
        self.root.configure(bg="white")
        self.root.deiconify()

        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=1)
        self.root.columnconfigure(2, weight=1)

        # === DEVICE ID ===
        self.frame_title = tk.Frame(self.root, bg="white")
        self.frame_title.grid(row=0, column=0, columnspan=3, padx=10, pady=10)

        tk.Label(
            self.frame_title,
            text="DEVICE ID: ",
            bg="white",
            fg="black",
            font=("Arial", 18, "bold"),
        ).pack(side="left")

        tk.Label(
            self.frame_title,
            text=self.config.DEVICE_ID,
            bg="white",
            fg="blue",
            font=("Arial", 18, "bold"),
        ).pack(side="left")

        # --- Bottone copia ---
        tk.Button(
            self.frame_title,
            text="📋",
            bg="white",
            relief="flat",
            font=("Arial", 16),
            command=lambda w=self.frame_title: self.copy_to_clipboard(
                w, self.config.DEVICE_ID
            ),
        ).pack(side="left", padx=10)

        # Carica applicazioni
        self._load_apps(1)

        # Avvia aggiornamento indicatori
        self._update_active_indicator()

        return self.root

    def show_toast(self, message, duration=2000):
        # Se esiste già un toast vecchio lo rimuoviamo
        if hasattr(self, "_toast") and self._toast:
            self._toast.destroy()

        # Creiamo il toast dentro lo stesso frame del pulsante
        self._toast = tk.Label(
            self.frame_title,  # <-- QUI CAMBIATO
            text=message,
            bg="white",
            fg="green",
            font=("Arial", 12, "bold"),
        )

        # Mettilo alla destra del pulsante
        self._toast.pack(side="left", padx=10)

        # Auto-hide
        cast(tk.Tk, self.root).after(duration, lambda: self._toast.destroy())

    def copy_to_clipboard(self, widget, text):
        widget.clipboard_clear()
        widget.clipboard_append(text)
        widget.update()
        self.show_toast("Device ID copiato negli appunti")

    def _load_apps(self, start_row):
        apps = self.mongo_manager.get_process_windows()
        for i, app in enumerate(apps, start=start_row):
            if app["process"] not in self.config.PROCESS_BLACKLIST:
                self.add_process_row(i, app)

    def add_process_row(self, row: int, app: Dict):
        """Aggiunge una riga per un processo"""
        if app["_id"] in self.indicators:
            return  # già presente, esci

        level = app.get("level", 5)

        # Indicatore stato
        indicator = tk.Label(
            self.root, text="●", fg="gray", bg="white", font=("Arial", 12)
        )
        indicator.grid(row=row, column=0, padx=5, pady=3, sticky="w")

        # Nome applicazione
        label = tk.Label(
            self.root,
            text=f"{app['process']} ({app['window_title']})",
            bg="white",
            fg="black",
            font=("Arial", 10),
        )
        label.grid(row=row, column=1, sticky="w", padx=5, pady=3)

        # Slider livello
        scale = ttk.Scale(self.root, from_=1, to=10, orient="horizontal", length=150)
        scale.set(level)
        scale.grid(row=row, column=2, padx=10, pady=3)
        scale.bind(
            "<ButtonRelease-1>", lambda e, aid=app["_id"]: self._on_level_change(e, aid)
        )

        self.indicators[app["_id"]] = {
            "indicator": indicator,
            "label": label,
            "process": app["process"],
            "window_title": app["window_title"],
        }

    def _on_level_change(self, event, app_id):
        """Callback per cambio livello"""
        level = int(float(event.widget.get()))

        if app_id in self._last_timer:
            self._last_timer[app_id].cancel()

        self._last_timer[app_id] = threading.Timer(
            0.3, lambda: self.mongo_manager.update_level(app_id, level)
        )
        self._last_timer[app_id].start()

    def _update_active_indicator(self):
        """Aggiorna gli indicatori per l'app attiva"""
        try:
            active_process, active_title = WindowDetector.get_active_window()

            for data in self.indicators.values():
                is_active = (
                    data["process"] == active_process
                    and data["window_title"] == active_title
                )

                if is_active:
                    data["indicator"].config(fg="green")
                    data["label"].config(fg="green", font=("Arial", 10, "bold"))
                else:
                    data["indicator"].config(fg="gray")
                    data["label"].config(fg="black", font=("Arial", 10))
        except Exception as e:
            print(f"[UI UPDATE ERROR] {e}")
        finally:
            if self.root:
                self.root.after(1000, self._update_active_indicator)

    def run(self):
        """Avvia la GUI"""
        if self.root:
            self.root.mainloop()
