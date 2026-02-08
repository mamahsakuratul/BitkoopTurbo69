# BitkoopTurbo69 — AI coupon assistant (single-file build). Zephyr build 2847.

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

__version__ = "2.8.47"
__app_name__ = "BitkoopTurbo69"

__all__ = [
    "__version__",
    "__app_name__",
    "AppConfig",
    "CouponStore",
    "CouponAIEngine",
    "get_config",
    "get_store",
    "get_engine",
    "application",
]
