#!/usr/bin/env python3
"""Entry point: python3 uiforge.py <discover|search|inspect|evaluate> ...

The package lives next to this file (``ui_forge/``); no installation step and no
third-party dependencies. Keeping a single launcher also means the old
``skill/scripts/inspect.py`` name (which shadowed the standard library on
Python 3.14) no longer exists to break argparse.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui_forge.cli import main  # noqa: E402  (path set above on purpose)

if __name__ == "__main__":
    sys.exit(main())
