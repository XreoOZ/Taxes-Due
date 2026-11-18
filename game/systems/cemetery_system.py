"""
Cemetery, Gravedigger & Burial System (Agent 3)

Coordinates gameplay logic for:
1. Cemetery Permit & Grave tile lifecycle (occupancy, 30-day reuse, corpse history retention).
2. 5 Visually distinct tombstone models generated upon burial completion.
3. Gravedigger job (Hoe tool, 1 Wood + 1 Stone consumed per grave, 50% movement speed carrying corpse).
4. Gravedigger material stock & restocking (target 5 Wood and 5 Stone in assigned household chest).
5. Burial commission & payment (up to 1 Silver, fallback to Landlord storage when no surviving members).
6. Exact burial workflow: 1h digging, placing corpse, 30m burial, tombstone placement.
7. Full cemetery overflow handling: safe temporary storage near cemetery with polite notification to Landlord.
"""

import math
import random
from game.config import (
    TILE_SIZE,
    GRAVEDIGGER_TARGET_WOOD,
    GRAVEDIGGER_TARGET_STONE,
    GRAVE_COST_WOOD,
    GRAVE_COST_STONE,
    GRAVE_DIG_HOURS,
    GRAVE_BURY_HOURS,
    GRAVE_REUSE_DAYS,
    BURIAL_FEE_MAX_SILVER,
    CORPSE_CARRY_SPEED_RATIO,
    TOMBSTONE_MODELS_COUNT
)
from game.systems.currency import (
    to_copper,
    from_copper,
    normalize_wallet,
    execute_currency_transfer
)


class CemeterySystem:
    _instance = None

    def __init__(self):
        self.pending_commissions = []  # list of dicts: {"corpse_id": ..., "fee_paid": ..., "payer_id": ...}
        self.overflow_corpses = []     # list of dicts: {"corpse_id": ..., "gx": ..., "gy": ...}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = CemeterySystem()
        return cls._instance

    @classmethod
    def get_cemetery_permit(cls, permit_manager):
        """Returns the first active Cemetery permit."""
        if not permit_manager:
            return None
        for p in getattr(permit_manager, "permits", []):
            if getattr(p, "permit_type", "") == "cemetery":
                return p
        return None

    @classmethod
    def get_all_cemetery_permits(cls, permit_manager):
        if not permit_manager:
            return []
        return [p for p in getattr(permit_manager, "permits", []) if getattr(p, "permit_type", "") == "cemetery"]

    @classmethod
    def get_assigned_gravediggers(cls, permit_manager, villager_manager):
        """Returns all assigned Gravedigger villagers."""
        if not villager_manager:
            return []
        all_vils = villager_manager.get_all_villagers() if hasattr(villager_manager, "get_all_villagers") else getattr(villager_manager, "villagers", [])
        return [v for v in all_vils if getattr(v, "job", "") == "Gravedigger" and getattr(v, "is_alive", True)]

    @classmethod
    def assign_gravedigger(cls, permit_manager, villager_manager, target_permit=None, furniture_manager=None):
        """
        Assigns the closest available household member without an active job as Gravedigger.
        Distance is measured from their household residence so moving households dynamically updates assignments.
        Changes their title to Gravedigger and registers them to the cemetery permit.
        Returns (success: bool, villager or error message).
        """
        if not villager_manager:
            return False, "Villager manager unavailable."

        cemetery = target_permit or cls.get_cemetery_permit(permit_manager)

        # Reference location: center of cemetery permit or origin
        ref_x, ref_y = 0.0, 0.0
        if cemetery and hasattr(cemetery, "grid_x"):
            ref_x = (cemetery.grid_x + cemetery.tiles_w / 2.0) * TILE_SIZE
            ref_y = (cemetery.grid_y + cemetery.tiles_h / 2.0) * TILE_SIZE

        from game.world.permits import find_closest_unassigned_household_worker
        chosen = find_closest_unassigned_household_worker(
            ref_x, ref_y,
            permit_manager=permit_manager,
            villager_manager=villager_manager,
            target_job="Gravedigger",
            furniture_manager=furniture_manager
        )

        if not chosen:
            return False, "No available household member without an active job."

        chosen.set_job("Gravedigger")
        chosen.say("I have taken up the Gravedigger duty.", duration=2.5)

        if cemetery:
            if not hasattr(cemetery, "assigned_workers"):
                cemetery.assigned_workers = []
            if str(chosen.id) not in [str(w) for w in cemetery.assigned_workers]:
                cemetery.assigned_workers.append(chosen.id)
            cemetery.max_workers = max(getattr(cemetery, "max_workers", 1), len(cemetery.assigned_workers))

        return True, chosen

    @classmethod
    def release_gravedigger(cls, permit_manager, villager_manager, target_permit=None):
        """
        Releases an assigned Gravedigger, restoring them to normal household member status.
        """
        if not villager_manager:
            return False, "Villager manager unavailable."

        cemetery = target_permit or cls.get_cemetery_permit(permit_manager)
        all_vils = villager_manager.get_all_villagers() if hasattr(villager_manager, "get_all_villagers") else getattr(villager_manager, "villagers", [])

        released_vil = None
        if cemetery and getattr(cemetery, "assigned_workers", None):
            pid = cemetery.assigned_workers.pop()
            cemetery.max_workers = max(0, getattr(cemetery, "max_workers", 1) - 1)
            released_vil = next((v for v in all_vils if str(v.id) == str(pid)), None)

        if not released_vil:
            released_vil = next((v for v in all_vils if getattr(v, "job", "") == "Gravedigger"), None)

        if released_vil:
            released_vil.set_job("Farmer")
            released_vil.say("I have stepped down from being a Gravedigger.", duration=2.5)
            return True, released_vil

        return False, "No active Gravedigger found."

    # -------------------------------------------------------------------------
    # Grave Lifecycle (30-day reuse, corpse history, 5 tombstone models)
    # -------------------------------------------------------------------------

    @classmethod
    def ensure_cemetery_graves(cls, cemetery_permit):
        """Ensures all tiles in the Cemetery permit are initialized in the tile_graves dictionary."""
        if not cemetery_permit:
            return
        if not hasattr(cemetery_permit, "tile_graves"):
            cemetery_permit.tile_graves = {}
        for t in cemetery_permit.tiles:
            if t not in cemetery_permit.tile_graves:
                cemetery_permit.tile_graves[t] = {
                    "corpse_id": None,
                    "corpse_name": None,
                    "buried_day": 0.0,
                    "tombstone_variant": None,
                    "corpse_history": [],
                    "is_occupied": False,
                    "dig_progress": 0.0,
                    "bury_progress": 0.0
                }

    @classmethod
    def update_grave_lifecycles(cls, cemetery_permit, current_day):
        """
        Updates grave states across the cemetery plot:
        - When a grave reaches 30 in-game days:
          1. Old tombstone disappears.
          2. Old corpse remains inside grave (retained in corpse_history, NEVER deleted).
          3. Grave tile becomes unoccupied / available again for a new burial commission!
        """
        if not cemetery_permit:
            return
        cls.ensure_cemetery_graves(cemetery_permit)

        for t, g in cemetery_permit.tile_graves.items():
            if g.get("is_occupied", False):
                buried_day = g.get("buried_day", 0.0)
                if current_day >= (buried_day + GRAVE_REUSE_DAYS):
                    # 30 days elapsed: tombstone removed, grave becomes available
                    c_id = g.get("corpse_id")
                    if c_id and c_id not in g["corpse_history"]:
                        g["corpse_history"].append(c_id)
                    g["is_occupied"] = False
                    g["tombstone_variant"] = None
                    g["dig_progress"] = 0.0
                    g["bury_progress"] = 0.0
                    # Note: old corpse remains registered in history, not deleted!

    @classmethod
    def get_available_grave_tile(cls, cemetery_permit, current_day=1.0):
        """
        Finds an available grave tile in the cemetery (empty or 30-day reusable).
        Returns: (gx, gy) or None if cemetery is completely full.
        """
        if not cemetery_permit:
            return None
        cls.ensure_cemetery_graves(cemetery_permit)
        cls.update_grave_lifecycles(cemetery_permit, current_day)

        sorted_tiles = sorted(cemetery_permit.tiles, key=lambda t: (t[1], t[0]))
        for t in sorted_tiles:
            g = cemetery_permit.tile_graves.get(t)
            if g and not g.get("is_occupied", False):
                return t
        return None

    @classmethod
    def complete_burial_on_tile(cls, cemetery_permit, tile, corpse, current_day=1.0):
        """
        Completes the burial on a grave tile:
        - Sets corpse_id, corpse_name, buried_day.
        - Randomly generates one of at least 5 visually distinct tombstone models.
        - Marks grave as occupied.
        """
        if not cemetery_permit or not tile:
            return None
        cls.ensure_cemetery_graves(cemetery_permit)
        g = cemetery_permit.tile_graves[tile]

        # Preserve previous occupant in history if reusing tile
        old_id = g.get("corpse_id")
        if old_id and old_id not in g["corpse_history"]:
            g["corpse_history"].append(old_id)

        if isinstance(corpse, dict):
            corpse_id = str(corpse.get("id", "unknown"))
            corpse_name = str(corpse.get("full_name", corpse.get("first_name", corpse_id)))
        else:
            corpse_id = str(getattr(corpse, "id", corpse))
            corpse_name = getattr(corpse, "full_name", str(corpse))
        g["corpse_id"] = corpse_id
        g["corpse_name"] = corpse_name
        g["buried_day"] = float(current_day)
        # Select randomly from 5 distinct tombstone variants (0 to 4)
        g["tombstone_variant"] = random.randint(0, TOMBSTONE_MODELS_COUNT - 1)
        g["is_occupied"] = True
        g["dig_progress"] = 0.0
        g["bury_progress"] = 0.0
        return g["tombstone_variant"]

    # -------------------------------------------------------------------------
    # Gravedigger Material Stock & Restocking (Target: 5 Wood, 5 Stone)
    # -------------------------------------------------------------------------

    @classmethod
    def check_gravedigger_stock(cls, gravedigger, furniture_manager):
        """
        Checks the Gravedigger's assigned household chest stock of Wood and Stone.
        Target: exactly 5 Wood, 5 Stone.
        Returns: (wood_count, stone_count, missing_wood, missing_stone)
        """
        fam_id = getattr(gravedigger, "family_id", None)
        chest = furniture_manager.get_storage_for_family(fam_id) if (furniture_manager and fam_id) else None
        inv = getattr(chest, "inventory", {}) if chest else {}

        wood_amt = inv.get("Wood", 0)
        stone_amt = inv.get("Stone", 0)
        missing_w = max(0, GRAVEDIGGER_TARGET_WOOD - wood_amt)
        missing_s = max(0, GRAVEDIGGER_TARGET_STONE - stone_amt)
        return wood_amt, stone_amt, missing_w, missing_s

    @classmethod
    def consume_grave_materials(cls, gravedigger, furniture_manager):
        """
        Consumes exactly 1 Wood and 1 Stone from the Gravedigger's household chest for a burial.
        Returns True if successful, False if insufficient materials.
        """
        fam_id = getattr(gravedigger, "family_id", None)
        chest = furniture_manager.get_storage_for_family(fam_id) if (furniture_manager and fam_id) else None
        if not chest or not hasattr(chest, "inventory"):
            return False

        inv = chest.inventory
        if inv.get("Wood", 0) < GRAVE_COST_WOOD or inv.get("Stone", 0) < GRAVE_COST_STONE:
            return False

        inv["Wood"] -= GRAVE_COST_WOOD
        inv["Stone"] -= GRAVE_COST_STONE
        return True

    # -------------------------------------------------------------------------
    # Burial Commission & Payment (Up to 1 Silver, Landlord fallback)
    # -------------------------------------------------------------------------

    @classmethod
    def commission_burial(cls, deceased_villager, villager_manager, furniture_manager=None, stockpile_manager=None, resources=None, gravedigger=None):
        """
        Processes burial arrangement for a deceased villager:
        - If surviving household members exist: Burial Representative retrieves up to 1 Silver
          from household chest and pays Gravedigger directly.
          If household has 1 Gold but no Silver, exchanges Gold to smaller denominations (Requirement 5).
        - If deceased has NO surviving household members: Gravedigger retrieves burial fee
          (up to 1 Silver = 10 Copper) directly from Landlord storage/resources.
        """
        if not deceased_villager:
            return None

        fam_id = getattr(deceased_villager, "family_id", None)
        family = villager_manager.get_family_by_id(fam_id) if (villager_manager and fam_id) else None
        surviving = [m for m in getattr(family, "members", []) if getattr(m, "is_alive", True)] if family else []

        max_fee_copper = BURIAL_FEE_MAX_SILVER * 10  # 1 Silver = 10 Copper
        fee_paid_copper = 0
        payer_type = "representative"

        if surviving:
            rep = surviving[0]
            chest = furniture_manager.get_storage_for_family(fam_id) if furniture_manager else None
            wallet = {"Copper": 0, "Silver": 0, "Gold": 0}
            source = None

            if chest and hasattr(chest, "currency") and isinstance(chest.currency, dict):
                wallet = normalize_wallet(chest.currency)
                source = chest.currency
            elif chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
                for k in ("Copper", "Silver", "Gold"):
                    wallet[k] = chest.inventory.get(k, 0)
                source = chest.inventory
            else:
                wallet = normalize_wallet(getattr(rep, "currency", {}))
                source = getattr(rep, "currency", None)

            # Currency exchange: If household has 1 Gold but no Silver/Copper, exchange Gold (Requirement 5)
            if wallet.get("Silver", 0) <= 0 and wallet.get("Copper", 0) <= 0 and wallet.get("Gold", 0) > 0:
                wallet["Gold"] -= 1
                wallet["Silver"] += 10
                if source is not None:
                    source["Gold"] = wallet["Gold"]
                    source["Silver"] = wallet["Silver"]

            avail_copper = to_copper(wallet)
            fee_paid_copper = min(max_fee_copper, avail_copper)
            if fee_paid_copper > 0 and source is not None:
                # Deduct payment from household source
                remaining_copper = max(0, avail_copper - fee_paid_copper)
                new_w = from_copper(remaining_copper)
                for d in ("Copper", "Silver", "Gold"):
                    source[d] = new_w.get(d, 0)
                    if source[d] <= 0 and d in source:
                        del source[d]

            rep.say(f"Commissioned burial for {deceased_villager.first_name} (Paid {fee_paid_copper}c).", duration=2.5)
        else:
            # Fallback: No surviving members -> Gravedigger retrieves fee from Landlord storage
            payer_type = "landlord"
            landlord_copper = 0
            if resources and isinstance(resources, dict):
                landlord_copper = resources.get("Copper", 0) + resources.get("Silver", 0) * 10 + resources.get("Gold", 0) * 100
                fee_paid_copper = min(max_fee_copper, landlord_copper)
                # Deduct from landlord resources
                if fee_paid_copper > 0:
                    resources["Copper"] = max(0, resources.get("Copper", 0) - fee_paid_copper)

        # Deposit payment directly to Gravedigger (Requirement 5 & 6)
        target_gd = gravedigger
        if not target_gd and villager_manager:
            all_v = villager_manager.get_all_villagers()
            target_gd = next((v for v in all_v if getattr(v, "job", "") == "Gravedigger" and getattr(v, "is_alive", True)), None)

        if target_gd and fee_paid_copper > 0:
            if not hasattr(target_gd, "currency") or not isinstance(target_gd.currency, dict):
                target_gd.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
            target_gd.currency["Copper"] = target_gd.currency.get("Copper", 0) + fee_paid_copper
            if hasattr(target_gd, "inventory") and isinstance(target_gd.inventory, dict):
                target_gd.inventory["Copper"] = target_gd.inventory.get("Copper", 0) + fee_paid_copper

        try:
            from game.systems.wealth_system import VillageWealthSystem
            VillageWealthSystem.mark_dirty()
        except ImportError:
            pass

        commission = {
            "corpse_id": str(deceased_villager.id),
            "corpse_name": deceased_villager.full_name,
            "corpse_obj": deceased_villager,
            "fee_paid": fee_paid_copper,
            "payer_type": payer_type,
            "status": "PENDING"
        }
        inst = cls.get_instance()
        inst.pending_commissions.append(commission)
        return commission

    # -------------------------------------------------------------------------
    # Full Cemetery Overflow Handling
    # -------------------------------------------------------------------------

    @classmethod
    def handle_full_cemetery_overflow(cls, gravedigger, corpse, cemetery_permit, tile_size=TILE_SIZE):
        """
        When Cemetery is completely full:
        1. Gravedigger carries corpse to a safe temporary position near Cemetery.
        2. Temporarily stores the corpse there without blocking roads or entrances.
        3. Displays polite bubble message to Landlord:
           "The cemetery is currently full. Please consider expanding it, Landlord."
        4. Registers pending corpse awaiting future available grave.
        """
        if not cemetery_permit:
            return 0.0, 0.0

        # Safe position just outside the perimeter of the cemetery plot
        min_tile = min(cemetery_permit.tiles, key=lambda t: (t[1], t[0]))
        temp_x = (min_tile[0] - 1.0) * tile_size
        temp_y = (min_tile[1] + 0.5) * tile_size

        inst = cls.get_instance()
        corpse_id = str(getattr(corpse, "id", corpse))
        if not any(c.get("corpse_id") == corpse_id for c in inst.overflow_corpses):
            inst.overflow_corpses.append({
                "corpse_id": corpse_id,
                "corpse_obj": corpse,
                "x": temp_x,
                "y": temp_y
            })

        # Polite notification to the Landlord
        gravedigger.say("The cemetery is currently full. Please consider expanding it, Landlord.", duration=3.5)
        return temp_x, temp_y
