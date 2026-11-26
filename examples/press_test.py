"""Smoke test for the bridge: press one button and report whether the screen changed.

    .venv/bin/python examples/press_test.py B
"""
import sys
import time

import numpy as np

from pikachu import Action, Button, Controller, FrameGrabber

button = Button[sys.argv[1] if len(sys.argv) > 1 else "B"]

with FrameGrabber() as g, Controller() as c:
    print("bridge:", Controller.status())
    before = g.latest(scale=4)
    t_press = time.monotonic()
    c.send(Action(button))
    time.sleep(0.1)
    c.send(None)
    # Watch for the first frame that differs noticeably from the one before the press.
    seq, t_change = before.seq, None
    while time.monotonic() - t_press < 2.0:
        f = g.latest(seq, scale=4)
        seq = f.seq
        if np.abs(f.image.astype(int) - before.image).mean() > 4:
            t_change = f.t
            break
    if t_change:
        print(f"screen changed {(t_change - t_press) * 1000:.0f} ms after pressing {button.name}")
    else:
        print(f"no screen change within 2 s of pressing {button.name}")
