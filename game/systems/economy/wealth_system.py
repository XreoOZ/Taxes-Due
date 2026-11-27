"""
Village Wealth System (AGENT 2 & AGENT 3 Integration)
Calculates and provides the centralized economic single source of truth for all coin wealth
across the village: Landlord Crown Treasury and individual peasant households.
Zero hardcoding, zero duplicate coin counting.
"""
import time
from game.systems.economy.currency import (
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


def _wallet_with_mirror_fallback(primary, fallback):
    """Prefer the physical wallet as a whole; fall back only for legacy-only wallets."""
    primary_wallet = normalize_wallet(primary)
    if any(primary_wallet.values()):
        return primary_wallet
    fallback_wallet = normalize_wallet(fallback)
    return fallback_wallet


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
                                 building_manager=None, stockpile_manager=None, permit_manager=None,
                                 force_recompute=False):
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

        # The treasury chest is the authoritative landlord coin container after
        # migration; it is separate from legacy resource mirrors and market vaults.
        if furniture_manager and hasattr(furniture_manager, "get_lord_treasury_chest"):
            treasury = furniture_manager.get_lord_treasury_chest()
            if treasury:
                for denom in CURRENCY_DENOMINATIONS:
                    ll_wallet[denom] += normalize_wallet(
                        getattr(treasury, "inventory", {})
                    )[denom]

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
                            if getattr(furn, "furniture_type", "") == "household_storage" and isinstance(getattr(furn, "inventory", None), dict):
                                f_wallet = normalize_wallet(furn.inventory)
                            else:
                                f_wallet = _wallet_with_mirror_fallback(
                                    getattr(furn, "inventory", None),
                                    getattr(furn, "currency", None),
                                )
                            for denom in CURRENCY_DENOMINATIONS:
                                fam_wallet[denom] += f_wallet[denom]

                    # Fallback lookup by method
                    if hasattr(furniture_manager, "get_storage_for_family"):
                        st = furniture_manager.get_storage_for_family(fam_id_str)
                        if st and id(st) not in visited_chests:
                            if getattr(st, "furniture_type", "") == "household_storage" and isinstance(getattr(st, "inventory", None), dict):
                                f_wallet = normalize_wallet(st.inventory)
                            else:
                                f_wallet = _wallet_with_mirror_fallback(
                                    getattr(st, "inventory", None),
                                    getattr(st, "currency", None),
                                )
                            for denom in CURRENCY_DENOMINATIONS:
                                fam_wallet[denom] += f_wallet[denom]

                    # A2. Unowned chests physically inside this family's
                    # permit still belong to the household even when
                    # family_id was never stamped (e.g. chest placed before
                    # the household was assigned). Count them once.
                    fam_permit_id = str(getattr(fam, "assigned_permit_id", "") or "")
                    permit = next((p for p in getattr(permit_manager, "permits", [])
                                   if str(getattr(p, "id", "")) == fam_permit_id), None) if fam_permit_id else None
                    if permit is not None:
                        for furn in furn_list:
                            if id(furn) in visited_chests:
                                continue
                            if getattr(furn, "furniture_type", "") != "household_storage":
                                continue
                            if getattr(furn, "family_id", None):
                                continue
                            try:
                                inside = permit.contains_tile(int(furn.grid_x), int(furn.grid_y))
                            except Exception:
                                inside = False
                            if inside:
                                visited_chests.add(id(furn))
                                f_wallet = _wallet_with_mirror_fallback(
                                    getattr(furn, "inventory", None),
                                    getattr(furn, "currency", None),
                                )
                                for denom in CURRENCY_DENOMINATIONS:
                                    fam_wallet[denom] += f_wallet[denom]

                # B. Coins physically carried in member pockets / personal inventories
                for m in getattr(fam, "members", []):
                    if hasattr(m, "currency") and isinstance(m.currency, dict):
                        mirror_wallet = m.currency
                    elif hasattr(m, "wallet") and isinstance(m.wallet, dict):
                        mirror_wallet = m.wallet
                    else:
                        mirror_wallet = None
                    m_wallet = _wallet_with_mirror_fallback(
                        getattr(m, "inventory", None), mirror_wallet
                    )
                    for denom in CURRENCY_DENOMINATIONS:
                        fam_wallet[denom] += m_wallet[denom]

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
