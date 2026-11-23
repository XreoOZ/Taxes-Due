"""Toolmaker System — iron chain production and tool commissions.

Iron Mine -> Iron Ore -> (smelt: 1 Ore + 1 Wood -> 1 Iron Bar, 10 ingame min,
stock target/daily cap) -> tool orders (2 Wood + 3 Iron Bar per tool,
1-2 ingame hours RNG per unit, qty per order).

Commission/payment/refund flow reuses BuilderSystem + ArtisanCommissionSystem:
each tool order is a ToolOrderSubject exposing ``construction_order`` so the
generic errands (BUILDER_FEE_*, servant landlord courier, death refunds) work
unchanged. Only ``artisan_job == "Toolmaker"`` orders are claimed here.
"""
import math
import random
import time

from game.data.config import (
    ARTISAN_JOB_IDS,
    DAILY_FOOD_REQUIREMENT,
    DEFAULT_ITEM_PRICES,
    DEDICATED_JOBS,
    ITEM_CATEGORIES,
    TOOLMAKER_BAR_DAILY_CAP,
    TOOLMAKER_BAR_RECIPE,
    TOOLMAKER_BAR_SMELT_INGAME_MINUTES,
    TOOLMAKER_BAR_STOCK_TARGET,
    TOOLMAKER_TOOL_MAX_INGAME_HOURS,
    TOOLMAKER_TOOL_MIN_INGAME_HOURS,
    TOOLMAKER_TOOL_RECIPE,
)
from game.systems.economy.currency import normalize_wallet, to_copper
from game.systems.economy.market_service import MarketService
from game.systems.work.builder_system import BuilderSystem
from game.config import TILE_SIZE, CHEST_INTERACTION_RADIUS


class ToolOrderSubject:
    """Lightweight commission subject so tool orders plug into the shared
    artisan machinery (_order_subjects, payment errands, refunds)."""

    def __init__(self, workbench, order):
        self.workbench = workbench
        self.construction_order = order
        self.id = order.get("id")
        self.name = f"{order.get('tool_name', 'Tool')} x{order.get('qty_total', 1)}"

    def get_world_pos(self, tile_size=TILE_SIZE):
        return self.workbench.get_world_pos(tile_size)

    def get_center_world(self, tile_size=TILE_SIZE):
        return self.workbench.get_world_pos(tile_size)

    def get_approach_point(self, *args, **kwargs):
        return self.workbench.get_approach_point(*args, **kwargs)


class ToolmakerSystem:
    _order_seq = 0

    # ------------------------------------------------------------------
    # Catalogue / order creation
    # ------------------------------------------------------------------
    @classmethod
    def craftable_tools(cls):
        """Every TOOL-category item is forgeable (existing + future tools)."""
        return sorted(
            name for name, cat in ITEM_CATEGORIES.items()
            if cat == "TOOL" and " " not in name
        )

    @classmethod
    def quote_tool_order(cls, tool_name, qty, building_manager=None, villager_manager=None):
        qty = max(1, int(qty or 1))
        materials = {item: int(amount) * qty for item, amount in TOOLMAKER_TOOL_RECIPE.items()}
        material_cost = BuilderSystem._material_cost(materials, building_manager)
        toolmakers = [v for v in (villager_manager.get_all_villagers() if villager_manager else [])
                      if getattr(v, "job", None) == "Toolmaker" and getattr(v, "is_alive", True)]
        family = villager_manager.get_family_by_id(toolmakers[0].family_id) if toolmakers and villager_manager else None
        household_size = max(
            1,
            len([m for m in getattr(family, "members", []) if getattr(m, "is_alive", True)]) if family else 1,
        )
        markets = MarketService.get_all_markets(building_manager)
        food_unit_price = BuilderSystem._food_unit_price(markets, minimum_stock=DAILY_FOOD_REQUIREMENT * household_size)
        wage = food_unit_price * DAILY_FOOD_REQUIREMENT * household_size
        return {
            "materials": materials,
            "material_cost_copper": material_cost,
            "living_wage_copper": wage,
            "price_copper": material_cost + wage,
            "food_unit_price_at_order": food_unit_price,
        }

    @classmethod
    def create_tool_order(cls, workbench, tool_name, qty, payer_family_id=None,
                          building_manager=None, villager_manager=None):
        """Queue a tool commission on a toolmaker workbench. Payer defaults to
        the landlord (player catalogue orders); household AI orders pass their
        family id and follow the normal household payment errand."""
        if not workbench or getattr(workbench, "furniture_type", "") != "toolmaker_workbench":
            return None, "Not a toolmaker workbench."
        if tool_name not in cls.craftable_tools():
            return None, f"{tool_name} is not a craftable tool."
        qty = max(1, min(100, int(qty or 1)))
        order = cls.quote_tool_order(tool_name, qty, building_manager, villager_manager)
        cls._order_seq += 1
        landlord_paid = payer_family_id is None
        order.update({
            "id": f"toolorder:{workbench.id}:{cls._order_seq}",
            "order_type": "TOOL_ORDER",
            "status": "LANDLORD_PAYMENT_PENDING" if landlord_paid else "AWAITING_PAYMENT",
            "payer_family_id": payer_family_id,
            "payer_type": "landlord" if landlord_paid else "household",
            "payer_id": "landlord" if landlord_paid else None,
            "builder_id": None,
            "artisan_job": "Toolmaker",
            "commission_paid": False,
            "tool_name": tool_name,
            "qty_total": qty,
            "qty_done": 0,
            "craft_progress": 0.0,
            "unit_duration_seconds": 0.0,
        })
        subject = ToolOrderSubject(workbench, order)
        if not isinstance(getattr(workbench, "tool_order_subjects", None), list):
            workbench.tool_order_subjects = []
        workbench.tool_order_subjects.append(subject)
        return subject, None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @classmethod
    def _toolmaker_workbenches(cls, furniture_manager, include_unfinished=False):
        out = []
        for f in getattr(furniture_manager, "furnitures", []):
            if getattr(f, "furniture_type", "") != "toolmaker_workbench":
                continue
            order = getattr(f, "construction_order", None)
            if not include_unfinished and isinstance(order, dict) and order.get("status") not in (None, "COMPLETE"):
                continue
            out.append(f)
        return out

    @classmethod
    def _tool_order_subjects(cls, furniture_manager):
        subjects = []
        for wb in cls._toolmaker_workbenches(furniture_manager):
            subjects.extend(getattr(wb, "tool_order_subjects", []) or [])
        return subjects

    @classmethod
    def _family_chest(cls, villager, furniture_manager):
        return (furniture_manager.get_storage_for_family(str(villager.family_id))
                if furniture_manager and getattr(villager, "family_id", None) else None)

    @classmethod
    def _chest_qty(cls, chest, item_name):
        if not chest:
            return 0
        inv = getattr(chest, "inventory", {}) or {}
        return max(0, int(inv.get(item_name, 0) or 0))

    @classmethod
    def _take_from_chest(cls, chest, item_name, amount):
        inv = getattr(chest, "inventory", None)
        if not isinstance(inv, dict):
            return 0
        actual = min(max(0, int(amount)), max(0, int(inv.get(item_name, 0) or 0)))
        if actual <= 0:
            return 0
        inv[item_name] -= actual
        if inv[item_name] <= 0:
            inv.pop(item_name, None)
        return actual

    @classmethod
    def _bars_today(cls, toolmaker, day_number):
        if getattr(toolmaker, "toolmaker_bars_day", -1) != int(day_number):
            toolmaker.toolmaker_bars_day = int(day_number)
            toolmaker.toolmaker_bars_smelted = 0
        return int(getattr(toolmaker, "toolmaker_bars_smelted", 0) or 0)

    # ------------------------------------------------------------------
    # Smelting: Iron Ore + Wood -> Iron Bar (10 ingame minutes per bar)
    # ------------------------------------------------------------------
    @classmethod
    def _smelt_step(cls, toolmaker, dt, furniture_manager, building_manager,
                    villager_manager, all_entities, player, day_cycle, for_order=False):
        """One smelting cycle at the nearest workbench. Returns True while busy."""
        day_number = getattr(day_cycle, "day_number", 1) if day_cycle else 1
        chest = cls._family_chest(toolmaker, furniture_manager)
        if chest is None:
            return False
        bars_in_chest = cls._chest_qty(chest, "Iron Bar")
        if not for_order:
            if bars_in_chest >= TOOLMAKER_BAR_STOCK_TARGET:
                return False
            if cls._bars_today(toolmaker, day_number) >= TOOLMAKER_BAR_DAILY_CAP:
                return False
        # Need ore + wood in the household chest.
        stock_targets = DEDICATED_JOBS.get("Toolmaker", {}).get("material_stock_target", {}) or {}
        missing = {}
        for item, amount in TOOLMAKER_BAR_RECIPE.items():
            curr = cls._chest_qty(chest, item)
            tgt = int(stock_targets.get(item, amount))
            if curr < int(amount):
                missing[item] = max(int(amount) - curr, tgt - curr)
        wood_target = int(stock_targets.get("Wood", 0))
        if wood_target > cls._chest_qty(chest, "Wood"):
            missing["Wood"] = max(missing.get("Wood", 0), wood_target - cls._chest_qty(chest, "Wood"))
        if missing:
            if cls._begin_material_restock(toolmaker, missing, building_manager,
                                           furniture_manager, villager_manager):
                return True
            return False
        benches = cls._toolmaker_workbenches(furniture_manager)
        if not benches:
            return False
        bench = min(benches, key=lambda b: math.hypot(
            b.get_world_pos(TILE_SIZE)[0] - toolmaker.x,
            b.get_world_pos(TILE_SIZE)[1] - toolmaker.y))
        dest = bench.get_approach_point(toolmaker.x, toolmaker.y, worker_id=toolmaker.id,
                                        all_entities=all_entities, tile_size=TILE_SIZE,
                                        bm=building_manager)
        arrived = toolmaker._move_towards(
            dest[0], dest[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=bench)
        if not arrived:
            toolmaker.task = "TOOLMAKER_SMELTING"
            return True
        toolmaker.task = "TOOLMAKER_SMELTING"
        toolmaker.toolmaker_smelt_timer = getattr(toolmaker, "toolmaker_smelt_timer", 0.0) + dt
        day_seconds = getattr(day_cycle, "day_length_seconds", 0) or 0
        minutes_seconds = (day_seconds / (24.0 * 60.0)) * TOOLMAKER_BAR_SMELT_INGAME_MINUTES if day_seconds else 0
        needed = max(1.0, minutes_seconds or TOOLMAKER_BAR_SMELT_INGAME_MINUTES)
        toolmaker._activity_total = needed
        if toolmaker.toolmaker_smelt_timer >= needed:
            for item, amount in TOOLMAKER_BAR_RECIPE.items():
                cls._take_from_chest(chest, item, int(amount))
            chest.store_item("Iron Bar", 1)
            toolmaker.toolmaker_bars_smelted = cls._bars_today(toolmaker, day_number) + 1
            toolmaker.toolmaker_smelt_timer = 0.0
            toolmaker.say("Smelted an Iron Bar.", duration=1.8)
        return True

    @classmethod
    def _begin_material_restock(cls, toolmaker, missing, building_manager,
                                furniture_manager, villager_manager):
        """Reuse Builder's market-buy errand (BUILDER_RESTOCK_* tasks are
        material-agnostic and resolved by ToolmakerSystem.update_worker)."""
        return BuilderSystem._begin_restock(
            toolmaker, missing, building_manager, furniture_manager, villager_manager)

    # ------------------------------------------------------------------
    # Tool order claiming & crafting
    # ------------------------------------------------------------------
    @classmethod
    def _select_tool_order(cls, toolmaker, furniture_manager):
        subjects = cls._tool_order_subjects(furniture_manager)
        awaiting = [s for s in subjects
                    if isinstance(getattr(s, "construction_order", None), dict)
                    and s.construction_order.get("status") == "AWAITING_PAYMENT"
                    and s.construction_order.get("builder_id") in (None, str(toolmaker.id))
                    and s.construction_order.get("artisan_job") == "Toolmaker"]
        if not awaiting:
            return None
        own = next((s for s in awaiting
                    if str(s.construction_order.get("payer_family_id")) == str(toolmaker.family_id)), None)
        return own or awaiting[0]

    @classmethod
    def _craftable_order(cls, toolmaker, furniture_manager):
        """Best active order for this toolmaker: earliest paid_seq among his
        CRAFTING/DELIVERING/PAID tool orders."""
        candidates = []
        for s in cls._tool_order_subjects(furniture_manager):
            order = getattr(s, "construction_order", None)
            if not isinstance(order, dict):
                continue
            if str(order.get("builder_id")) != str(toolmaker.id):
                continue
            if order.get("status") not in ("PAID", "CRAFTING", "AWAITING_MATERIAL", "DELIVERING"):
                continue
            BuilderSystem._ensure_paid_seq(order, furniture_manager, None)
            candidates.append((int(order.get("paid_seq", 0) or 0), s))
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])
        return candidates[0][1]

    @classmethod
    def _order_materials_ready(cls, order, chest):
        """Next unit's recipe must be in the toolmaker's household chest."""
        for item, amount in TOOLMAKER_TOOL_RECIPE.items():
            if cls._chest_qty(chest, item) < int(amount):
                return False
        return True

    @classmethod
    def _unit_seconds(cls, day_cycle):
        day_seconds = getattr(day_cycle, "day_length_seconds", 0) or 0
        hours = random.uniform(TOOLMAKER_TOOL_MIN_INGAME_HOURS, TOOLMAKER_TOOL_MAX_INGAME_HOURS)
        return max(1.0, (day_seconds / 24.0) * hours) if day_seconds else hours * 60.0

    @classmethod
    def _craft_step(cls, toolmaker, subject, dt, furniture_manager, building_manager,
                    villager_manager, all_entities, player, day_cycle,
                    stockpile_manager=None):
        order = subject.construction_order
        chest = cls._family_chest(toolmaker, furniture_manager)

        # DELIVERING: carry finished tools to the payer's storage.
        if order.get("status") == "DELIVERING":
            return cls._deliver_step(toolmaker, subject, dt, furniture_manager,
                                     building_manager, all_entities, player,
                                     stockpile_manager=stockpile_manager,
                                     villager_manager=villager_manager)

        if order.get("status") == "PAID":
            order["status"] = "CRAFTING"
            order["craft_progress"] = 0.0
            order["unit_duration_seconds"] = cls._unit_seconds(day_cycle)
            order["qty_done"] = int(order.get("qty_done", 0) or 0)

        if order.get("status") not in ("CRAFTING", "AWAITING_MATERIAL"):
            return True

        # Material gate: wood restock / bar smelting feed the bench.
        if not cls._order_materials_ready(order, chest):
            missing = {}
            for item, amount in TOOLMAKER_TOOL_RECIPE.items():
                short = int(amount) - cls._chest_qty(chest, item)
                if short > 0:
                    missing[item] = short
            wood_target = int((DEDICATED_JOBS.get("Toolmaker", {}).get("material_stock_target", {}) or {}).get("Wood", 0))
            if wood_target > cls._chest_qty(chest, "Wood"):
                missing["Wood"] = max(missing.get("Wood", 0), wood_target - cls._chest_qty(chest, "Wood"))
            if "Iron Bar" in missing:
                # 1. First priority: try smelting Iron Bar (bypass daily cap for active paid order)
                if cls._smelt_step(toolmaker, dt, furniture_manager, building_manager,
                                   villager_manager, all_entities, player, day_cycle, for_order=True):
                    order["status"] = "AWAITING_MATERIAL"
                    return True
                # If smelting could not start because chest lacks ore/wood, restock ore/wood in bulk to smelt:
                ore_missing = {}
                stock_targets = DEDICATED_JOBS.get("Toolmaker", {}).get("material_stock_target", {}) or {}
                for r_item, r_amt in TOOLMAKER_BAR_RECIPE.items():
                    c_qty = cls._chest_qty(chest, r_item)
                    if c_qty < int(r_amt):
                        ore_missing[r_item] = max(int(r_amt) - c_qty, int(stock_targets.get(r_item, 10)) - c_qty)
                if ore_missing and cls._begin_material_restock(toolmaker, ore_missing, building_manager,
                                                               furniture_manager, villager_manager):
                    order["status"] = "AWAITING_MATERIAL"
                    return True
                # 2. Second priority: if raw ore is not sold at market, can we buy Iron Bar directly?
                if cls._begin_material_restock(toolmaker, {"Iron Bar": missing["Iron Bar"]}, building_manager,
                                               furniture_manager, villager_manager):
                    order["status"] = "AWAITING_MATERIAL"
                    return True
                missing.pop("Iron Bar", None)
            if missing and cls._begin_material_restock(toolmaker, missing, building_manager,
                                                       furniture_manager, villager_manager):
                order["status"] = "AWAITING_MATERIAL"
                return True
            order["status"] = "AWAITING_MATERIAL"
            if not getattr(toolmaker, "speech_text", None):
                toolmaker.say("I need wood and iron before I can forge more tools.", duration=2.5)
            return True
        order["status"] = "CRAFTING"

        bench = subject.workbench
        dest = bench.get_approach_point(toolmaker.x, toolmaker.y, worker_id=toolmaker.id,
                                        all_entities=all_entities, tile_size=TILE_SIZE,
                                        bm=building_manager)
        arrived = toolmaker._move_towards(
            dest[0], dest[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=bench)
        if not arrived:
            toolmaker.task = "TOOLMAKER_CRAFTING"
            toolmaker.active_tool = "Hammer"
            return True

        toolmaker.task = "TOOLMAKER_CRAFTING"
        toolmaker.active_tool = "Hammer"
        order["craft_progress"] = float(order.get("craft_progress", 0.0)) + dt
        needed = max(1.0, float(order.get("unit_duration_seconds", 0.0) or cls._unit_seconds(day_cycle)))
        toolmaker._activity_total = needed
        if order["craft_progress"] >= needed:
            # Consume one unit's recipe from the household chest.
            for item, amount in TOOLMAKER_TOOL_RECIPE.items():
                cls._take_from_chest(chest, item, int(amount))
            tool_name = order.get("tool_name")
            toolmaker.inventory[tool_name] = int(toolmaker.inventory.get(tool_name, 0)) + 1
            from game.systems.work.tool_condition import ToolConditionSystem
            ToolConditionSystem.register_new_units(toolmaker, tool_name, 1)
            order["qty_done"] = int(order.get("qty_done", 0)) + 1
            order["craft_progress"] = 0.0
            order["unit_duration_seconds"] = cls._unit_seconds(day_cycle)
            remaining = int(order.get("qty_total", 1)) - int(order.get("qty_done", 0))
            if remaining <= 0:
                order["status"] = "DELIVERING"
                toolmaker.say(f"Finished the {order.get('qty_total')} {tool_name} order — delivering.", duration=2.5)
            else:
                toolmaker.say(f"Forged 1 {tool_name} ({order['qty_done']}/{order['qty_total']}).", duration=1.8)
        return True

    @classmethod
    def _deliver_step(cls, toolmaker, subject, dt, furniture_manager,
                      building_manager, all_entities, player,
                      stockpile_manager=None, villager_manager=None):
        order = subject.construction_order
        tool_name = order.get("tool_name")
        qty = int(order.get("qty_total", 1))
        carried = max(0, int(toolmaker.inventory.get(tool_name, 0)))
        if carried <= 0:
            order["status"] = "COMPLETE"
            toolmaker.task = "IDLE"
            return True

        # Destination: payer household chest, or Lord Treasury for landlord orders.
        payer_family = order.get("payer_family_id")
        dest_chest = None
        if order.get("payer_type") == "landlord" or payer_family in (None, "landlord"):
            from game.systems.economy.lord_treasury import LordTreasurySystem
            dest_chest = LordTreasurySystem.get_chest(furniture_manager)
        else:
            dest_chest = furniture_manager.get_storage_for_family(str(payer_family))

        if dest_chest is None:
            # No household chest: deliver the tools as owner-tagged loose
            # stacks. Household payers get the drop placed on a tile inside
            # their own permit (physically hauled there first) so the
            # family's "safe at home" check stops retrieve/drop loops;
            # landlord orders keep the at-feet fallback.
            if stockpile_manager is not None:
                owner_type = "landlord" if order.get("payer_type") == "landlord" else "villager"
                owner_id = None if order.get("payer_type") == "landlord" else str(payer_family)
                amount = min(carried, qty)
                drop_tile = None
                if owner_type == "villager":
                    permit_manager = getattr(toolmaker, "permit_manager", None)
                    vm = villager_manager or getattr(toolmaker, "villager_manager", None)
                    fam = None
                    if permit_manager is not None and vm is not None:
                        try:
                            fam = vm.get_family_by_id(str(payer_family))
                        except Exception:
                            fam = None
                    permit_id = getattr(fam, "assigned_permit_id", None)
                    if permit_id is not None:
                        from game.world.permits import resolve_household_ground_drop_tile
                        drop_tile = resolve_household_ground_drop_tile(
                            permit_id, permit_manager, building_manager,
                            furniture_manager=furniture_manager,
                            ref_x=toolmaker.x, ref_y=toolmaker.y)
                if drop_tile is not None:
                    dx = (drop_tile[0] + 0.5) * TILE_SIZE
                    dy = (drop_tile[1] + 0.5) * TILE_SIZE
                    arrived = toolmaker._move_towards(
                        dx, dy, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                        all_entities=all_entities, player=player,
                        building_manager=building_manager,
                        furniture_manager=furniture_manager,
                        exclusive_target=False)
                    toolmaker.task = "TOOLMAKER_DELIVERING"
                    if not arrived:
                        return True
                    gx, gy = drop_tile
                else:
                    gx = int(toolmaker.x // TILE_SIZE)
                    gy = int(toolmaker.y // TILE_SIZE)
                stockpile_manager.drop_resource(
                    tool_name, amount, gx, gy,
                    owner_type=owner_type, owner_id=owner_id)
                toolmaker.inventory[tool_name] = carried - amount
                if toolmaker.inventory[tool_name] <= 0:
                    toolmaker.inventory.pop(tool_name, None)
                    from game.systems.work.tool_condition import ToolConditionSystem
                    conds = getattr(toolmaker, "tool_conditions", {})
                    if isinstance(conds, dict):
                        conds.pop(tool_name, None)
                order["status"] = "COMPLETE"
                order["progress_ratio"] = 1.0
                toolmaker.task = "IDLE"
                toolmaker.active_tool = None
                toolmaker.say(f"Dropped {amount} {tool_name} — the household has no chest.", duration=2.5)
                return True
            if not getattr(toolmaker, "speech_text", None):
                toolmaker.say("The payer has no storage yet; tools are safe in my pack.", duration=3.0)
            toolmaker.task = "TOOLMAKER_DELIVERING"
            return True

        pos = dest_chest.get_approach_point(
            toolmaker.x, toolmaker.y, worker_id=toolmaker.id,
            all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
        arrived = toolmaker._move_towards(
            pos[0], pos[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=dest_chest)
        if arrived:
            amount = min(carried, qty)
            dest_chest.store_item(tool_name, amount)
            toolmaker.inventory[tool_name] = carried - amount
            if toolmaker.inventory[tool_name] <= 0:
                toolmaker.inventory.pop(tool_name, None)
                from game.systems.work.tool_condition import ToolConditionSystem
                conds = getattr(toolmaker, "tool_conditions", {})
                if isinstance(conds, dict):
                    conds.pop(tool_name, None)
            order["status"] = "COMPLETE"
            order["progress_ratio"] = 1.0
            toolmaker.task = "IDLE"
            toolmaker.active_tool = None
            toolmaker.say(f"Delivered {amount} {tool_name} to {dest_chest.name if hasattr(dest_chest,'name') else 'storage'}.", duration=2.5)
        else:
            toolmaker.task = "TOOLMAKER_DELIVERING"
        return True

    # ------------------------------------------------------------------
    # Entry point — called from Villager.update() inside WORK slots
    # ------------------------------------------------------------------
    @classmethod
    def update_worker(cls, toolmaker, dt, schedule_activity, building_manager,
                      furniture_manager, villager_manager, all_entities, player,
                      day_cycle, stockpile_manager=None, permit_manager=None):
        if getattr(toolmaker, "job", None) != "Toolmaker" or not furniture_manager:
            return False

        # Builder's market-restock errands are material-agnostic — reuse them.
        if str(getattr(toolmaker, "task", "")).startswith("BUILDER_RESTOCK_"):
            return BuilderSystem._update_restock(
                toolmaker, dt, building_manager, furniture_manager, villager_manager,
                all_entities, player, stockpile_manager=stockpile_manager,
                permit_manager=permit_manager)

        if schedule_activity != "WORK":
            return False

        # 1) Claim new tool commissions. Landlord-paid orders are dispatched
        #    by main.py's periodic servant-courier pass (real servant_manager).
        awaiting = cls._select_tool_order(toolmaker, furniture_manager)
        if awaiting is not None:
            BuilderSystem._claim_awaiting_order(
                toolmaker, awaiting, villager_manager, furniture_manager, stockpile_manager)

        # 2) Active craft/deliver order wins; otherwise smelt bars.
        active = cls._craftable_order(toolmaker, furniture_manager)
        if active is not None:
            return cls._craft_step(toolmaker, active, dt, furniture_manager,
                                   building_manager, villager_manager, all_entities,
                                   player, day_cycle, stockpile_manager=stockpile_manager)

        # 3) Automatic bar production keeps the household chest stocked.
        if cls._smelt_step(toolmaker, dt, furniture_manager, building_manager,
                           villager_manager, all_entities, player, day_cycle):
            return True

        # 4) Wood stock target restock when completely idle.
        chest = cls._family_chest(toolmaker, furniture_manager)
        wood_target = int((DEDICATED_JOBS.get("Toolmaker", {}).get("material_stock_target", {}) or {}).get("Wood", 0))
        if chest is not None and wood_target > cls._chest_qty(chest, "Wood"):
            missing = {"Wood": wood_target - cls._chest_qty(chest, "Wood")}
            if cls._begin_material_restock(toolmaker, missing, building_manager,
                                           furniture_manager, villager_manager):
                return True
        return False
