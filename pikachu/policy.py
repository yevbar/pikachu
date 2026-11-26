"""Policy interface and the real-time loop that drives it."""
from __future__ import annotations

import abc
import time

import numpy as np

from .capture import Frame, FrameGrabber
from .controls import NEUTRAL, Action, KartAction, as_action


class Policy(abc.ABC):
    """Subclass and implement act(). Set input_format = "pil" to get PIL images."""
    input_format: str = "numpy"  # or "pil"
    scale: int = 2               # JPEG downscale: 1=1920x1080, 2=960x540, 4=480x270

    @abc.abstractmethod
    def act(self, image) -> "Action | KartAction | None":
        """Given the latest RGB frame, return the controller state to hold."""

    def reset(self):
        """Called before the loop starts."""


class Noop(Policy):
    def act(self, image):
        return NEUTRAL


def run(policy: Policy, grabber: FrameGrabber, controller=None,
        duration: float | None = None, max_hz: float | None = None, report_every: float = 5.0):
    """Frame -> policy -> controller loop. controller=None is a dry run.

    Paced by the capture card (60 fps); max_hz caps it lower if set.
    """
    policy.reset()
    min_dt = 0.0 if max_hz is None else 1.0 / max_hz
    seq, n, lat_sum, t_report = 0, 0, 0.0, time.monotonic()
    t_end = None if duration is None else time.monotonic() + duration
    try:
        while t_end is None or time.monotonic() < t_end:
            t0 = time.monotonic()
            frame: Frame = grabber.latest(seq, scale=policy.scale)
            seq = frame.seq
            image = frame.to_pil() if policy.input_format == "pil" else frame.image
            action = as_action(policy.act(image))
            if controller is not None:
                controller.send(action)
            n += 1
            lat_sum += time.monotonic() - frame.t  # frame arrival -> input sent
            now = time.monotonic()
            if now - t_report >= report_every:
                print(f"[run] {n / (now - t_report):.1f} Hz, "
                      f"frame->send {lat_sum / n * 1000:.1f} ms, last={action}")
                n, lat_sum, t_report = 0, 0.0, now
            spare = min_dt - (time.monotonic() - t0)
            if spare > 0:
                time.sleep(spare)
    finally:
        if controller is not None:
            controller.send(NEUTRAL)
