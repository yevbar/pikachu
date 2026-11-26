"""Controller action spec shared by policies, the client and the root bridge."""
from __future__ import annotations

import enum
from dataclasses import dataclass


class Button(enum.IntFlag):
    """Pro Controller buttons. Combine with |, e.g. Button.A | Button.R."""
    NONE = 0
    A = enum.auto()
    B = enum.auto()
    X = enum.auto()
    Y = enum.auto()
    L = enum.auto()
    R = enum.auto()
    ZL = enum.auto()
    ZR = enum.auto()
    PLUS = enum.auto()
    MINUS = enum.auto()
    HOME = enum.auto()
    CAPTURE = enum.auto()
    DPAD_UP = enum.auto()
    DPAD_DOWN = enum.auto()
    DPAD_LEFT = enum.auto()
    DPAD_RIGHT = enum.auto()
    L_STICK_PRESS = enum.auto()
    R_STICK_PRESS = enum.auto()


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, float(v)))


@dataclass(frozen=True)
class Action:
    """Full controller state to hold until the next action.

    Sticks are in [-1, 1]; +x is right, +y is up.
    """
    buttons: Button = Button.NONE
    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0

    def __post_init__(self):
        for f in ("lx", "ly", "rx", "ry"):
            object.__setattr__(self, f, _clamp(getattr(self, f)))

    def to_wire(self) -> dict:
        return {"b": int(self.buttons), "ls": [self.lx, self.ly], "rs": [self.rx, self.ry]}

    @classmethod
    def from_wire(cls, d: dict) -> "Action":
        return cls(Button(d.get("b", 0)), *d.get("ls", (0, 0)), *d.get("rs", (0, 0)))


NEUTRAL = Action()

# nxbt direct-input packet keys for each Button
_NXBT_KEYS = {
    Button.A: "A", Button.B: "B", Button.X: "X", Button.Y: "Y",
    Button.L: "L", Button.R: "R", Button.ZL: "ZL", Button.ZR: "ZR",
    Button.PLUS: "PLUS", Button.MINUS: "MINUS", Button.HOME: "HOME", Button.CAPTURE: "CAPTURE",
    Button.DPAD_UP: "DPAD_UP", Button.DPAD_DOWN: "DPAD_DOWN",
    Button.DPAD_LEFT: "DPAD_LEFT", Button.DPAD_RIGHT: "DPAD_RIGHT",
}


def to_nxbt_packet(action: Action, packet: dict) -> dict:
    """Fill an nxbt packet (from Nxbt.create_input_packet()) from an Action."""
    for btn, key in _NXBT_KEYS.items():
        packet[key] = bool(action.buttons & btn)
    packet["L_STICK"]["PRESSED"] = bool(action.buttons & Button.L_STICK_PRESS)
    packet["R_STICK"]["PRESSED"] = bool(action.buttons & Button.R_STICK_PRESS)
    packet["L_STICK"]["X_VALUE"] = round(action.lx * 100)
    packet["L_STICK"]["Y_VALUE"] = round(action.ly * 100)
    packet["R_STICK"]["X_VALUE"] = round(action.rx * 100)
    packet["R_STICK"]["Y_VALUE"] = round(action.ry * 100)
    return packet


class KartAction(enum.Enum):
    """Discrete Mario Kart World action set, handy as a classifier/RL head.

    Default MKW Pro Controller layout: A accelerate, B brake/reverse,
    R hop/drift, L use item, left stick steer.
    """
    NOOP = Action()
    ACCEL = Action(Button.A)
    ACCEL_LEFT = Action(Button.A, lx=-1)
    ACCEL_RIGHT = Action(Button.A, lx=1)
    ACCEL_SOFT_LEFT = Action(Button.A, lx=-0.5)
    ACCEL_SOFT_RIGHT = Action(Button.A, lx=0.5)
    DRIFT_LEFT = Action(Button.A | Button.R, lx=-1)
    DRIFT_RIGHT = Action(Button.A | Button.R, lx=1)
    HOP = Action(Button.A | Button.R)
    ITEM = Action(Button.A | Button.L)
    BRAKE = Action(Button.B)

    @property
    def action(self) -> Action:
        return self.value


def as_action(a: "Action | KartAction | None") -> Action:
    if a is None:
        return NEUTRAL
    return a.action if isinstance(a, KartAction) else a
