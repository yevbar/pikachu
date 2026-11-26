"""Measure input->photon latency by toggling the menu cursor (DPAD down/up).

Run on a menu where D-pad moves a highlight instantly (e.g. System > Controllers).
    .venv/bin/python examples/latency.py 20
"""
import statistics
import sys
import time

import numpy as np

from pikachu import Action, Button, Controller, FrameGrabber

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20


def changed(a, b):
    # fraction of pixels that changed noticeably
    return (np.abs(a.astype(int) - b).max(axis=2) > 40).mean() > 0.006


with FrameGrabber() as g, Controller() as c:
    lat = []
    for i in range(N):
        btn = Button.DPAD_DOWN if i % 2 == 0 else Button.DPAD_UP
        time.sleep(0.6)  # let the screen settle
        before = g.latest(scale=4)
        t0 = time.monotonic()
        c.send(Action(btn))
        seq = before.seq
        while time.monotonic() - t0 < 1.0:
            f = g.latest(seq, scale=4)
            seq = f.seq
            if time.monotonic() - t0 > 0.08 and not c._current == Action():
                c.send(None)
            if changed(f.image, before.image):
                lat.append((f.t - t0) * 1000)
                break
        c.send(None)
    print(f"{len(lat)}/{N} presses detected")
    if lat:
        print(f"input->screen latency ms: median {statistics.median(lat):.0f}, "
              f"min {min(lat):.0f}, max {max(lat):.0f}")
        print("all:", [round(x) for x in lat])
