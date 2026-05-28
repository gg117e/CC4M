"""Visualization package for MSCC clone analysis."""

import sys
from pathlib import Path

# src/ 配下の modules パッケージを解決するためにパスを追加
_src_dir = Path(__file__).resolve().parent.parent
_project_root = _src_dir.parent

for _p in (str(_project_root), str(_src_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
