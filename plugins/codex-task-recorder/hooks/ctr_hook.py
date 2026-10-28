"""Codex hook entry point. Every lifecycle event runs this script.

It must never block Codex: whatever happens, it exits 0.
"""
import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, _LIB)

try:
    from ctr.hook import main
except BaseException:  # a broken install must not break the user's session
    sys.exit(0)

sys.exit(main())
