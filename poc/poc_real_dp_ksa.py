#!/usr/bin/env python3
"""Compatibility entry point for the modular adaptive pipeline.

The former monolithic implementation is preserved under ``archive/`` for
historical comparison. The supported entry point is now ``run_pipeline.py``;
this wrapper keeps the old filename usable and exposes its ``--query`` flag.
"""

from __future__ import annotations

from run_pipeline import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
