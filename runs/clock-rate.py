#!/usr/bin/env python3
"""clock-rate.py [SECONDS]: how fast Windows' clock runs against this WSL's (monotonic against monotonic), for a
test relay or simulated players in WSL beside games on Windows (--clock-rate). On the first PC the WSL clock has run
3.8% slow for days and at other times at the same rate (2026-10-06, the port-recomp notes 5.15), so a test
measures it instead of assuming it. Prints the ratio with three decimals (1.000: the same rate)."""
import subprocess
import sys
import time

seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 5
p = subprocess.Popen(["powershell.exe", "-NoProfile", "-Command",
                      "$s=[Diagnostics.Stopwatch]::StartNew(); Start-Sleep -Milliseconds 300; Write-Output $s.Elapsed.TotalSeconds; "
                      f"Start-Sleep -Seconds {seconds}; Write-Output $s.Elapsed.TotalSeconds"],
                     stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)
a = float(p.stdout.readline())
m0 = time.monotonic()
b = float(p.stdout.readline())
m1 = time.monotonic()
print(f"{(b - a) / (m1 - m0):.3f}")
