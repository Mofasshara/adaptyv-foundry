from __future__ import annotations
import copy
import json
from pathlib import Path
from typing import Any

_FIX = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return copy.deepcopy(json.loads((_FIX / name).read_text()))  # defensive copy
