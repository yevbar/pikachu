"""Run as root. Emulates a Pro Controller via nxbt and accepts commands from
pikachu.controller.Controller over a Unix datagram socket.

Messages (JSON):
  {"t": "state", "b": <Button bits>, "ls": [x, y], "rs": [x, y]}  held input
  {"t": "macro", "m": "<nxbt macro>"}                              queued macro
Held state is released to neutral if no state message arrives for WATCHDOG_S.
Status is written to /tmp/pikachu-status.json, log to /tmp/nxbt.log.
"""
import json
import logging
import os
import socket
import sys
import time

import nxbt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pikachu.controls import NEUTRAL, Action, to_nxbt_packet  # noqa: E402

SOCK_PATH = "/tmp/pikachu-ctl.sock"
STATUS_PATH = "/tmp/pikachu-status.json"
LOG = "/tmp/nxbt.log"
WATCHDOG_S = 0.25

logging.basicConfig(filename=LOG, level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.info
os.chmod(LOG, 0o666)


def write_status(**kw):
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"ts": time.time(), **kw}, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATUS_PATH)


nx = nxbt.Nxbt()
addrs = nx.get_switch_addresses()
log(f"known switch addresses: {addrs}")
ctl = nx.create_controller(nxbt.PRO_CONTROLLER, reconnect_address=addrs or None)
log("controller created, waiting for connection (open Change Grip/Order on the Switch if pairing)")
while True:
    st = nx.state[ctl]
    write_status(state=st["state"])
    if st["state"] == "connected":
        break
    if st["state"] == "crashed":
        log(f"CRASHED: {st['errors']}")
        sys.exit(1)
    time.sleep(0.5)
log("CONNECTED")

if os.path.exists(SOCK_PATH):
    os.remove(SOCK_PATH)
sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.bind(SOCK_PATH)
os.chmod(SOCK_PATH, 0o666)
sock.settimeout(0.05)

held = NEUTRAL
last_state_msg = 0.0
last_status = 0.0
n_msgs = 0


def apply(action):
    nx.set_controller_input(ctl, to_nxbt_packet(action, nx.create_input_packet()))


while True:
    try:
        data = sock.recv(65536)
        msg = json.loads(data)
        n_msgs += 1
        if msg.get("t") == "state":
            action = Action.from_wire(msg)
            last_state_msg = time.monotonic()
            if action != held:
                held = action
                apply(held)
        elif msg.get("t") == "macro":
            held = NEUTRAL
            apply(NEUTRAL)
            log(f"macro: {msg['m']!r}")
            nx.macro(ctl, msg["m"], block=False)
    except socket.timeout:
        pass
    except (ValueError, KeyError) as e:
        log(f"bad message: {e!r}")

    now = time.monotonic()
    if held != NEUTRAL and now - last_state_msg > WATCHDOG_S:
        log("watchdog: no input from client, releasing to neutral")
        held = NEUTRAL
        apply(NEUTRAL)
    if now - last_status > 0.5:
        st = nx.state[ctl]
        write_status(state=st["state"], held=held.to_wire(), msgs=n_msgs)
        last_status = now
        if st["state"] == "crashed":
            log(f"CRASHED: {st['errors']}")
            sys.exit(1)
