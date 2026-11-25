"""Artisan Stock Production System (Config-Driven, Modular).

Manages Lord-configured production quotas per artisan product, tracks
ready stock across chests/markets/ground/stored furniture, and feeds
proactive crafting tasks to Toolmakers and Builders alongside existing
commission workflows.
"""

import math
from game.data.config import (
    DEDICATED_JOBS,
    DEFAULT_ITEM_PRICES,
    FURNITURE_TYPES,
    PRODUCTION_BUILDER_FURNITURE_IDS,
    PRODUCTION_DEFAULT_QUOTA,
    PRODUCTION_QUOTA_MAX,
    PRODUCTION_QUOTA_STEP,
    TILE_SIZE,
    TOOLMAKER_TOOL_RECIPE,
    TOOL_TYPES,
)


class ProductionSystem:
    """Stateless helper operating on building_manager.production_quotas."""

    @classmethod
    def get_workstation_types(cls):
        """Return workstation furniture types used by active production artisans."""
        types = set()
        for job_id in ("Toolmaker", "Builder"):
            wt = DEDICATED_JOBS.get(job_id, {}).get("workplace_furniture_type")
            if wt:
                types.add(wt)
        return types

    @classmethod
    def get_catalog(cls):
        """Build the producible item catalog dynamically from TOOL_TYPES and FURNITURE_TYPES."""
        items = []
        for tool_id, cfg in TOOL_TYPES.items():
            items.append({
                "id": tool_id,
                "name": cfg.get("name", tool_id.replace("_", " ")),
                "artisan": "Toolmaker",
                "category": "Tool",
                "kind": "tool",
                "recipe": {k: int(v) for k, v in TOOLMAKER_TOOL_RECIPE.items() if int(v) > 0},
                "base_price": int(DEFAULT_ITEM_PRICES.get(tool_id, 10)),
            })

        for furn_id in PRODUCTION_BUILDER_FURNITURE_IDS:
            cfg = FURNITURE_TYPES.get(furn_id)
            if not cfg:
                continue
            raw_cat = cfg.get("category_id", "furniture")
            cat_label = {
                "public_structure": "Civic",
                "workplace": "Workstation",
                "furniture": "Furniture",
            }.get(raw_cat, raw_cat.replace("_", " ").title())
            items.append({
                "id": furn_id,
                "name": cfg.get("name", furn_id.replace("_", " ").title()),
                "artisan": "Builder",
                "category": cat_label,
                "kind": "furniture",
                "recipe": {k: int(v) for k, v in (cfg.get("materials", {}) or {}).items() if int(v) > 0},
                "base_price": int(DEFAULT_ITEM_PRICES.get(furn_id, 10)),
            })
        return items

    @classmethod
    def get_quota_map(cls, building_manager):
        if building_manager is None:
            return {}
        quotas = getattr(building_manager, "production_quotas", None)
        if not isinstance(quotas, dict):
            quotas = {}
            building_manager.production_quotas = quotas
        return quotas

    @classmethod
    def get_quota(cls, building_manager, item_id):
        quotas = cls.get_quota_map(building_manager)
        return max(0, int(quotas.get(item_id, PRODUCTION_DEFAULT_QUOTA) or 0))

    @classmethod
    def set_quota(cls, building_manager, item_id, qty):
        quotas = cls.get_quota_map(building_manager)
        clamped = max(0, min(int(PRODUCTION_QUOTA_MAX), int(qty)))
        quotas[item_id] = clamped
        return clamped

    @classmethod
    def adjust_quota(cls, building_manager, item_id, delta=PRODUCTION_QUOTA_STEP):
        cur = cls.get_quota(building_manager, item_id)
        return cls.set_quota(building_manager, item_id, cur + int(delta))

    @classmethod
    def get_current_stock(cls, item_id, furniture_manager=None, building_manager=None,
                          stockpile_manager=None):
        """Count ready commercial stock at artisan workstations and market stalls.

        Personal household chests are intentionally excluded so tools actively
        owned/used by villagers are never counted as sellable stock.
        """
        total = 0
        workstation_types = cls.get_workstation_types()

        if furniture_manager:
            for f in getattr(furniture_manager, "furnitures", []):
                if getattr(f, "furniture_type", "") not in workstation_types:
                    continue
                if getattr(f, "is_dropped", False) or getattr(f, "stored_in_id", None) is not None:
                    continue
                inv = getattr(f, "inventory", None)
                if isinstance(inv, dict):
                    total += max(0, int(inv.get(item_id, 0) or 0))

        if building_manager:
            for b in getattr(building_manager, "buildings", []):
                if getattr(b, "building_type", "") != "market" or getattr(b, "is_under_construction", False):
                    continue
                inv = getattr(b, "inventory", None)
                if isinstance(inv, dict):
                    total += max(0, int(inv.get(item_id, 0) or 0))

        return total

    @classmethod
    def get_next_needed_product(cls, artisan_job, building_manager, furniture_manager=None,
                                stockpile_manager=None):
        """Return the highest-priority catalog item for artisan_job with stock < quota."""
        candidates = []
        for entry in cls.get_catalog():
            if entry["artisan"] != artisan_job:
                continue
            item_id = entry["id"]
            quota = cls.get_quota(building_manager, item_id)
            if quota <= 0:
                continue
            stock = cls.get_current_stock(
                item_id,
                furniture_manager=furniture_manager,
                building_manager=building_manager,
                stockpile_manager=stockpile_manager,
            )
            if stock < quota:
                fill_ratio = float(stock) / float(quota)
                candidates.append((fill_ratio, stock, entry))
        if not candidates:
            return None
        candidates.sort(key=lambda c: (c[0], c[1], c[2]["name"]))
        return candidates[0][2]

    @classmethod
    def store_crafted_product(cls, worker, item_id, furniture_manager=None,
                              building_manager=None, stockpile_manager=None,
                              permit_manager=None, workbench=None):
        """Store 1 crafted product directly into the artisan's workstation inventory."""
        target_bench = workbench
        if target_bench is None and furniture_manager is not None:
            job_id = getattr(worker, "job", None)
            wtype = DEDICATED_JOBS.get(job_id, {}).get("workplace_furniture_type")
            benches = [
                f for f in getattr(furniture_manager, "furnitures", [])
                if (wtype is None or getattr(f, "furniture_type", "") == wtype)
                and getattr(f, "furniture_type", "") in cls.get_workstation_types()
                and not getattr(f, "is_dropped", False)
                and getattr(f, "stored_in_id", None) is None
            ]
            if benches:
                wx, wy = getattr(worker, "x", 0.0), getattr(worker, "y", 0.0)
                target_bench = min(
                    benches,
                    key=lambda b: math.hypot(
                        b.get_world_pos(TILE_SIZE)[0] - wx,
                        b.get_world_pos(TILE_SIZE)[1] - wy,
                    ),
                )
        if target_bench is not None and hasattr(target_bench, "store_item"):
            target_bench.store_item(item_id, 1)
            return True
        return False
