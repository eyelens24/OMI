#!/usr/bin/env python3
"""Cross-platform, local-only Doctor Quant launcher. Run with any Python 3.10+."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ.setdefault("HOST", "127.0.0.1")
os.environ.setdefault("PORT", "8000")
print(f"Starting Doctor Quant at http://{os.environ['HOST']}:{os.environ['PORT']} (local-only)")
raise SystemExit(subprocess.call([sys.executable, "server.py"], env=os.environ))
