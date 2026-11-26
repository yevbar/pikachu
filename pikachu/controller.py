"""Unprivileged client for the root nxbt bridge (nxbridge.py)."""
from __future__ import annotations

import json
import socket
import threading
import time

from .controls import NEUTRAL, Action, KartAction, as_action

SOCK_PATH = "/tmp/pikachu-ctl.sock"
STATUS_PATH = "/tmp/pikachu-status.json"
KEEPALIVE_S = 0.05  # bridge releases everything after ~0.25 s of silence


class Controller:
    """Sends held controller state to the bridge.

    send() sets the state; a keepalive thread re-sends it so the bridge's
    watchdog stays happy while the policy is thinking. close() (or exiting
    the with-block) returns the controller to neutral.
    """

    def __init__(self, path: str = SOCK_PATH):
        self._path = path
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._lock = threading.Lock()
        self._current: Action = NEUTRAL
        self._running = True
        self._thread = threading.Thread(target=self._keepalive, daemon=True, name="Controller")
        self._thread.start()

    def _send_raw(self, msg: dict):
        self._sock.sendto(json.dumps(msg).encode(), self._path)

    def send(self, action: "Action | KartAction | None"):
        a = as_action(action)
        with self._lock:
            self._current = a
            self._send_raw({"t": "state", **a.to_wire()})

    def macro(self, macro: str):
        """Run an nxbt macro string (menu navigation etc.). Overrides held state."""
        with self._lock:
            self._current = NEUTRAL
            self._send_raw({"t": "macro", "m": macro})

    def press(self, *buttons, hold: float = 0.1, gap: float = 0.1):
        """Blocking tap of one or more nxbt button names, e.g. press("B")."""
        names = " ".join(b if isinstance(b, str) else b.name for b in buttons)
        self.macro(f"{names} {hold}s\n{gap}s")
        time.sleep(hold + gap + 0.05)

    def _keepalive(self):
        while self._running:
            time.sleep(KEEPALIVE_S)
            with self._lock:
                if self._current != NEUTRAL:
                    try:
                        self._send_raw({"t": "state", **self._current.to_wire()})
                    except OSError:
                        pass

    @staticmethod
    def status() -> dict:
        try:
            with open(STATUS_PATH) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"state": "bridge not running"}

    def close(self):
        self._running = False
        try:
            self.send(NEUTRAL)
        except OSError:
            pass
        self._sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
