#!/usr/bin/env python3
"""Return exit code 0 if `torch` is importable, non-zero otherwise."""
import sys
try:
    import importlib
    util = getattr(importlib, "util", None)
    if util is not None:
        spec = util.find_spec("torch")
    else:
        import pkgutil
        spec = pkgutil.find_loader("torch")
except Exception:
    spec = None

sys.exit(0 if spec else 1)
