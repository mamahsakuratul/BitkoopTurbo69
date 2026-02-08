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
    FREE_SHIP = "free_ship"
    BOGO = "bogo"
    CASHBACK = "cashback"
    BUNDLE = "bundle"


class MerchantTier(str, Enum):
    PREMIUM = "premium"
    STANDARD = "standard"
    PARTNER = "partner"


@dataclass
class Merchant:
    merchant_id: str
    name: str
    slug: str
    domain: str
    tier: MerchantTier
    categories: List[str]
    logo_url: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "merchant_id": self.merchant_id,
            "name": self.name,
            "slug": self.slug,
            "domain": self.domain,
            "tier": self.tier.value,
            "categories": self.categories,
            "logo_url": self.logo_url,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class Coupon:
    coupon_id: str
    merchant_id: str
    code: str
    description: str
    coupon_type: CouponType
    value: float
    currency: str
    min_purchase: Optional[float] = None
    max_discount: Optional[float] = None
    expires_at: Optional[datetime] = None
    is_verified: bool = False
    use_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "coupon_id": self.coupon_id,
            "merchant_id": self.merchant_id,
            "code": self.code,
            "description": self.description,
            "coupon_type": self.coupon_type.value,
            "value": self.value,
            "currency": self.currency,
            "min_purchase": self.min_purchase,
            "max_discount": self.max_discount,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_verified": self.is_verified,
            "use_count": self.use_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
        }


@dataclass
class UserPreference:
    user_id: str
    preferred_categories: List[str]
    preferred_merchants: List[str]
    currency: str
    max_results: int
    exclude_expired: bool = True
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "preferred_categories": self.preferred_categories,
            "preferred_merchants": self.preferred_merchants,
            "currency": self.currency,
            "max_results": self.max_results,
            "exclude_expired": self.exclude_expired,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class SearchRequest:
    query: str
    categories: Optional[List[str]] = None
