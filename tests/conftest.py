"""Test bootstrap helpers.

Keeps repository-root imports stable across local/CI pytest invocations without
mutating import order when root is already discoverable.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.append(root_str)
