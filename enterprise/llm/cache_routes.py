"""Cache management API routes (admin-only).

Provides endpoints for inspecting and managing the action decision cache.
"""

from fastapi import APIRouter, Depends

from enterprise.auth.dependencies import require_admin
from enterprise.auth.schemas import UserContext

from .action_cache import explain_cache_key, get_cache_store

router = APIRouter(prefix="/enterprise/cache", tags=["cache"])


@router.get("/stats")
async def cache_stats(
    user: UserContext = Depends(require_admin),
) -> dict:
    store = get_cache_store()
    return store.stats


@router.delete("/task/{task_id}")
async def clear_task_cache(
    task_id: str,
    user: UserContext = Depends(require_admin),
) -> dict:
    store = get_cache_store()
    prefix = f"action_cache:{user.org_id}:"
    removed = store.clear_by_prefix(prefix)
    return {"removed": removed, "task_id": task_id}


@router.delete("/expired")
async def clear_expired_cache(
    user: UserContext = Depends(require_admin),
) -> dict:
    store = get_cache_store()
    removed = store.clear_expired()
    return {"removed": removed}


@router.delete("/all")
async def clear_all_cache(
    user: UserContext = Depends(require_admin),
) -> dict:
    store = get_cache_store()
    removed = store.clear_all()
    return {"removed": removed}


@router.post("/reset-stats")
async def reset_cache_stats(
    user: UserContext = Depends(require_admin),
) -> dict:
    store = get_cache_store()
    store.reset_stats()
    return {"status": "ok"}


@router.post("/explain")
async def explain_cache(
    payload: dict,
    user: UserContext = Depends(require_admin),
) -> dict:
    return explain_cache_key(
        org_id=user.org_id,
        dom_html=payload.get("dom_html", ""),
        navigation_goal=payload.get("navigation_goal", ""),
    )
