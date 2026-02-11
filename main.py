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
    expires = now + timedelta(days=30)
    for i, m in enumerate(merchants):
        code = f"BT69_{m.slug.upper()}_{1000 + i}"
        cid = hash_coupon_id(m.merchant_id, code, now.timestamp())
        coupons.append(
            Coupon(
                coupon_id=cid,
                merchant_id=m.merchant_id,
                code=code,
                description=f"Save on {m.name} orders — limited time.",
                coupon_type=CouponType.PERCENT_OFF,
                value=15.0,
                currency="USD",
                min_purchase=25.0,
                max_discount=50.0,
                expires_at=expires,
                is_verified=(i % 2 == 0),
                use_count=0,
                created_at=now,
                updated_at=now,
                tags=["welcome", "general"],
            )
        )
        code2 = f"SHIPFREE{i}"
        cid2 = hash_coupon_id(m.merchant_id, code2, now.timestamp() + 1)
        coupons.append(
            Coupon(
                coupon_id=cid2,
                merchant_id=m.merchant_id,
                code=code2,
                description="Free standard shipping on orders over $49.",
                coupon_type=CouponType.FREE_SHIP,
                value=0,
                currency="USD",
                min_purchase=49.0,
                expires_at=expires,
                is_verified=True,
                use_count=0,
                created_at=now,
                updated_at=now,
                tags=["shipping"],
            )
        )
    return coupons


def load_mock_merchants() -> List[Merchant]:
    return _mock_merchants()


def load_mock_coupons() -> List[Coupon]:
    return _mock_coupons(_mock_merchants())


# ---------------------------------------------------------------------------
# AI engine
# ---------------------------------------------------------------------------


class CouponAIEngine:
    def __init__(self, store: CouponStore) -> None:
        self._store = store

    def search(self, request: SearchRequest) -> List[SearchResult]:
        query_terms = [t for t in request.query.lower().split() if len(t) >= 2]
        if not query_terms:
            return []
        candidates: List[Coupon] = []
        if request.merchant_ids:
            for mid in request.merchant_ids:
                candidates.extend(self._store.get_coupons_by_merchant(mid))
        elif request.categories:
            expanded = expand_categories_with_subs(request.categories)
            for cat in expanded:
                candidates.extend(self._store.get_coupons_by_category(cat))
            candidates = list({c.coupon_id: c for c in candidates}.values())
        else:
            candidates = self._store.list_all_coupons(limit=500)
        if request.coupon_types:
            type_set = set(request.coupon_types)
            candidates = [c for c in candidates if c.coupon_type in type_set]
        results: List[SearchResult] = []
        seen_ids: set = set()
        for coupon in candidates:
            if coupon.coupon_id in seen_ids:
                continue
            merchant = self._store.get_merchant(coupon.merchant_id)
            if not merchant:
                continue
            match_reasons: List[str] = []
            score = compute_coupon_score(coupon, merchant, query_terms, match_reasons)
            if not match_reasons and not request.categories:
                match_reasons.append("general_match")
            results.append(SearchResult(coupon=coupon, score=score, match_reasons=match_reasons))
            seen_ids.add(coupon.coupon_id)
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:MAX_COUPONS_PER_QUERY]
        page_size = max(1, request.page_size)
        page = max(1, request.page)
        start = (page - 1) * page_size
        return results[start : start + page_size]

    def suggest_for_merchant(self, merchant_id: str, limit: int = 5) -> List[SearchResult]:
        coupons = self._store.get_coupons_by_merchant(merchant_id)
        merchant = self._store.get_merchant(merchant_id)
        if not merchant:
            return []
        out: List[SearchResult] = []
        for c in coupons[: limit * 2]:
            reasons: List[str] = ["merchant_suggestion"]
            score = compute_coupon_score(c, merchant, [merchant.name], reasons)
            out.append(SearchResult(coupon=c, score=score, match_reasons=reasons))
        out.sort(key=lambda r: r.score, reverse=True)
        return out[:limit]

    def suggest_by_category(self, category: str, limit: int = 10) -> List[SearchResult]:
        categories = validate_categories([category])
        if not categories:
            return []
        req = SearchRequest(query=category, categories=categories, page_size=limit)
        return self.search(req)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class InMemoryRateLimiter:
    def __init__(self, requests_per_minute: int = RATE_LIMIT_REQUESTS_PER_MINUTE) -> None:
        self._rpm = requests_per_minute
        self._counts: defaultdict = defaultdict(list)

    def _trim(self, key: str) -> None:
        now = time.time()
        cutoff = now - 60
        self._counts[key] = [t for t in self._counts[key] if t > cutoff]

    def allow(self, key: str) -> bool:
        self._trim(key)
        if len(self._counts[key]) >= self._rpm:
            return False
        self._counts[key].append(time.time())
        return True

    def remaining(self, key: str) -> int:
        self._trim(key)
        return max(0, self._rpm - len(self._counts[key]))


def rate_limit_middleware(limiter: InMemoryRateLimiter, get_key: Callable[[Any], str]):
    def wrapper(handler):
        def inner(request: Any) -> Any:
            key = get_key(request)
            if not limiter.allow(key):
                return {"success": False, "error": "Rate limit exceeded", "code": "RATE_LIMIT"}
            return handler(request)
        return inner
    return wrapper


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TTLCache:
    def __init__(self, ttl_seconds: int, max_entries: int = 1000) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._data: dict = {}
        self._expiry: dict = {}

    def get(self, key: str) -> Optional[Any]:
        if key not in self._data:
            return None
        if time.time() > self._expiry.get(key, 0):
            self._data.pop(key, None)
            self._expiry.pop(key, None)
            return None
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        if len(self._data) >= self._max:
            oldest = min(self._expiry, key=self._expiry.get)
            self._data.pop(oldest, None)
            self._expiry.pop(oldest, None)
        self._data[key] = value
        self._expiry[key] = time.time() + self._ttl

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)
        self._expiry.pop(key, None)

    def clear(self) -> None:
        self._data.clear()
        self._expiry.clear()


def coupons_cache() -> TTLCache:
    return TTLCache(ttl_seconds=CACHE_TTL_COUPONS, max_entries=500)


def merchants_cache() -> TTLCache:
    return TTLCache(ttl_seconds=CACHE_TTL_MERCHANTS, max_entries=200)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@dataclass
class SearchEvent:
    query: str
    result_count: int
    categories: List[str]
    timestamp: datetime = field(default_factory=utc_now)


@dataclass
class RedemptionEvent:
    coupon_id: str
    merchant_id: str
    value: float
    timestamp: datetime = field(default_factory=utc_now)


class AnalyticsAggregator:
    def __init__(self) -> None:
        self._search_events: List[SearchEvent] = []
        self._redemption_events: List[RedemptionEvent] = []
        self._query_counts: Dict[str, int] = {}
        self._merchant_redemption_totals: Dict[str, float] = {}

    def record_search(self, query: str, result_count: int, categories: List[str]) -> None:
        self._search_events.append(
            SearchEvent(query=query, result_count=result_count, categories=categories)
        )
        self._query_counts[query.lower()] = self._query_counts.get(query.lower(), 0) + 1

    def record_redemption(self, coupon_id: str, merchant_id: str, value: float) -> None:
        self._redemption_events.append(
            RedemptionEvent(coupon_id=coupon_id, merchant_id=merchant_id, value=value)
        )
        self._merchant_redemption_totals[merchant_id] = (
            self._merchant_redemption_totals.get(merchant_id, 0) + value
        )

    def total_searches(self) -> int:
        return len(self._search_events)

    def total_redemptions(self) -> int:
        return len(self._redemption_events)

    def top_queries(self, n: int = 10) -> List[tuple]:
        return sorted(self._query_counts.items(), key=lambda x: x[1], reverse=True)[:n]

    def merchant_redemption_summary(self) -> Dict[str, float]:
        return dict(self._merchant_redemption_totals)

    def clear(self) -> None:
        self._search_events.clear()
        self._redemption_events.clear()
        self._query_counts.clear()
        self._merchant_redemption_totals.clear()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_coupons_json(coupons: List[Coupon]) -> str:
    return json.dumps([serialize_coupon(c) for c in coupons], indent=2)


def export_merchants_json(merchants: List[Merchant]) -> str:
    return json.dumps([serialize_merchant(m) for m in merchants], indent=2)


def export_coupons_csv(coupons: List[Coupon]) -> str:
    if not coupons:
        return ""
    out = io.StringIO()
    first = serialize_coupon(coupons[0])
    writer = csv.DictWriter(out, fieldnames=first.keys())
    writer.writeheader()
    for c in coupons:
        row = serialize_coupon(c)
        row["created_at"] = row["created_at"].replace("T", " ") if row.get("created_at") else ""
        row["updated_at"] = row["updated_at"].replace("T", " ") if row.get("updated_at") else ""
        row["expires_at"] = row["expires_at"].replace("T", " ") if row.get("expires_at") else ""
        writer.writerow(row)
    return out.getvalue()


def export_merchants_csv(merchants: List[Merchant]) -> str:
    if not merchants:
        return ""
    out = io.StringIO()
    first = serialize_merchant(merchants[0])
    writer = csv.DictWriter(out, fieldnames=first.keys())
    writer.writeheader()
    for m in merchants:
        row = serialize_merchant(m)
        row["created_at"] = row["created_at"].replace("T", " ") if row.get("created_at") else ""
        row["updated_at"] = row["updated_at"].replace("T", " ") if row.get("updated_at") else ""
        writer.writerow(row)
    return out.getvalue()


# ---------------------------------------------------------------------------
# API server (singletons + handlers)
# ---------------------------------------------------------------------------

_store: Optional[CouponStore] = None
_engine: Optional[CouponAIEngine] = None
_limiter: Optional[InMemoryRateLimiter] = None


def _create_store_with_seed() -> CouponStore:
    store = CouponStore()
    for m in load_mock_merchants():
        store.add_merchant(m)
    for c in load_mock_coupons():
        store.add_coupon(c)
    return store


def get_store() -> CouponStore:
    global _store
    if _store is None:
        _store = _create_store_with_seed()
    return _store


def get_engine() -> CouponAIEngine:
    global _engine
    if _engine is None:
        _engine = CouponAIEngine(get_store())
    return _engine


def get_limiter() -> InMemoryRateLimiter:
    global _limiter
    if _limiter is None:
        cfg = get_config()
        _limiter = InMemoryRateLimiter(requests_per_minute=cfg.rate_limit_rpm)
    return _limiter


def _get_client_key(environ: dict) -> str:
    return environ.get("REMOTE_ADDR", "unknown")


# ---------------------------------------------------------------------------
# WSGI application
# ---------------------------------------------------------------------------


def _parse_path(path: str) -> Tuple[str, List[str]]:
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "", []
    return parts[0], parts[1:]


def _read_body(environ: dict) -> bytes:
    body = b""
    if environ.get("REQUEST_METHOD", "GET").upper() in ("POST", "PUT", "PATCH"):
        try:
            length = int(environ.get("CONTENT_LENGTH", 0))
            if length:
                body = environ["wsgi.input"].read(length)
        except (ValueError, KeyError):
            pass
    return body


def _json_response(data: dict) -> bytes:
    return json.dumps(data).encode("utf-8")


def application(environ: dict, start_response: Callable) -> List[bytes]:
    path_info = environ.get("PATH_INFO", "") or "/"
    method = environ.get("REQUEST_METHOD", "GET").upper()
    base, rest = _parse_path(path_info)
    key = _get_client_key(environ)
    if not get_limiter().allow(key):
        start_response("429 Too Many Requests", [("Content-Type", "application/json")])
        return [_json_response({"success": False, "error": "Rate limit exceeded"})]
    if base == "search" and method == "POST":
        body = _read_body(environ)
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            start_response("400 Bad Request", [("Content-Type", "application/json")])
            return [_json_response({"success": False, "error": "Invalid JSON"})]
        query = (data.get("query") or "").strip()
        if not query:
            start_response("400 Bad Request", [("Content-Type", "application/json")])
            return [_json_response({"success": False, "error": "Missing query"})]
        page = validate_page(int(data.get("page", 1)))
        page_size = validate_page_size(int(data.get("page_size", 12)))
        categories = validate_categories(data.get("categories"))
        types_raw = data.get("coupon_types")
        coupon_types = None
        if types_raw and isinstance(types_raw, list):
            try:
                coupon_types = [CouponType(t) for t in types_raw]
            except ValueError:
                pass
        req = SearchRequest(
            query=query,
            categories=categories if categories else None,
            merchant_ids=data.get("merchant_ids"),
            coupon_types=coupon_types,
            page=page,
            page_size=page_size,
        )
        results = get_engine().search(req)
        payload = {"success": True, "results": serialize_search_results(results), "page": page, "page_size": page_size}
        start_response("200 OK", [("Content-Type", "application/json")])
        return [_json_response(payload)]
    if base == "merchants" and method == "GET":
        store = get_store()
        qs = environ.get("QUERY_STRING", "")
        limit_str = "50"
        for part in qs.split("&"):
            if part.startswith("limit="):
                limit_str = part.split("=", 1)[1]
                break
        limit = validate_page_size(int(limit_str or "50"), 100)
        merchants = store.list_merchants(limit=limit)
        payload = {"success": True, "merchants": [serialize_merchant(m) for m in merchants]}
        start_response("200 OK", [("Content-Type", "application/json")])
        return [_json_response(payload)]
    if base == "coupons" and len(rest) == 1 and method == "GET":
        coupon = get_store().get_coupon(rest[0])
        if not coupon:
            start_response("404 Not Found", [("Content-Type", "application/json")])
            return [_json_response({"success": False, "error": "Coupon not found"})]
        payload = {"success": True, "coupon": serialize_coupon(coupon)}
        start_response("200 OK", [("Content-Type", "application/json")])
        return [_json_response(payload)]
    if base == "suggest" and len(rest) == 1 and method == "GET":
        results = get_engine().suggest_for_merchant(rest[0], limit=10)
        payload = {"success": True, "suggestions": serialize_search_results(results)}
        start_response("200 OK", [("Content-Type", "application/json")])
        return [_json_response(payload)]
    if base == "health" and method == "GET":
        start_response("200 OK", [("Content-Type", "application/json")])
        return [_json_response({"status": "ok", "service": "BitkoopTurbo69"})]
    start_response("404 Not Found", [("Content-Type", "application/json")])
    return [_json_response({"success": False, "error": "Not found"})]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_store() -> CouponStore:
    store = CouponStore()
    for m in load_mock_merchants():
        store.add_merchant(m)
    for c in load_mock_coupons():
        store.add_coupon(c)
    return store


def cmd_search(store: CouponStore, engine: CouponAIEngine, args: argparse.Namespace) -> int:
    req = SearchRequest(
        query=args.query,
        categories=args.categories.split(",") if args.categories else None,
        page=args.page,
        page_size=args.page_size,
    )
    results = engine.search(req)
    out = serialize_search_results(results)
    print(json.dumps({"results": out, "count": len(out)}, indent=2))
    return 0


def cmd_merchants(store: CouponStore, args: argparse.Namespace) -> int:
    merchants = store.list_merchants(limit=args.limit)
    print(json.dumps({"merchants": [serialize_merchant(m) for m in merchants]}, indent=2))
    return 0


def cmd_coupons(store: CouponStore, args: argparse.Namespace) -> int:
    coupons = store.list_all_coupons(limit=args.limit)
    print(json.dumps({"coupons": [serialize_coupon(c) for c in coupons]}, indent=2))
    return 0


def cmd_seed(store: CouponStore, args: argparse.Namespace) -> int:
    print("Seed data already loaded in-memory. Merchants:", store.merchant_count(), "Coupons:", store.coupon_count())
    return 0


def cli_main() -> int:
    parser = argparse.ArgumentParser(prog="bitkoop-turbo69", description="BitkoopTurbo69 AI coupon assistant CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    search_p = sub.add_parser("search", help="Search coupons by query")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("--categories", default=None, help="Comma-separated categories")
    search_p.add_argument("--page", type=int, default=1)
    search_p.add_argument("--page-size", type=int, default=12, dest="page_size")
    mer_p = sub.add_parser("merchants", help="List merchants")
    mer_p.add_argument("--limit", type=int, default=50)
    coup_p = sub.add_parser("coupons", help="List coupons")
    coup_p.add_argument("--limit", type=int, default=50)
    sub.add_parser("seed", help="Show seed stats")
    args = parser.parse_args()
    store = _build_store()
    engine = CouponAIEngine(store)
    if args.command == "search":
        return cmd_search(store, engine, args)
    if args.command == "merchants":
        return cmd_merchants(store, args)
    if args.command == "coupons":
        return cmd_coupons(store, args)
    if args.command == "seed":
        return cmd_seed(store, args)
    return 1


# ---------------------------------------------------------------------------
# Run (API server or Shopping God static)
# ---------------------------------------------------------------------------


def _run_wsgi() -> None:
    try:
        from wsgiref.simple_server import make_server
    except ImportError:
        print("wsgiref not available; install Python standard library.", file=sys.stderr)
        sys.exit(1)
    cfg = get_config()
    host, port = cfg.api_host, cfg.api_port
    with make_server(host, port, application) as httpd:
        print(f"BitkoopTurbo69 API on http://{host}:{port}")
        httpd.serve_forever()


def _run_shopping_god_static() -> None:
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shopping-god")
    if not os.path.isdir(root):
        print("shopping-god directory not found.", file=sys.stderr)
        sys.exit(1)
    try:
        import http.server
        import webbrowser
    except ImportError:
        sys.exit(1)
    os.chdir(root)
    port = 8948
    handler = http.server.SimpleHTTPRequestHandler
    with http.server.HTTPServer(("", port), handler) as httpd:
        url = f"http://127.0.0.1:{port}"
        print(f"Shopping God at {url}")
        webbrowser.open(url)
        httpd.serve_forever()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    if mode == "web" or mode == "shopping-god":
        _run_shopping_god_static()
    elif mode == "cli":
        sys.exit(cli_main())
    else:
        _run_wsgi()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("search", "merchants", "coupons", "seed"):
        sys.exit(cli_main())
    main()
