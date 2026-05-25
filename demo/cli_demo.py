#!/usr/bin/env python3
"""
Interactive demo script for asciinema recording.
Feeds commands to lifi_agent interactive mode with realistic timing.
"""

import subprocess, time, sys, os

SPEED = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0

def wait(s): time.sleep(s / SPEED)

# Commands to feed to interactive mode
commands = [
    ("send 0.001 WETH from Base to Arbitrum", 8),
    ("safe send 0.001 WETH from Base to Arbitrum with max_fee 0.5%", 10),
    ("doctor", 8),
]

print("Starting interactive CLI demo...", flush=True)
wait(1)

# Launch interactive mode
proc = subprocess.Popen(
    ["python3", "-m", "lifi_agent"],
    stdin=subprocess.PIPE,
    stdout=sys.stdout,
    stderr=sys.stderr,
    cwd="/root/lifi-intents-demo",
    env={**os.environ, "LIFI_AGENT_MOCK_MODE": "0"},
)

for cmd, pause in commands:
    wait(2)
    proc.stdin.write((cmd + "\n").encode())
    proc.stdin.flush()
    wait(pause)

# Exit
wait(1)
proc.stdin.write(b"exit\n")
proc.stdin.flush()
proc.wait()
