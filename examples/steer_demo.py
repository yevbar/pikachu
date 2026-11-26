"""Minimal example policy: steer toward the brighter half of the road region.

Not a real driver -- just shows the frame -> KartAction shape of a policy.
Only run this once you're already in a race (e.g. a Time Trial).

    .venv/bin/python examples/steer_demo.py 20     # run for 20 s
"""
import sys

import numpy as np

from pikachu import Controller, FrameGrabber, KartAction, Policy, run


class SteerDemo(Policy):
    scale = 4  # 480x270 RGB is plenty for this

    def act(self, image: np.ndarray) -> KartAction:
        road = image[150:250].mean(axis=2)  # grayscale band below the horizon
        left, right = road[:, :240].mean(), road[:, 240:].mean()
        if abs(left - right) < 5:
            return KartAction.ACCEL
        return KartAction.ACCEL_SOFT_LEFT if left > right else KartAction.ACCEL_SOFT_RIGHT


if __name__ == "__main__":
    with FrameGrabber() as g, Controller() as c:
        run(SteerDemo(), g, c, duration=float(sys.argv[1]) if len(sys.argv) > 1 else 10)
