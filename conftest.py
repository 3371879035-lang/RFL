"""Make ``src/`` importable for tests without installing the package.

Keeps the project importable from a frozen, shared interpreter (the same one
the v0.2 tree uses) without writing into its site-packages.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
