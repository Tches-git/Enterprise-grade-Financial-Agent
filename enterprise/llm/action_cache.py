"""Action result cache for LLM decision reuse.

Caches LLM decisions keyed by a hash of the page's structural DOM and a semantic
fingerprint of the navigation goal. The semantic fingerprint improves reuse when
similar goals are phrased differently.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL = 86400
_DYNAMIC_PATTERNS = [
    re.compile(r'\bid="[^"]*\d{6,}[^"]*"'),
    re.compile(r'\bdata-reactid="[^"]*"'),
    re.compile(r'\bdata-testid="[^"]*"'),
    re.compile(r'\bstyle="[^"]*"'),
    re.compile(r'\bclass="[^"]*"'),
    re.compile(r"<!--[\s\S]*?-->"),
    re.compile(r"\s+"),
]
_COMMENT_PATTERN = re.compile(r"<!--[\s\S]*?-->")
_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+")


def _strip_dynamic_content(dom_html: str) -> str:
    text = _COMMENT_PATTERN.sub("", dom_html)
    for pattern in _DYNAMIC_PATTERNS:
        text = pattern.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def compute_dom_hash(dom_html: str) -> str:
    stripped = _strip_dynamic_content(dom_html)
    return hashlib.sha256(stripped.encode("utf-8")).hexdigest()


def _normalize_goal(navigation_goal: str) -> str:
    tokens = sorted({match.group(0).lower() for match in _WORD_RE.finditer(navigation_goal)})
    return " ".join(tokens)


def compute_goal_hash(navigation_goal: str) -> str:
    normalized = _normalize_goal(navigation_goal)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def compute_semantic_goal_signature(navigation_goal: str) -> str:
    normalized = _normalize_goal(navigation_goal)
    return hashlib.sha256(f"semantic::{normalized}".encode("utf-8")).hexdigest()[:16]


def build_cache_key(org_id: str, dom_hash: str, goal_hash: str) -> str:
    return f"action_cache:{org_id}:{dom_hash}:{goal_hash}"


class ActionCacheStore:
    def __init__(self) -> None:
        self._store: dict[str, tuple[dict[str, Any], float]] = {}
        self._hits = 0
        self._misses = 0
        self._sets = 0

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        value, expires_at = entry
        if datetime.utcnow().timestamp() > expires_at:
            del self._store[key]
            self._misses += 1
            logger.debug("Cache expired: %s", key)
            return None

        self._hits += 1
        logger.info("Cache hit: %s", key)
        return value

    def set(self, key: str, value: dict[str, Any], ttl: int = DEFAULT_CACHE_TTL) -> None:
        expires_at = datetime.utcnow().timestamp() + ttl
        self._store[key] = (value, expires_at)
        self._sets += 1
        logger.info("Cache set: %s (ttl=%ds)", key, ttl)

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear_by_prefix(self, prefix: str) -> int:
        keys_to_delete = [key for key in self._store if key.startswith(prefix)]
        for key in keys_to_delete:
            del self._store[key]
        return len(keys_to_delete)

    def clear_expired(self) -> int:
        now = datetime.utcnow().timestamp()
        expired_keys = [key for key, (_, exp) in self._store.items() if now > exp]
        for key in expired_keys:
            del self._store[key]
        return len(expired_keys)

    def clear_all(self) -> int:
        count = len(self._store)
        self._store.clear()
        return count

    @property
    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = round(self._hits / total * 100, 1) if total > 0 else 0.0
        semantic_groups = len({key.rsplit(":", 1)[-1] for key in self._store})
        return {
            "total_entries": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "sets": self._sets,
            "semantic_groups": semantic_groups,
        }

    def reset_stats(self) -> None:
        self._hits = 0
        self._misses = 0
        self._sets = 0


_cache_store = ActionCacheStore()


def get_cache_store() -> ActionCacheStore:
    return _cache_store


def configure_cache_store(store: ActionCacheStore) -> None:
    global _cache_store
    _cache_store = store


def cache_action_decision(
    org_id: str,
    dom_html: str,
    navigation_goal: str,
    decision: dict[str, Any],
    ttl: int = DEFAULT_CACHE_TTL,
) -> str:
    dom_hash = compute_dom_hash(dom_html)
    goal_hash = compute_goal_hash(navigation_goal)
    semantic_signature = compute_semantic_goal_signature(navigation_goal)
    key = build_cache_key(org_id, dom_hash, f"{goal_hash}:{semantic_signature}")
    payload = dict(decision)
    payload.setdefault("semantic_signature", semantic_signature)
    payload.setdefault("goal_hash", goal_hash)
    _cache_store.set(key, payload, ttl)
    return key


def lookup_cached_decision(
    org_id: str,
    dom_html: str,
    navigation_goal: str,
) -> dict[str, Any] | None:
    dom_hash = compute_dom_hash(dom_html)
    goal_hash = compute_goal_hash(navigation_goal)
    semantic_signature = compute_semantic_goal_signature(navigation_goal)
    key = build_cache_key(org_id, dom_hash, f"{goal_hash}:{semantic_signature}")
    cached = _cache_store.get(key)
    if cached is not None:
        return cached

    prefix = build_cache_key(org_id, dom_hash, "")
    for existing_key, (value, expires_at) in list(_cache_store._store.items()):
        if not existing_key.startswith(prefix):
            continue
        if datetime.utcnow().timestamp() > expires_at:
            del _cache_store._store[existing_key]
            continue
        if value.get("semantic_signature") == semantic_signature:
            _cache_store._hits += 1
            logger.info("Semantic cache hit: %s", existing_key)
            return value

    _cache_store._misses += 1
    return None


def explain_cache_key(org_id: str, dom_html: str, navigation_goal: str) -> dict[str, str]:
    dom_hash = compute_dom_hash(dom_html)
    goal_hash = compute_goal_hash(navigation_goal)
    semantic_signature = compute_semantic_goal_signature(navigation_goal)
    cache_key = build_cache_key(org_id, dom_hash, f"{goal_hash}:{semantic_signature}")
    return {
        "dom_hash": dom_hash,
        "goal_hash": goal_hash,
        "semantic_signature": semantic_signature,
        "cache_key": cache_key,
    }
