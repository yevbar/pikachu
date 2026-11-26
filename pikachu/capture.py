"""Low-latency frame grabber for the USB capture card (V4L2, MJPEG).

A background thread keeps the newest raw JPEG from the card (60 fps).
Frames are only decoded when a consumer asks, so a slow policy never
builds up a backlog; it just always sees the most recent frame.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

_REDUCED = {1: cv2.IMREAD_COLOR, 2: cv2.IMREAD_REDUCED_COLOR_2,
            4: cv2.IMREAD_REDUCED_COLOR_4, 8: cv2.IMREAD_REDUCED_COLOR_8}


@dataclass
class Frame:
    seq: int          # monotonically increasing frame number
    t: float          # time.monotonic() when the frame arrived from the card
    image: np.ndarray  # RGB uint8, HxWx3

    def to_pil(self):
        from PIL import Image
        return Image.fromarray(self.image)


class FrameGrabber:
    def __init__(self, device: str = "/dev/video0", width: int = 1920,
                 height: int = 1080, fps: int = 60):
        self._cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open {device}")
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        # Hand us the raw JPEG bytes; we decode ourselves (faster, and lets us
        # skip the occasional empty buffer the card emits).
        self._cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)

        self._cond = threading.Condition()
        self._jpeg: np.ndarray | None = None
        self._seq = 0
        self._t = 0.0
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="FrameGrabber")
        self._thread.start()

    def _loop(self):
        while self._running:
            ok, buf = self._cap.read()
            t = time.monotonic()
            if not ok or buf is None or buf.size < 1000:
                continue
            # Copy: OpenCV reuses this buffer for the next read, which would
            # corrupt a frame a consumer is still decoding.
            jpeg = buf.reshape(-1).copy()
            with self._cond:
                self._jpeg = jpeg
                self._seq += 1
                self._t = t
                self._cond.notify_all()

    def latest(self, after_seq: int = 0, timeout: float = 1.0, scale: int = 2) -> Frame:
        """Return the newest frame with seq > after_seq, waiting up to timeout.

        scale: 1, 2, 4 or 8 -- JPEG-domain downscale (1080p / 2 = 960x540).
        """
        with self._cond:
            if not self._cond.wait_for(lambda: self._seq > after_seq, timeout):
                raise TimeoutError("no new frame from capture card")
            jpeg, seq, t = self._jpeg, self._seq, self._t
        bgr = cv2.imdecode(jpeg, _REDUCED[scale])
        return Frame(seq, t, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

    def frames(self, scale: int = 2, timeout: float = 1.0):
        """Iterate over fresh frames, skipping any that arrived while busy."""
        seq = 0
        while self._running:
            f = self.latest(seq, timeout, scale)
            seq = f.seq
            yield f

    def close(self):
        self._running = False
        self._thread.join(timeout=1)
        self._cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
