"""
Village Wealth System (AGENT 2 & AGENT 3 Integration)
Calculates and provides the centralized economic single source of truth for all coin wealth
across the village: Landlord Crown Treasury and individual peasant households.
Zero hardcoding, zero duplicate coin counting.
"""
import time
from game.systems.currency import (
    to_copper,
    from_copper,
    normalize_wallet,
    canonical_denomination,
    CURRENCY_DENOMINATIONS
)

HOUSEHOLD_PALETTE = [
    (34, 197, 94),   # Emerald green
    (245, 158, 11),  # Amber
    (168, 85, 247),  # Purple
    (236, 72, 153),  # Pink
    (14, 165, 233),  # Sky blue
    (20, 184, 166),  # Teal
    (249, 115, 22),  # Orange
    (139, 92, 246),  # Violet
]


class VillageWealthSystem:
    _cached_result = None
    _is_dirty = True
    _last_calc_time = 0.0
    CACHE_LIFETIME = 0.25  # In-game / UI caching threshold (250ms)

    @classmethod
    def mark_dirty(cls):
        """Marks cached wealth data dirty, forcing recomputation on next request."""
        cls._is_dirty = True

    @classmethod
    def invalidate_cache(cls):
        """Alias for mark_dirty."""
        cls._is_dirty = True

    @classmethod
    def calculate_village_wealth(cls, resources=None, villager_manager=None, furniture_manager=None,
                                 building_manager=None, stockpile_manager=None, force_recompute=False):
        """
        Aggregates actual physical coin ownership across the village without duplication.
        Crucial: Household Possession is a mirrored record; we read directly from the
        actual authoritative physical coin containers (chests, member pockets, market treasuries,
        and dropped ground stacks) exactly once.

        Returns:
            dict containing:
            - total_wealth_copper: int
            - total_wallet: {"Gold": int, "Silver": int, "Copper": int}
            - landlord: dict(name, wealth_copper, wallet, percentage, share_pct, color)
            - households: list of dict(id, family_id, name, wealth_copper, wallet, percentage, share_pct, color)
        """
        now = time.time()
        if not force_recompute and not cls._is_dirty and cls._cached_result is not None:
            if now - cls._last_calc_time < cls.CACHE_LIFETIME:
                return cls._cached_result

        # 1. LANDLORD WEALTH
        ll_wallet = {"Copper": 0, "Silver": 0, "Gold": 0}

        # A. Coins in Landlord resource store / Crown Treasury
        if resources is not None and isinstance(resources, dict):
            for k, amt in resources.items():
                canon = canonical_denomination(k)
                if canon:
                    ll_wallet[canon] += max(0, int(amt))
        elif stockpile_manager:
            # Fallback if resources dict not passed: read landlord physical stacks
            for s in getattr(stockpile_manager, "stacks", []):
                if getattr(s, "owner_type", "landlord") == "landlord":
                    canon = canonical_denomination(getattr(s, "resource_type", ""))
                    if canon:
                        ll_wallet[canon] += max(0, int(getattr(s, "amount", 0)))

        # B. Coins in Unassigned (Landlord-owned) Market Stalls
        if building_manager:
            for b in getattr(building_manager, "buildings", []):
                if getattr(b, "building_type", "") == "market":
                    assigned_fam = getattr(b, "assigned_household_id", None) or getattr(b, "assigned_family_id", None)
                    if not assigned_fam:
                        mkt_curr = normalize_wallet(getattr(b, "currency", {}))
                        for denom in ("Copper", "Silver", "Gold"):
                            ll_wallet[denom] += mkt_curr[denom]

        ll_copper = to_copper(ll_wallet)

        # 2. PEASANT HOUSEHOLDS WEALTH
        households = []
        if villager_manager:
            families = getattr(villager_manager, "families", [])
            for idx, fam in enumerate(families):
                fam_id_str = str(getattr(fam, "id", ""))
                fam_wallet = {"Copper": 0, "Silver": 0, "Gold": 0}
                visited_chests = set()

                # A. Coins in Household Storage Furniture (chests)
                if furniture_manager:
                    furn_list = getattr(furniture_manager, "furnitures", getattr(furniture_manager, "furniture", []))
                    for furn in furn_list:
                        if str(getattr(furn, "family_id", "")) == fam_id_str:
                            visited_chests.add(id(furn))
                            # Check currency container if separate
                            if hasattr(furn, "currency") and isinstance(furn.currency, dict):
                                f_curr = normalize_wallet(furn.currency)
                                for denom in ("Copper", "Silver", "Gold"):
                                    fam_wallet[denom] += f_curr[denom]
                            # Check inventory dict for coins (avoid double-counting if identical to currency)
                            if hasattr(furn, "inventory") and isinstance(furn.inventory, dict):
                                if getattr(furn, "inventory") is not getattr(furn, "currency", None):
                                    for item_name, count in furn.inventory.items():
                                        canon = canonical_denomination(item_name)
                                        if canon and canon not in getattr(furn, "currency", {}):
                                            fam_wallet[canon] += max(0, int(count))

                    # Fallback lookup by method
                    if hasattr(furniture_manager, "get_storage_for_family"):
                        st = furniture_manager.get_storage_for_family(fam_id_str)
                        if st and id(st) not in visited_chests:
                            if hasattr(st, "currency") and isinstance(st.currency, dict):
                                f_curr = normalize_wallet(st.currency)
                                for denom in ("Copper", "Silver", "Gold"):
                                    fam_wallet[denom] += f_curr[denom]
                            if hasattr(st, "inventory") and isinstance(st.inventory, dict):
                                if getattr(st, "inventory") is not getattr(st, "currency", None):
                                    for item_name, count in st.inventory.items():
                                        canon = canonical_denomination(item_name)
                                        if canon and canon not in getattr(st, "currency", {}):
                                            fam_wallet[canon] += max(0, int(count))

                # B. Coins physically carried in member pockets / personal inventories
                for m in getattr(fam, "members", []):
                    counted_denoms = set()
                    # Wallet / currency dict
                    if hasattr(m, "currency") and isinstance(m.currency, dict):
                        m_curr = normalize_wallet(m.currency)
                        for denom in ("Copper", "Silver", "Gold"):
                            fam_wallet[denom] += m_curr[denom]
                            if m_curr[denom] > 0:
                                counted_denoms.add(denom)
                    elif hasattr(m, "wallet") and isinstance(m.wallet, dict):
                        m_w = normalize_wallet(m.wallet)
                        for denom in ("Copper", "Silver", "Gold"):
                            fam_wallet[denom] += m_w[denom]
                            if m_w[denom] > 0:
                                counted_denoms.add(denom)

                    # Personal inventory dict (ensure no double-counting with currency/wallet)
                    if hasattr(m, "inventory") and isinstance(m.inventory, dict):
                        if getattr(m, "inventory") is not getattr(m, "currency", None) and \
                           getattr(m, "inventory") is not getattr(m, "wallet", None):
                            for item_name, count in m.inventory.items():
                                canon = canonical_denomination(item_name)
                                if canon and canon not in counted_denoms:
                                    fam_wallet[canon] += max(0, int(count))

                # C. Coins in Market Stalls assigned to this household
                if building_manager:
                    for b in getattr(building_manager, "buildings", []):
                        if getattr(b, "building_type", "") == "market":
                            b_fam = getattr(b, "assigned_household_id", None) or getattr(b, "assigned_family_id", None)
                            if str(b_fam) == fam_id_str:
                                mkt_curr = normalize_wallet(getattr(b, "currency", {}))
                                for denom in ("Copper", "Silver", "Gold"):
                                    fam_wallet[denom] += mkt_curr[denom]

                # D. Dropped coins on ground owned by this household
                if stockpile_manager:
                    member_ids = {str(m.id) for m in getattr(fam, "members", [])}
                    for s in getattr(stockpile_manager, "stacks", []):
                        if getattr(s, "owner_type", None) == "villager":
                            s_owner = str(getattr(s, "owner_id", ""))
                            if s_owner == fam_id_str or s_owner in member_ids:
                                canon = canonical_denomination(getattr(s, "resource_type", ""))
                                if canon:
                                    fam_wallet[canon] += max(0, int(getattr(s, "amount", 0)))

                fam_copper = to_copper(fam_wallet)
                col = HOUSEHOLD_PALETTE[idx % len(HOUSEHOLD_PALETTE)]

                households.append({
                    "id": fam.id,
                    "family_id": fam.id,
                    "name": f"The {fam.surname} Family",
                    "wealth_copper": fam_copper,
                    "wallet": fam_wallet,
                    "color": col,
                    "percentage": 0.0,
                    "share_pct": 0.0
                })

        # 3. TOTAL VILLAGE WEALTH & SHARE PERCENTAGES
        total_copper = ll_copper + sum(hh["wealth_copper"] for hh in households)

        if total_copper > 0:
            ll_pct = round((ll_copper / total_copper) * 100.0, 1)
            for hh in households:
                p = round((hh["wealth_copper"] / total_copper) * 100.0, 1)
                hh["percentage"] = p
                hh["share_pct"] = p
        else:
            ll_pct = 0.0
            for hh in households:
                hh["percentage"] = 0.0
                hh["share_pct"] = 0.0

        result = {
            "total_wealth_copper": total_copper,
            "total_wallet": from_copper(total_copper),
            "landlord": {
                "name": "Landlord (Crown Treasury)",
                "wealth_copper": ll_copper,
                "wallet": ll_wallet,
                "percentage": ll_pct,
                "share_pct": ll_pct,
                "color": (59, 130, 246)  # Royal Blue
            },
            "households": households
        }

        cls._cached_result = result
        cls._is_dirty = False
        cls._last_calc_time = now
        return result
