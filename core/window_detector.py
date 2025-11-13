"""Rilevamento finestra attiva cross-platform"""

import re
import platform
import subprocess
from typing import Tuple, Optional
import psutil
from urllib.parse import urlparse


class WindowDetector:
    """Rileva la finestra attiva in modo cross-platform"""

    @staticmethod
    def get_active_window() -> Tuple[str, str]:
        """Ritorna (process_name, window_title)"""
        system = platform.system()

        if system == "Darwin":
            return WindowDetector._get_macos_window()
        elif system == "Windows":
            return WindowDetector._get_windows_window()
        elif system == "Linux":
            return WindowDetector._get_linux_window()
        else:
            return "unknown", "Unknown"

    @staticmethod
    def _get_macos_window() -> Tuple[str, str]:
        """Rileva finestra attiva su macOS"""
        app_name, window_title = "unknown", "Unknown"

        try:
            script = """
                tell application "System Events"
                    set frontApp to first application process whose frontmost is true
                    set bundleID to bundle identifier of frontApp
                    return bundleID
                end tell
            """
            result = subprocess.check_output(["osascript", "-e", script])
            app_name = WindowDetector.normalize_app_name(result.decode("utf-8").strip())
            window_title = app_name

            # Gestione browser
            browsers = ["Chrome", "Safari", "Firefox", "Brave"]
            if window_title in browsers:
                url = WindowDetector._get_browser_url(window_title)
                if url:
                    match = re.search(r"https?://([a-zA-Z0-9.-]+)", url)
                    window_title = match.group(1) if match else url
                else:
                    app_name, window_title = "unknown", "Unknown"
        except Exception as e:
            print(f"[WARN] macOS detection failed: {e}")

        return app_name, window_title

    @staticmethod
    def normalize_app_name(raw: str) -> str:
        """Restituisce un nome leggibile da bundle ID o nome processo"""
        if "." in raw:  # es: com.microsoft.VSCode
            name = raw.split(".")[-1]
            # Se è camelCase o PascalCase → aggiunge spazi
            name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).strip()
            return name
        return raw.strip()

    @staticmethod
    def _get_browser_url(browser_name: str) -> Optional[str]:
        """Estrae l'URL dal browser su macOS"""
        scripts = {
            "Chrome": 'tell application "Google Chrome" to return URL of '
            "active tab of front window",
            "Safari": 'tell application "Safari" to return URL of '
            "current tab of front window",
            "Firefox": 'tell application "Firefox" to return URL of '
            "current tab of front window",
            "Brave Browser": 'tell application "Brave Browser" to return URL of '
            "active tab of front window",
        }

        try:
            url = (
                subprocess.check_output(["osascript", "-e", scripts[browser_name]])
                .decode()
                .strip()
            )
            return WindowDetector._get_domain(url) if url else None
        except Exception:
            return None

    @staticmethod
    def _get_domain(url: str) -> str | None:
        try:
            hostname = urlparse(url).hostname
            if not hostname or "." not in hostname:
                return None
            parts = hostname.split(".")
            return ".".join(parts[-2:])
        except Exception:
            return None

    @staticmethod
    def _get_windows_window() -> Tuple[str, str]:
        """Rileva finestra attiva su Windows"""
        try:
            import win32gui  # type: ignore
            import win32process  # type: ignore

            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return "unknown", "Unknown"

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)

            # Nome app
            app_name = proc.name().replace(".exe", "")

            # Titolo finestra
            window_title = win32gui.GetWindowText(hwnd).strip() or "Unknown"
            app_name = WindowDetector.normalize_app_name(window_title)
            window_title = app_name

            # Se è un browser, prova a estrarre dominio
            browsers = ["chrome", "msedge", "firefox", "brave"]
            if any(b in app_name.lower() for b in browsers):
                match = re.search(r"https?://([a-zA-Z0-9.-]+)", window_title)
                if match:
                    window_title = match.group(1)

            return app_name, window_title

        except Exception as e:
            print(f"[WARN] Windows detection failed: {e}")
            return "unknown", "Unknown"

    @staticmethod
    def _get_linux_window() -> Tuple[str, str]:
        """Rileva finestra attiva su Linux"""
        try:
            # Ottiene ID finestra attiva
            win_id = (
                subprocess.check_output(
                    ["xdotool", "getwindowfocus"], stderr=subprocess.DEVNULL
                )
                .decode()
                .strip()
            )

            # Nome finestra (titolo)
            window_title = (
                subprocess.check_output(
                    ["xdotool", "getwindowname", win_id], stderr=subprocess.DEVNULL
                )
                .decode()
                .strip()
            )
            window_title = WindowDetector.normalize_app_name(window_title)

            # Nome app
            app_name = (
                subprocess.check_output(
                    ["xprop", "-id", win_id, "WM_CLASS"], stderr=subprocess.DEVNULL
                )
                .decode()
                .strip()
            )
            app_name = WindowDetector.normalize_app_name(app_name)

            # xprop ritorna tipo: WM_CLASS(STRING) = "code", "Code"
            match = re.search(r'"([^"]+)",\s*"([^"]+)"', app_name)
            app_name = match.group(2) if match else "unknown"

            if not window_title:
                window_title = "Unknown"

            # Gestione browser: se è Chrome/Firefox/Brave, estrai dominio
            browsers = ["Chrome", "Firefox", "Brave", "Chromium"]
            if any(b.lower() in app_name.lower() for b in browsers):
                match = re.search(r"https?://([a-zA-Z0-9.-]+)", window_title)
                if match:
                    window_title = match.group(1)

            return app_name, window_title

        except Exception as e:
            print(f"[WARN] Linux detection failed: {e}")
            return "unknown", "Unknown"
