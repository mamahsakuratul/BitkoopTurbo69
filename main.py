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
    merchant_ids: Optional[List[str]] = None
    coupon_types: Optional[List[CouponType]] = None
    page: int = 1
    page_size: int = 12
    sort_by: str = "relevance"


@dataclass
class SearchResult:
    coupon: Coupon
    score: float
    match_reasons: List[str]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class AppConfig:
    app_name: str = "BitkoopTurbo69"
    environment: str = "production"
    debug: bool = False
    default_currency: str = DEFAULT_CURRENCY
    page_size: int = DEFAULT_PAGE_SIZE
    rate_limit_rpm: int = RATE_LIMIT_REQUESTS_PER_MINUTE
    cache_ttl_coupons: int = CACHE_TTL_COUPONS
    cache_ttl_merchants: int = CACHE_TTL_MERCHANTS
    session_ttl: int = SESSION_TTL_SECONDS
    api_host: str = "0.0.0.0"
    api_port: int = 8947
    log_level: str = "INFO"
    secret_salt: str = "x9k2m7q4v1n8p5w0z3b6c"
    merchant_feed_url: str = "https://api.bitkoop-turbo69.example.com/merchants"
    coupon_feed_url: str = "https://api.bitkoop-turbo69.example.com/coupons"
    webhook_verification_token: str = "wv_7f2e9a1b4c8d0e3f5a6"
    allowed_origins: List[str] = field(
        default_factory=lambda: [
            "https://shopping-god.example.com",
            "http://localhost:8948",
            "http://127.0.0.1:8948",
        ]
    )
    db_path: str = "bitkoop_turbo69_data.db"
    backup_interval_hours: int = 6
    max_backup_count: int = 14

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            environment=os.environ.get("BT69_ENV", "production"),
            debug=os.environ.get("BT69_DEBUG", "0") == "1",
            api_port=int(os.environ.get("BT69_API_PORT", "8947")),
            log_level=os.environ.get("BT69_LOG_LEVEL", "INFO"),
        )


def get_config() -> AppConfig:
    return AppConfig.from_env()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    def __init__(self, message: str, field: Optional[str] = None):
        self.message = message
        self.field = field
        super().__init__(message)


def validate_coupon_code(code: str) -> str:
    if not code or not code.strip():
        raise ValidationError("Coupon code cannot be empty", "code")
    cleaned = code.strip()[:MAX_CODE_LENGTH]
    if len(cleaned) < 2:
        raise ValidationError("Coupon code too short", "code")
    return cleaned


def validate_description(desc: str) -> str:
    if not desc:
        return ""
    return desc.strip()[:MAX_DESCRIPTION_LENGTH]


def validate_merchant_id(merchant_id: str) -> str:
    if not merchant_id or not merchant_id.strip():
        raise ValidationError("Merchant ID cannot be empty", "merchant_id")
    if not re.match(r"^[a-zA-Z0-9_-]+$", merchant_id):
        raise ValidationError("Merchant ID contains invalid characters", "merchant_id")
    return merchant_id.strip()


def validate_coupon_type(value: str) -> CouponType:
    try:
        return CouponType(value)
    except ValueError:
        raise ValidationError(f"Unknown coupon type: {value}", "coupon_type")


def validate_currency(currency: str) -> str:
    c = currency.strip().upper()
    if c not in SUPPORTED_CURRENCIES:
        raise ValidationError(f"Unsupported currency: {currency}", "currency")
    return c


def validate_page(page: int) -> int:
    if page < 1:
        return 1
    return min(page, 9999)


def validate_page_size(size: int, max_size: int = 100) -> int:
    if size < 1:
        return 12
    return min(size, max_size)


def validate_categories(categories: Optional[List[str]]) -> List[str]:
    if not categories:
        return []
    out = []
    for c in categories[:20]:
        if c and isinstance(c, str) and c.strip():
            out.append(c.strip().lower())
    return list(dict.fromkeys(out))


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text.strip())
    return " ".join(normalized.split())


def hash_coupon_id(merchant_id: str, code: str, created_ts: Optional[float] = None) -> str:
    raw = f"{HASH_SALT_PREFIX}{merchant_id}:{code}:{created_ts or 0}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def slugify(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = "".join(c if c.isalnum() or c in "-_" else " " for c in s)
    return "-".join(s.lower().split())[:64]


def utc_now() -> datetime:
    return datetime.utcnow()


def parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def chunk_list(lst: List, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def serialize_coupon(c: Coupon) -> Dict[str, Any]:
    return c.to_dict()


def serialize_merchant(m: Merchant) -> Dict[str, Any]:
    return m.to_dict()


def serialize_search_result(sr: SearchResult) -> Dict[str, Any]:
    return {
        "coupon": serialize_coupon(sr.coupon),
        "score": round(sr.score, 4),
        "match_reasons": sr.match_reasons,
    }


def serialize_search_results(results: List[SearchResult]) -> List[Dict[str, Any]]:
    return [serialize_search_result(sr) for sr in results]


def serialize_user_preference(up: UserPreference) -> Dict[str, Any]:
    return up.to_dict()


def serialize_error(message: str, code: str = "ERROR") -> Dict[str, Any]:
    return {"success": False, "error": message, "code": code}


# ---------------------------------------------------------------------------
# Coupon store
# ---------------------------------------------------------------------------


class CouponStore:
    def __init__(self) -> None:
        self._coupons: Dict[str, Coupon] = {}
        self._merchants: Dict[str, Merchant] = {}
        self._by_merchant: Dict[str, List[str]] = {}
        self._by_category: Dict[str, List[str]] = {}

    def add_merchant(self, merchant: Merchant) -> None:
        self._merchants[merchant.merchant_id] = merchant
        for cat in merchant.categories:
            self._by_category.setdefault(cat, []).append(merchant.merchant_id)
            self._by_category[cat] = list(dict.fromkeys(self._by_category[cat]))

    def get_merchant(self, merchant_id: str) -> Optional[Merchant]:
        return self._merchants.get(merchant_id)

    def list_merchants(self, limit: int = 100) -> List[Merchant]:
        return list(self._merchants.values())[:limit]

    def add_coupon(self, coupon: Coupon) -> None:
        self._coupons[coupon.coupon_id] = coupon
        self._by_merchant.setdefault(coupon.merchant_id, []).append(coupon.coupon_id)

    def get_coupon(self, coupon_id: str) -> Optional[Coupon]:
        return self._coupons.get(coupon_id)

    def get_coupons_by_merchant(self, merchant_id: str) -> List[Coupon]:
        ids = self._by_merchant.get(merchant_id, [])
        return [self._coupons[cid] for cid in ids if cid in self._coupons]

    def get_coupons_by_category(self, category: str) -> List[Coupon]:
        m_ids = self._by_category.get(category, [])
        out: List[Coupon] = []
        for mid in m_ids:
            out.extend(self.get_coupons_by_merchant(mid))
        return out

    def list_all_coupons(self, limit: int = 500) -> List[Coupon]:
        return list(self._coupons.values())[:limit]

    def remove_coupon(self, coupon_id: str) -> bool:
        if coupon_id not in self._coupons:
            return False
        c = self._coupons.pop(coupon_id)
        lst = self._by_merchant.get(c.merchant_id, [])
        if coupon_id in lst:
            lst.remove(coupon_id)
        return True

    def increment_use_count(self, coupon_id: str) -> bool:
        c = self._coupons.get(coupon_id)
        if not c:
            return False
        c.use_count += 1
        c.updated_at = utc_now()
        return True

    def coupon_count(self) -> int:
        return len(self._coupons)

    def merchant_count(self) -> int:
        return len(self._merchants)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

CATEGORIES: List[str] = [
    "electronics", "fashion", "grocery", "travel", "home", "sports",
    "beauty", "books", "toys", "automotive", "health", "food", "pet",
    "office", "jewelry",
]

SUBCATEGORIES: dict = {
    "electronics": ["laptops", "phones", "tablets", "audio", "gaming", "cameras"],
    "fashion": ["mens", "womens", "kids", "shoes", "accessories", "outerwear"],
    "grocery": ["produce", "dairy", "frozen", "beverages", "snacks", "organic"],
    "travel": ["flights", "hotels", "car-rental", "vacation-packages", "cruises"],
    "home": ["furniture", "kitchen", "bedding", "decor", "outdoor", "tools"],
    "sports": ["fitness", "outdoor", "cycling", "team-sports", "winter"],
    "beauty": ["skincare", "makeup", "hair", "fragrance", "bath"],
    "books": ["fiction", "nonfiction", "children", "academic", "audiobooks"],
    "toys": ["action-figures", "board-games", "educational", "outdoor-toys"],
    "automotive": ["parts", "accessories", "tires", "tools", "care"],
    "health": ["vitamins", "supplements", "medical-supplies", "wellness"],
    "food": ["restaurants", "meal-kits", "delivery", "baking", "international"],
    "pet": ["dog", "cat", "bird", "aquarium", "small-pet"],
    "office": ["supplies", "furniture", "tech", "printing", "storage"],
    "jewelry": ["rings", "necklaces", "bracelets", "earrings", "watches"],
}


def get_all_categories() -> List[str]:
    return list(CATEGORIES)


def get_subcategories(category: str) -> List[str]:
    return SUBCATEGORIES.get(category.lower(), [])


def normalize_category(cat: str) -> str:
    c = cat.strip().lower().replace(" ", "-")
    return c if c in CATEGORIES else ""


def expand_categories_with_subs(categories: List[str]) -> Set[str]:
    out: Set[str] = set()
    for c in categories:
        out.add(c.lower())
        for sub in get_subcategories(c):
            out.add(sub)
    return out


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

CATEGORY_WEIGHTS = {
    "electronics": CATEGORY_WEIGHT_ELECTRONICS,
    "fashion": CATEGORY_WEIGHT_FASHION,
    "grocery": CATEGORY_WEIGHT_GROCERY,
    "travel": CATEGORY_WEIGHT_TRAVEL,
    "default": 1.0,
}


def _category_weight(categories: List[str]) -> float:
    w = 1.0
    for c in categories:
        w = max(w, CATEGORY_WEIGHTS.get(c.lower(), 1.0))
    return w


def _tier_multiplier(tier: MerchantTier) -> float:
    if tier == MerchantTier.PREMIUM:
        return 1.15
    if tier == MerchantTier.PARTNER:
        return 1.08
    return 1.0


def _freshness_factor(created_at: datetime) -> float:
    delta = datetime.utcnow() - created_at
    days = delta.total_seconds() / 86400
    if days <= 0:
        return 1.0
    decay = max(0.3, 1.0 - (days / SCORE_DECAY_DAYS) * 0.5)
    return decay


def _type_bonus(coupon_type: CouponType) -> float:
    bonuses = {
        CouponType.PERCENT_OFF: 1.1,
        CouponType.FIXED_OFF: 1.05,
        CouponType.FREE_SHIP: 1.12,
        CouponType.BOGO: 1.08,
        CouponType.CASHBACK: 1.07,
        CouponType.BUNDLE: 1.04,
    }
    return bonuses.get(coupon_type, 1.0)


def compute_coupon_score(
    coupon: Coupon,
    merchant: Merchant,
    query_terms: List[str],
    match_reasons: List[str],
) -> float:
    base = 0.5
    for term in query_terms:
        if term in coupon.description.lower():
            base += 0.15
            match_reasons.append("description_match")
        if term in coupon.code.lower():
            base += 0.1
            match_reasons.append("code_match")
        for cat in merchant.categories:
            if term in cat.lower():
                base += 0.12
                match_reasons.append("category_match")
                break
    base = min(1.0, base)
    base *= _category_weight(merchant.categories)
    base *= _tier_multiplier(merchant.tier)
    base *= _freshness_factor(coupon.created_at)
    base *= _type_bonus(coupon.coupon_type)
    if coupon.is_verified:
        base *= 1.05
    return max(MIN_RELEVANCE_THRESHOLD, base)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def _mock_merchants() -> List[Merchant]:
    now = utc_now()
    return [
        Merchant(
            merchant_id="merchant_zelpha_94",
            name="Zelpha Outpost",
            slug="zelpha-outpost",
            domain="zelpha-outpost.example.com",
            tier=MerchantTier.PREMIUM,
            categories=["electronics", "home"],
            logo_url=None,
            created_at=now,
            updated_at=now,
        ),
        Merchant(
            merchant_id="merchant_vortex_12",
            name="Vortex Gear Co",
            slug="vortex-gear",
            domain="vortex-gear.example.com",
            tier=MerchantTier.STANDARD,
            categories=["fashion", "sports"],
            logo_url=None,
            created_at=now,
            updated_at=now,
        ),
        Merchant(
            merchant_id="merchant_quasar_77",
            name="Quasar Grocers",
            slug="quasar-grocers",
            domain="quasar-grocers.example.com",
            tier=MerchantTier.PARTNER,
            categories=["grocery", "food"],
            logo_url=None,
            created_at=now,
            updated_at=now,
        ),
        Merchant(
            merchant_id="merchant_nova_travel_33",
            name="Nova Travel Hub",
            slug="nova-travel",
            domain="nova-travel.example.com",
            tier=MerchantTier.PREMIUM,
            categories=["travel"],
            logo_url=None,
            created_at=now,
            updated_at=now,
        ),
        Merchant(
            merchant_id="merchant_flux_beauty_55",
            name="Flux Beauty",
            slug="flux-beauty",
            domain="flux-beauty.example.com",
            tier=MerchantTier.STANDARD,
            categories=["beauty", "health"],
            logo_url=None,
            created_at=now,
            updated_at=now,
        ),
    ]


def _mock_coupons(merchants: List[Merchant]) -> List[Coupon]:
    coupons: List[Coupon] = []
    now = utc_now()
