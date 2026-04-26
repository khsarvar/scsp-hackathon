"""Subprocess-based Python sandbox for the code agent.

Each `run_python(code, ...)` call:
  - Spawns a fresh `python -c <preamble + code>` subprocess.
  - Sets cwd to a per-session work_dir so any `plt.savefig('foo.png')` lands there.
  - Loads the cleaned CSV at HEALTHLAB_CSV into `df` before the agent's code runs.
  - Captures stdout/stderr, enforces a wall-clock timeout, and lists any new PNGs.

The sandbox is deliberately simple: subprocess isolation only, no resource limits or
network policies. Acceptable for a single-user hackathon app — do not expose to
untrusted callers.

NOTE: subprocesses do NOT share state across calls. Every call rebuilds `df` from
the CSV. The agent's prompt makes this constraint explicit.
"""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any


PREAMBLE = """
import os, sys, json, math
os.environ['MPLBACKEND'] = 'Agg'
import pandas as pd
import numpy as np
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
pd.set_option('display.width', 160)
pd.set_option('display.max_columns', 40)

DATA_PATH = os.environ['HEALTHLAB_CSV']
df = pd.read_csv(DATA_PATH)
# --- agent code below ---
"""


def run_python(
    code: str,
    csv_path: str,
    work_dir: str,
    timeout: int = 30,
) -> dict[str, Any]:
    """Execute `code` in a subprocess with `df` pre-loaded from `csv_path`.

    Returns a dict with stdout, stderr, list of new PNG basenames written to
    work_dir, return code, and a `timeout` flag.
    """
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    before = {p.name for p in Path(work_dir).iterdir() if p.is_file()}

    script = PREAMBLE + "\n" + code + "\n"

    env = os.environ.copy()
    env["HEALTHLAB_CSV"] = csv_path
    env["MPLBACKEND"] = "Agg"
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out: dict[str, Any] = {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-4000:],
            "returncode": proc.returncode,
            "timeout": False,
        }
    except subprocess.TimeoutExpired as e:
        captured_out = (e.stdout or b"")
        captured_err = (e.stderr or b"")
        if isinstance(captured_out, bytes):
            captured_out = captured_out.decode("utf-8", errors="replace")
        if isinstance(captured_err, bytes):
            captured_err = captured_err.decode("utf-8", errors="replace")
        out = {
            "ok": False,
            "stdout": captured_out[-8000:],
            "stderr": (captured_err + f"\nTimeoutExpired after {timeout}s")[-4000:],
            "returncode": -1,
            "timeout": True,
        }
    except Exception as e:
        out = {
            "ok": False,
            "stdout": "",
            "stderr": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"[-4000:],
            "returncode": -1,
            "timeout": False,
        }

    after = {p.name for p in Path(work_dir).iterdir() if p.is_file()}
    new_pngs = sorted(f for f in (after - before) if f.lower().endswith(".png"))
    out["charts"] = new_pngs
    return out
