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
    CHEST_INTERACTION_RADIUS,
    INTERACTION_CONTACT_RADIUS,
    LOOSE_ITEM_ARRIVAL_DIST,
    CURRENCY_DENOMINATIONS,
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
from game.systems.economy.currency import (
    COPPER_PER_SILVER,
    canonical_denomination,
    to_copper,
    from_copper,
    normalize_wallet,
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
            released_vil.set_job("Unassigned")
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
    def get_overflow_corpse_ids(cls):
        return {
            str(item.get("corpse_id"))
            for item in cls.get_instance().overflow_corpses
        }

    @classmethod
    def release_ready_overflow_corpse(cls, cemetery_permit, current_day=1.0):
        """Requeue the oldest overflow corpse once an empty grave is available."""
        if not cls.get_available_grave_tile(cemetery_permit, current_day):
            return None
        pending = cls.get_instance().overflow_corpses
        if not pending:
            return None
        record = pending.pop(0)
        corpse = record.get("corpse_obj")
        if corpse:
            corpse.is_picked_up = False
            corpse.is_buried = False
        return corpse

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
        chest_inventory = getattr(chest, "inventory", {}) if chest else {}
        personal_inventory = getattr(gravedigger, "inventory", {})

        wood_amt = chest_inventory.get("Wood", 0) + personal_inventory.get("Wood", 0)
        stone_amt = chest_inventory.get("Stone", 0) + personal_inventory.get("Stone", 0)
        from game.config import DEDICATED_JOBS
        stock_targets = DEDICATED_JOBS.get("Gravedigger", {}).get("material_stock_target", {})
        current = {"Wood": wood_amt, "Stone": stone_amt}
        missing_w = max(0, int(stock_targets.get("Wood", 0)) - current["Wood"])
        missing_s = max(0, int(stock_targets.get("Stone", 0)) - current["Stone"])
        return wood_amt, stone_amt, missing_w, missing_s

    @classmethod
    def get_missing_gravedigger_materials(cls, gravedigger, furniture_manager):
        """Return configured material deficits for this household and worker."""
        from game.config import DEDICATED_JOBS
        family_id = getattr(gravedigger, "family_id", None)
        chest = furniture_manager.get_storage_for_family(family_id) if furniture_manager and family_id else None
        chest_inventory = getattr(chest, "inventory", {}) if chest else {}
        personal_inventory = getattr(gravedigger, "inventory", {})
        targets = DEDICATED_JOBS.get("Gravedigger", {}).get("material_stock_target", {})
        stock = {item: chest_inventory.get(item, 0) + personal_inventory.get(item, 0) for item in targets}
        missing = {item: max(0, int(target) - stock[item]) for item, target in targets.items() if stock[item] < target}
        return stock, missing

    @classmethod
    def consume_grave_materials(cls, gravedigger, furniture_manager):
        """
        Consumes exactly 1 Wood and 1 Stone from the Gravedigger's household chest for a burial.
        Returns True if successful, False if insufficient materials.
        """
        fam_id = getattr(gravedigger, "family_id", None)
        chest = furniture_manager.get_storage_for_family(fam_id) if (furniture_manager and fam_id) else None
        chest_inventory = getattr(chest, "inventory", {}) if chest else {}
        personal_inventory = getattr(gravedigger, "inventory", {})
        from game.config import DEDICATED_JOBS
        materials = DEDICATED_JOBS.get("Gravedigger", {}).get("materials_per_grave", {})
        for item, amount in materials.items():
            if chest_inventory.get(item, 0) + personal_inventory.get(item, 0) < amount:
                return False
        for item, amount in materials.items():
            taken = min(chest_inventory.get(item, 0), amount)
            chest_inventory[item] = chest_inventory.get(item, 0) - taken
            personal_inventory[item] = personal_inventory.get(item, 0) - (amount - taken)
            if chest_inventory.get(item, 0) <= 0:
                chest_inventory.pop(item, None)
            if personal_inventory.get(item, 0) <= 0:
                personal_inventory.pop(item, None)
        return True

    # -------------------------------------------------------------------------
    # Burial Commission & Payment (Up to 1 Silver, Landlord fallback)
    # -------------------------------------------------------------------------

    @classmethod
    def commission_burial(cls, deceased_villager, villager_manager, furniture_manager=None, stockpile_manager=None, resources=None, gravedigger=None):
        """
        Starts one physical payment flow per corpse. The household representative
        pays when survivors exist; otherwise the gravedigger collects from landlord
        storage. Any payment is capped by the configured maximum fee.
        """
        if not deceased_villager:
            return None

        corpse_id = str(getattr(deceased_villager, "id", ""))
        existing = next(
            (entry for entry in cls.get_instance().pending_commissions
             if entry.get("corpse_id") == corpse_id),
            None,
        )
        if existing:
            return existing

        fam_id = getattr(deceased_villager, "family_id", None)
        family = villager_manager.get_family_by_id(fam_id) if (villager_manager and fam_id) else None
        surviving = [m for m in getattr(family, "members", []) if getattr(m, "is_alive", True)] if family else []
        payer_type = "representative" if surviving else "landlord"
        payer = None
        if surviving:
            payer = family.get_available_recovery_representative() if family else None
            payer = payer or surviving[0]
            if payer is gravedigger:
                payer = next((member for member in surviving if member is not gravedigger), None)
            if payer:
                chest = furniture_manager.get_storage_for_family(fam_id) if furniture_manager else None
                available = to_copper(getattr(chest, "inventory", {})) if chest else 0
            else:
                payer_type = "landlord"
                payer = gravedigger
                available = cls._landlord_coin_value(stockpile_manager, furniture_manager)
        else:
            payer = gravedigger
            available = cls._landlord_coin_value(stockpile_manager, furniture_manager)

        fee_available = min(BURIAL_FEE_MAX_SILVER * COPPER_PER_SILVER, available)
        commission = {
            "corpse_id": str(deceased_villager.id),
            "corpse_name": deceased_villager.full_name,
            "corpse_obj": deceased_villager,
            "fee_paid": 0,
            "fee_available": fee_available,
            "payer_type": payer_type,
            "payer_id": getattr(payer, "id", None),
            "gravedigger_id": getattr(gravedigger, "id", None),
            "status": "PAYMENT_PENDING" if fee_available > 0 else "PAID",
        }
        inst = cls.get_instance()
        inst.pending_commissions.append(commission)

        if fee_available > 0 and payer_type == "representative" and payer:
            from game.systems.work.commission_schedule import CommissionScheduleSystem
            CommissionScheduleSystem.queue(
                payer, "BURIAL_PAYMENT_RETRIEVE",
                burial_payment_target_corpse_id=corpse_id,
                burial_payment_gravedigger_id=getattr(gravedigger, "id", None),
            )
        elif fee_available > 0 and gravedigger:
            from game.systems.work.commission_schedule import CommissionScheduleSystem
            CommissionScheduleSystem.queue(
                gravedigger, "GRAVEDIGGER_BURIAL_PAYMENT_RETRIEVE",
                burial_payment_target_corpse_id=corpse_id,
                burial_payment_gravedigger_id=getattr(gravedigger, "id", None),
            )
        elif payer_type == "representative" and payer:
            payer.say("No household coins were available for the burial fee.", duration=2.5)
        return commission

    @classmethod
    def _landlord_coin_stacks(cls, stockpile_manager):
        valid_denominations = set(CURRENCY_DENOMINATIONS)
        return [
            stack for stack in getattr(stockpile_manager, "stacks", [])
            if getattr(stack, "owner_type", None) == "landlord"
            and canonical_denomination(getattr(stack, "resource_type", "")) in valid_denominations
        ]

    @classmethod
    def _landlord_coin_value(cls, stockpile_manager, furniture_manager=None):
        from game.systems.economy.lord_treasury import LordTreasurySystem
        treasury_value = LordTreasurySystem.value(furniture_manager)
        if furniture_manager and LordTreasurySystem.get_chest(furniture_manager):
            return treasury_value
        wallet = {"Copper": 0, "Silver": 0, "Gold": 0}
        for stack in cls._landlord_coin_stacks(stockpile_manager):
            denom = canonical_denomination(stack.resource_type)
            wallet[denom] += max(0, int(getattr(stack, "amount", 0)))
        return to_copper(wallet)

    @classmethod
    def _commission_for_corpse(cls, corpse_id):
        return next((entry for entry in cls.get_instance().pending_commissions
                     if entry.get("corpse_id") == str(corpse_id)), None)

    @classmethod
    def complete_burial_commission(cls, corpse_id):
        inst = cls.get_instance()
        inst.pending_commissions = [
            entry for entry in inst.pending_commissions
            if entry.get("corpse_id") != str(corpse_id)
        ]

    @classmethod
    def _replace_wallet_in_inventory(cls, inventory, wallet):
        for key in list(inventory):
            if canonical_denomination(key):
                del inventory[key]
        inventory.update({key: value for key, value in wallet.items() if value > 0})

    @classmethod
    def _mark_wealth_dirty(cls):
        try:
            from game.systems.economy.wealth_system import VillageWealthSystem
            VillageWealthSystem.mark_dirty()
        except ImportError:
            pass

    @classmethod
    def _collect_household_fee(cls, payer, commission, furniture_manager):
        chest = furniture_manager.get_storage_for_family(payer.family_id) if furniture_manager else None
        if not chest or not isinstance(getattr(chest, "inventory", None), dict):
            commission["fee_paid"] = 0
            commission["status"] = "PAID"
            return 0

        wallet = normalize_wallet(chest.inventory)
        total = to_copper(wallet)
        fee = min(BURIAL_FEE_MAX_SILVER * COPPER_PER_SILVER, total)
        cls._replace_wallet_in_inventory(chest.inventory, from_copper(total - fee))
        for denom, amount in from_copper(fee).items():
            if amount:
                payer.inventory[denom] = payer.inventory.get(denom, 0) + amount
        from game.systems.economy.currency import compact_currency_wallet
        compact_currency_wallet(chest.inventory)
        compact_currency_wallet(payer.inventory)
        commission["fee_paid"] = fee
        commission["status"] = "PAYMENT_TRAVELING"
        return fee

    @classmethod
    def _collect_landlord_fee(cls, gravedigger, commission, stockpile_manager, furniture_manager=None):
        from game.systems.economy.lord_treasury import LordTreasurySystem
        if furniture_manager and LordTreasurySystem.get_chest(furniture_manager):
            fee = min(BURIAL_FEE_MAX_SILVER * COPPER_PER_SILVER,
                      LordTreasurySystem.value(furniture_manager))
            success, _ = LordTreasurySystem.withdraw_covering(
                furniture_manager, gravedigger.inventory, fee
            )
            commission["fee_paid"] = fee if success else 0
            commission["status"] = "PAID"
            if success and fee > 0:
                from game.systems.economy.market_sales_report import MarketSalesReportSystem
                villager_manager = getattr(gravedigger, "villager_manager", None)
                MarketSalesReportSystem.record_household_income(
                    villager_manager, getattr(gravedigger, "family_id", None),
                    "Burial Services", fee,
                    getattr(villager_manager, "current_day_number", 1),
                )
            return commission["fee_paid"]
        stacks = cls._landlord_coin_stacks(stockpile_manager)
        wallet = {"Copper": 0, "Silver": 0, "Gold": 0}
        for stack in stacks:
            wallet[canonical_denomination(stack.resource_type)] += max(0, int(stack.amount))

        total = to_copper(wallet)
        fee = min(BURIAL_FEE_MAX_SILVER * COPPER_PER_SILVER, total)
        remainder = from_copper(total - fee)
        if stacks:
            drop_tile = (stacks[0].grid_x, stacks[0].grid_y)
            for stack in stacks:
                if stack in stockpile_manager.stacks:
                    stockpile_manager.stacks.remove(stack)
            stockpile_manager.mark_totals_dirty()
            for denom, amount in remainder.items():
                if amount:
                    stockpile_manager.drop_resource(denom, amount, *drop_tile, owner_type="landlord")

        for denom, amount in from_copper(fee).items():
            if amount:
                gravedigger.inventory[denom] = gravedigger.inventory.get(denom, 0) + amount
        from game.systems.economy.currency import compact_currency_wallet
        compact_currency_wallet(gravedigger.inventory)
        commission["fee_paid"] = fee
        commission["status"] = "PAID"
        cls._mark_wealth_dirty()
        if fee > 0:
            from game.systems.economy.market_sales_report import MarketSalesReportSystem
            villager_manager = getattr(gravedigger, "villager_manager", None)
            MarketSalesReportSystem.record_household_income(
                villager_manager, getattr(gravedigger, "family_id", None),
                "Burial Services", fee,
                getattr(villager_manager, "current_day_number", 1),
            )
        return fee

    @classmethod
    def update_burial_payment_task(cls, villager, dt, building_manager, furniture_manager,
                                   stockpile_manager, all_entities, player,
                                   villager_manager=None, day_number=1):
        task = getattr(villager, "task", "")
        if task not in ("BURIAL_PAYMENT_RETRIEVE", "BURIAL_PAYMENT_TRAVEL",
                        "GRAVEDIGGER_BURIAL_PAYMENT_RETRIEVE"):
            return False

        commission = cls._commission_for_corpse(
            getattr(villager, "burial_payment_target_corpse_id", None)
        )
        if not commission:
            villager.burial_payment_target_corpse_id = None
            villager.burial_payment_gravedigger_id = None
            villager._resume_or_idle_after_need()
            return True

        if task == "BURIAL_PAYMENT_RETRIEVE":
            chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
            if not chest:
                commission["fee_paid"] = 0
                commission["status"] = "PAID"
                cls._mark_wealth_dirty()
                villager.task = "IDLE"
                villager.burial_payment_target_corpse_id = None
                villager.burial_payment_gravedigger_id = None
                villager._resume_or_idle_after_need()
                return True
            pos = chest.get_approach_point(
                villager.x, villager.y, worker_id=villager.id,
                all_entities=all_entities, tile_size=TILE_SIZE,
                bm=building_manager,
            )
            arrived = villager._move_towards(
                pos[0], pos[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
                interaction_target=chest,
            )
            if arrived:
                fee = cls._collect_household_fee(villager, commission, furniture_manager)
                if fee <= 0:
                    villager.burial_payment_target_corpse_id = None
                    villager.burial_payment_gravedigger_id = None
                    villager._resume_or_idle_after_need()
                else:
                    villager.task = "BURIAL_PAYMENT_TRAVEL"
            return True

        if task == "BURIAL_PAYMENT_TRAVEL":
            gravedigger = (
                all_entities.by_id(commission.get("gravedigger_id"))
                if hasattr(all_entities, "by_id")
                else next((entity for entity in all_entities
                           if str(getattr(entity, "id", "")) == str(commission.get("gravedigger_id"))), None)
            )
            if not gravedigger or not getattr(gravedigger, "is_alive", True):
                chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
                if chest:
                    for denom, amount in from_copper(commission.get("fee_paid", 0)).items():
                        if amount:
                            chest.store_item(denom, amount)
                    from game.systems.economy.currency import compact_currency_wallet
                    compact_currency_wallet(chest.inventory)
                commission["status"] = "PAID"
                villager.burial_payment_target_corpse_id = None
                villager.task = "IDLE"
                villager._resume_or_idle_after_need()
                return True

            arrived = villager._move_towards(
                gravedigger.x, gravedigger.y, dt, arrival_dist=INTERACTION_CONTACT_RADIUS,
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
                interaction_target=gravedigger,
            )
            if arrived:
                for denom, amount in from_copper(commission.get("fee_paid", 0)).items():
                    if amount:
                        villager.inventory[denom] = max(0, villager.inventory.get(denom, 0) - amount)
                        if villager.inventory[denom] <= 0:
                            villager.inventory.pop(denom, None)
                        gravedigger.inventory[denom] = gravedigger.inventory.get(denom, 0) + amount
                from game.systems.economy.currency import compact_currency_wallet
                compact_currency_wallet(villager.inventory)
                compact_currency_wallet(gravedigger.inventory)
                from game.systems.economy.market_sales_report import MarketSalesReportSystem
                if str(getattr(gravedigger, "family_id", "")) != str(getattr(villager, "family_id", "")):
                    MarketSalesReportSystem.record_household_income(
                        villager_manager, getattr(gravedigger, "family_id", None),
                        "Burial Services", commission.get("fee_paid", 0), day_number,
                    )
                commission["status"] = "PAID"
                cls._mark_wealth_dirty()
                villager.say(f"Paid the burial fee for {commission['corpse_name']}.", duration=2.5)
                gravedigger.say(f"Burial fee received: {commission['fee_paid']}c.", duration=2.5)
                villager.burial_payment_target_corpse_id = None
                villager.burial_payment_gravedigger_id = None
                villager._resume_or_idle_after_need()
            return True

        from game.systems.economy.lord_treasury import LordTreasurySystem
        treasury = LordTreasurySystem.get_chest(furniture_manager)
        if treasury:
            available = LordTreasurySystem.value(furniture_manager)
            if available <= 0:
                cls._collect_landlord_fee(villager, commission, stockpile_manager, furniture_manager)
                villager.burial_payment_target_corpse_id = None
                villager.burial_payment_gravedigger_id = None
                villager._resume_or_idle_after_need()
                return True
            pos = treasury.get_approach_point(
                villager.x, villager.y, worker_id=villager.id,
                all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager,
            )
            arrived = villager._move_towards(
                pos[0], pos[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
                interaction_target=treasury,
            )
            if arrived:
                fee = cls._collect_landlord_fee(villager, commission, stockpile_manager, furniture_manager)
                villager.burial_payment_target_corpse_id = None
                villager.burial_payment_gravedigger_id = None
                villager._resume_or_idle_after_need()
                if fee:
                    villager.say(f"Collected {fee}c from the Lord's Treasury for the burial.", duration=2.5)
            return True

        stacks = cls._landlord_coin_stacks(stockpile_manager)
        if not stacks:
            cls._collect_landlord_fee(villager, commission, stockpile_manager, furniture_manager)
            villager.burial_payment_target_corpse_id = None
            villager.burial_payment_gravedigger_id = None
            villager._resume_or_idle_after_need()
            return True
        target = min(stacks, key=lambda stack: math.hypot(
            (stack.grid_x + 0.5) * TILE_SIZE - villager.x,
            (stack.grid_y + 0.5) * TILE_SIZE - villager.y,
        ))
        target_x = (target.grid_x + 0.5) * TILE_SIZE
        target_y = (target.grid_y + 0.5) * TILE_SIZE
        arrived = villager._move_towards(
            target_x, target_y, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=target,
        )
        if arrived:
            fee = cls._collect_landlord_fee(villager, commission, stockpile_manager, furniture_manager)
            villager.burial_payment_target_corpse_id = None
            villager.burial_payment_gravedigger_id = None
            villager._resume_or_idle_after_need()
            if fee:
                villager.say(f"Collected {fee}c from landlord storage for the burial.", duration=2.5)
        return True

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
        corpse_x, corpse_y = cls.get_overflow_position(cemetery_permit, corpse, tile_size)

        inst = cls.get_instance()
        corpse_id = str(getattr(corpse, "id", corpse))
        if not any(c.get("corpse_id") == corpse_id for c in inst.overflow_corpses):
            inst.overflow_corpses.append({
                "corpse_id": corpse_id,
                "corpse_obj": corpse,
                "x": corpse_x,
                "y": corpse_y,
            })

        if hasattr(corpse, "x"):
            corpse.x = corpse_x
            corpse.y = corpse_y
            corpse.is_picked_up = False
            corpse.is_cemetery_overflow = True

        # Polite notification to the Landlord
        if gravedigger:
            message = "There is no cemetery yet. Please grant cemetery land, Landlord." if not cemetery_permit else "The cemetery is full. Please consider expanding it, Landlord."
            gravedigger.say(message, duration=3.5)
        return corpse_x, corpse_y

    @classmethod
    def get_overflow_position(cls, cemetery_permit, corpse, tile_size=TILE_SIZE):
        """Return a safe holding position outside the cemetery boundary."""
        if cemetery_permit and cemetery_permit.tiles:
            min_tile = min(cemetery_permit.tiles, key=lambda t: (t[1], t[0]))
            return (min_tile[0] - 1.0) * tile_size, (min_tile[1] + 0.5) * tile_size
        return (
            float(getattr(corpse, "x", 0.0)),
            float(getattr(corpse, "y", 0.0)),
        )
