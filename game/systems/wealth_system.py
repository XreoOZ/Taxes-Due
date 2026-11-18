"""
Village Wealth System (AGENT 2 & AGENT 3 Integration)
Calculates and provides the centralized economic single source of truth for all coin wealth
across the village: Landlord Crown Treasury and individual peasant households.
Zero hardcoding, zero duplicate coin counting.
"""

from game.systems.currency import to_copper, from_copper, normalize_wallet, canonical_denomination

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
    @classmethod
    def calculate_village_wealth(cls, resources=None, villager_manager=None, furniture_manager=None, building_manager=None, stockpile_manager=None):
        """
        Aggregates actual coin ownership across the village without duplication:
        - Landlord: resources / stockpile coins + Landlord-controlled market coin treasuries
        - Each Peasant Household: storage chest coins + member wallets + assigned market stall treasuries
        """
        # 1. LANDLORD WEALTH
        ll_wallet = {"Copper": 0, "Silver": 0, "Gold": 0}
        if resources:
            for k in ("Copper", "Silver", "Gold", "Copper Coin", "Silver Coin", "Gold Coin"):
                amt = resources.get(k, 0)
                canon = canonical_denomination(k)
                if canon:
                    ll_wallet[canon] += max(0, int(amt))

        # Check Landlord Market Stalls
        if building_manager:
            for b in getattr(building_manager, "buildings", []):
                if getattr(b, "building_type", "") == "market":
                    assigned_fam = getattr(b, "assigned_family_id", None)
                    if not assigned_fam:
                        mkt_curr = normalize_wallet(getattr(b, "currency", {}))
                        for denom in ("Copper", "Silver", "Gold"):
                            ll_wallet[denom] += mkt_curr[denom]

        ll_copper = to_copper(ll_wallet)

        # 2. HOUSEHOLD WEALTH
        households = []
        if villager_manager:
            for idx, fam in enumerate(getattr(villager_manager, "families", [])):
                fam_wallet = {"Copper": 0, "Silver": 0, "Gold": 0}

                # A. Coins in Household Storage Furniture (chests)
                if furniture_manager:
                    for furn in getattr(furniture_manager, "furnitures", getattr(furniture_manager, "furniture", [])):
                        if getattr(furn, "family_id", None) == fam.id and hasattr(furn, "inventory"):
                            for item_name, count in furn.inventory.items():
                                canon = canonical_denomination(item_name)
                                if canon:
                                    fam_wallet[canon] += max(0, int(count))

                # B. Coins in family members' personal pockets / wallets
                for m in getattr(fam, "members", []):
                    # Check wallet dict
                    if hasattr(m, "wallet") and isinstance(m.wallet, dict):
                        m_w = normalize_wallet(m.wallet)
                        for denom in ("Copper", "Silver", "Gold"):
                            fam_wallet[denom] += m_w[denom]
                    # Check inventory dict for coins
                    if hasattr(m, "inventory") and isinstance(m.inventory, dict):
                        for item_name, count in m.inventory.items():
                            canon = canonical_denomination(item_name)
                            if canon:
                                fam_wallet[canon] += max(0, int(count))

                # C. Coins in Market Stalls assigned to this family
                if building_manager:
                    for b in getattr(building_manager, "buildings", []):
                        if getattr(b, "building_type", "") == "market":
                            if getattr(b, "assigned_family_id", None) == fam.id:
                                mkt_curr = normalize_wallet(getattr(b, "currency", {}))
                                for denom in ("Copper", "Silver", "Gold"):
                                    fam_wallet[denom] += mkt_curr[denom]

                fam_copper = to_copper(fam_wallet)
                col = HOUSEHOLD_PALETTE[idx % len(HOUSEHOLD_PALETTE)]

                households.append({
                    "family_id": fam.id,
                    "name": f"The {fam.surname} Family",
                    "wealth_copper": fam_copper,
                    "wallet": fam_wallet,
                    "color": col,
                    "percentage": 0.0
                })

        # 3. TOTAL WEALTH & PERCENTAGES
        total_copper = ll_copper + sum(hh["wealth_copper"] for hh in households)

        if total_copper > 0:
            ll_pct = round((ll_copper / total_copper) * 100.0, 1)
            for hh in households:
                hh["percentage"] = round((hh["wealth_copper"] / total_copper) * 100.0, 1)
        else:
            ll_pct = 0.0
            for hh in households:
                hh["percentage"] = 0.0

        return {
            "total_wealth_copper": total_copper,
            "total_wallet": from_copper(total_copper),
            "landlord": {
                "name": "Landlord (Crown Treasury)",
                "wealth_copper": ll_copper,
                "wallet": ll_wallet,
                "percentage": ll_pct,
                "color": (59, 130, 246)  # Royal Blue
            },
            "households": households
        }
