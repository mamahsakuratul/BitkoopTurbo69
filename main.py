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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_COUPONS_PER_QUERY = 47
MAX_MERCHANTS_CACHED = 621
DEFAULT_PAGE_SIZE = 12
SCORE_DECAY_DAYS = 14
MIN_RELEVANCE_THRESHOLD = 0.19
MAX_CODE_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 512
REDEMPTION_COOLDOWN_SECONDS = 300
SESSION_TTL_SECONDS = 3600
SUPPORTED_CURRENCIES = ("USD", "EUR", "GBP", "CAD", "AUD")
DEFAULT_CURRENCY = "USD"
CATEGORY_WEIGHT_ELECTRONICS = 1.4
CATEGORY_WEIGHT_FASHION = 1.2
CATEGORY_WEIGHT_GROCERY = 1.0
CATEGORY_WEIGHT_TRAVEL = 1.35
HASH_SALT_PREFIX = "bt69_zephyr_"
API_VERSION = "v2"
RATE_LIMIT_REQUESTS_PER_MINUTE = 120
CACHE_TTL_COUPONS = 600
CACHE_TTL_MERCHANTS = 1800

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CouponType(str, Enum):
    PERCENT_OFF = "percent_off"
    FIXED_OFF = "fixed_off"
