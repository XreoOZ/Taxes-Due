"""Artisan-generic commission lifecycle: dead-artisan sweep and refund errands.

Extracted from carpenter_system.py — every order carries an "artisan_job"
field so Blacksmith/Baker/etc. reuse the same queue, payment, and
refund flows. CarpenterSystem keeps thin delegating wrappers for
backward compatibility.
"""

import math

from game.data.config import TILE_SIZE, CHEST_INTERACTION_RADIUS, LOOSE_ITEM_ARRIVAL_DIST
from game.systems.economy.currency import (
    canonical_denomination,
    compact_currency_wallet,
    from_copper,
    normalize_wallet,
    to_copper,
)


class ArtisanCommissionSystem:
    """Death-sweep + refund errands for paid artisan commissions (any job)."""

    @classmethod
    def sweep_dead_commission_orders(cls, building_manager, furniture_manager,
                                     villager_manager, servant_manager=None,
                                     stockpile_manager=None, day_cycle=None):
        from game.systems.work.carpenter_system import CarpenterSystem
        """Called once per frame. When the artisan holding queued commissions
        dies (or loses the job), every order assigned to him is released:

        - PAID orders spawn a refund errand (household rep collects from the
          artisan's family funds; landlord orders go through a servant) and
          the order resets to unpaid so another artisan can re-commission it.
        - Orders still in payment/material transit simply lose their
          carpenter_id — payment flows self-heal via existing dead-artisan
          checks, and the order becomes claimable again.

        Artisan-agnostic: each order's "artisan_job" decides which job the
        assigned worker must hold (defaults to Carpenter via config).
        """
        if not building_manager or not furniture_manager or not villager_manager:
            return
        villagers = villager_manager.get_all_villagers()
        by_id = {str(getattr(v, "id", "")): v for v in villagers}
        for subject in CarpenterSystem._order_subjects(furniture_manager, building_manager):
            order = getattr(subject, "construction_order", None)
            if not isinstance(order, dict):
                continue
            cid = order.get("carpenter_id")
            artisan = CarpenterSystem._artisan_job(order)
            carpenter = by_id.get(str(cid)) if cid is not None else None
            worker_gone = (carpenter is None
                           or not getattr(carpenter, "is_alive", True)
                           or getattr(carpenter, "job", None) != artisan)
            assigned_gone = (
                (cid is not None and worker_gone)
                or (cid is None and order.get("status") == "PAID"
                    and order.get("commission_paid") is True)
            )
            if not assigned_gone:
                continue
            if order.get("status") == "PAID":
                cls._begin_commission_refund(
                    order, carpenter, furniture_manager, building_manager,
                    villager_manager, servant_manager, stockpile_manager)
                # Reset to unpaid so the order can be re-commissioned; the
                # refund errand returns the fee independently.
                landlord_paid = (order.get("paid_by_id") == "landlord"
                                 or order.get("payer_type") == "landlord"
                                 or order.get("payer_id") == "landlord")
                order["status"] = "LANDLORD_PAYMENT_PENDING" if landlord_paid else "AWAITING_PAYMENT"
                if landlord_paid:
                    order["payer_type"] = "landlord"
                    order["payer_id"] = "landlord"
                else:
                    order["payer_id"] = None
                order["carpenter_id"] = None
                order["commission_paid"] = False
                order.pop("paid_seq", None)
                order.pop("_claim_retry_at", None)
            else:
                # Payment/material transit: release the slot; the flow
                # self-heals (dead-carpenter checks reset it to unpaid).
                order["carpenter_id"] = None

    @classmethod
    def _begin_commission_refund(cls, order, dead_carpenter, furniture_manager,
                                 building_manager, villager_manager,
                                 servant_manager, stockpile_manager):
        amount = max(0, int(order.get("paid_amount_copper")
                            or order.get("price_copper") or 0))
        if amount <= 0 or order.get("refund_issued"):
            return
        landlord_paid = (order.get("paid_by_id") == "landlord"
                         or order.get("payer_type") == "landlord"
                         or order.get("payer_id") == "landlord")
        to_family = order.get("paid_by_family_id") or order.get("payer_family_id")
        from_family = (getattr(dead_carpenter, "family_id", None)
                       or order.get("carpenter_family_id"))
        if landlord_paid:
            if cls._dispatch_servant_refund(order, amount, from_family,
                                            furniture_manager, servant_manager):
                order["refund_issued"] = True
        elif to_family is not None:
            if cls._dispatch_villager_refund(order, amount, from_family, to_family,
                                             furniture_manager, villager_manager,
                                             stockpile_manager):
                order["refund_issued"] = True

    @classmethod
    def _dispatch_servant_refund(cls, order, amount, from_family,
                                 furniture_manager, servant_manager):
        """Landlord-paid commission: an AI servant recovers coins from the
        deceased carpenter's household funds and returns them to the Treasury."""
        if not servant_manager:
            return False
        servant = next((s for s in getattr(servant_manager, "servants", [])
                        if getattr(s, "is_alive", True)
                        and getattr(s, "state", "IDLE") == "IDLE"), None)
        if not servant:
            return False
        servant.carpenter_refund_from_family = from_family
        servant.carpenter_refund_amount = amount
        servant.state = "COMMISSION_REFUND_COLLECT"
        servant.say("I will recover the refunded commission coins, my Lord.", duration=2.5)
        return True

    @classmethod
    def _dispatch_villager_refund(cls, order, amount, from_family, to_family,
                                  furniture_manager, villager_manager,
                                  stockpile_manager):
        """Household-paid commission: a surviving member of the paying
        household travels to the carpenter's home and collects the refund
        from that household's funds (chest, loose stacks, wallets, treasury)."""
        family = villager_manager.get_family_by_id(to_family) if villager_manager else None
        survivors = [m for m in getattr(family, "members", [])
                     if getattr(m, "is_alive", True)] if family else []
        rep = next((m for m in survivors
                    if getattr(m, "task", "") not in (
                        "SEEKING_FOOD", "SEEKING_WATER", "SEEKING_TOILET",
                        "RECOVER_DEATH_ITEMS", "COMMISSION_REFUND_COLLECT")
                    and getattr(m, "hunger", 100.0) > 20.0
                    and getattr(m, "thirst", 100.0) > 20.0
                    and getattr(m, "need_toilet", 100.0) > 20.0), None)
        if rep is None and survivors:
            rep = survivors[0]
        if rep is None:
            return False
        from game.systems.work.commission_schedule import CommissionScheduleSystem
        CommissionScheduleSystem.queue(
            rep, "COMMISSION_REFUND_COLLECT",
            carpenter_payment_order_id=order.get("id"),
            carpenter_refund_from_family=from_family,
            carpenter_refund_to_family=to_family,
            carpenter_refund_amount=amount,
        )
        rep.say("I will collect the carpenter's commission refund.", duration=2.5)
        return True

    @classmethod
    def _clear_refund_task(cls, villager):
        villager.carpenter_payment_order_id = None
        villager.carpenter_refund_from_family = None
        villager.carpenter_refund_to_family = None
        villager.carpenter_refund_amount = 0
        villager.carpenter_refund_phase = None

    @classmethod
    def _update_refund_task(cls, villager, dt, building_manager, furniture_manager,
                            stockpile_manager, all_entities, player, villager_manager):
        from game.systems.work.carpenter_system import CarpenterSystem
        """COMMISSION_REFUND_COLLECT: household rep walks to the deceased
        carpenter's household funds, collects the fee, then delivers it to the
        paying household's storage (or drops it as household-owned coins if
        the payer has no chest)."""
        subject = CarpenterSystem._find_subject_by_order_id(
            getattr(villager, "carpenter_payment_order_id", None),
            furniture_manager, building_manager)
        amount = max(0, int(getattr(villager, "carpenter_refund_amount", 0) or 0))
        if subject is None or amount <= 0:
            cls._clear_refund_task(villager)
            villager._resume_or_idle_after_need()
            return True
        phase = getattr(villager, "carpenter_refund_phase", None) or "COLLECT"
        carried = to_copper(normalize_wallet(villager.inventory))
        if phase == "COLLECT":
            if carried >= amount:
                villager.carpenter_refund_phase = "RETURN"
                return True
            cls._refund_collect_step(
                villager, amount, dt, building_manager, furniture_manager,
                stockpile_manager, all_entities, player, villager_manager)
            return True
        # RETURN: deliver collected coins to the paying household's storage.
        to_family = getattr(villager, "carpenter_refund_to_family", None)
        dest_chest = (furniture_manager.get_storage_for_family(to_family)
                      if furniture_manager else None)
        if dest_chest is None:
            gx = int(villager.x // TILE_SIZE)
            gy = int(villager.y // TILE_SIZE)
            for denom, value in from_copper(carried).items():
                if value:
                    stockpile_manager.drop_resource(
                        denom, value, gx, gy,
                        owner_type="villager", owner_id=str(to_family))
            cls._clear_refund_task(villager)
            villager.say("Commission refund delivered.", duration=2.0)
            villager._resume_or_idle_after_need()
            return True
        pos = dest_chest.get_approach_point(
            villager.x, villager.y, worker_id=villager.id,
            all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
        arrived = villager._move_towards(
            pos[0], pos[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=dest_chest)
        if arrived:
            pay = min(amount, to_copper(normalize_wallet(villager.inventory)))
            if pay > 0:
                CarpenterSystem._move_exact_value(villager.inventory, dest_chest.inventory, pay)
            cls._clear_refund_task(villager)
            villager.say("Commission refund delivered.", duration=2.0)
            villager._resume_or_idle_after_need()
        return True

    @classmethod
    def _refund_collect_step(cls, villager, amount, dt, building_manager,
                             furniture_manager, stockpile_manager,
                             all_entities, player, villager_manager):
        from game.systems.work.carpenter_system import CarpenterSystem
        """One collection attempt per tick: carpenter family chest -> loose
        coin stacks -> abstract wallets -> Lord Treasury backstop."""
        from_family = getattr(villager, "carpenter_refund_from_family", None)
        carried = to_copper(normalize_wallet(villager.inventory))
        remaining = amount - carried
        if remaining <= 0:
            villager.carpenter_refund_phase = "RETURN"
            return
        # 1) Carpenter household chest (physical visit to the family home).
        src_chest = (furniture_manager.get_storage_for_family(from_family)
                     if furniture_manager else None)
        if src_chest is not None and to_copper(normalize_wallet(src_chest.inventory)) > 0:
            pos = src_chest.get_approach_point(
                villager.x, villager.y, worker_id=villager.id,
                all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
            arrived = villager._move_towards(
                pos[0], pos[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
                interaction_target=src_chest)
            if arrived:
                take = min(remaining, to_copper(normalize_wallet(src_chest.inventory)))
                CarpenterSystem._move_exact_value(src_chest.inventory, villager.inventory, take)
                compact_currency_wallet(villager.inventory)
                villager.carpenter_refund_phase = (
                    "RETURN" if to_copper(normalize_wallet(villager.inventory)) >= amount
                    else villager.carpenter_refund_phase or "COLLECT")
            return
        # 2) Loose coin stacks owned by the carpenter's household.
        stacks = [s for s in CarpenterSystem._family_coin_stacks(from_family, stockpile_manager)
                  if int(getattr(s, "amount", 0)) > 0]
        if stacks:
            stack = min(stacks, key=lambda s: math.hypot(
                (s.grid_x + 0.5) * TILE_SIZE - villager.x,
                (s.grid_y + 0.5) * TILE_SIZE - villager.y))
            sx, sy = (stack.grid_x + 0.5) * TILE_SIZE, (stack.grid_y + 0.5) * TILE_SIZE
            arrived = villager._move_towards(
                sx, sy, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST,
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
                interaction_target=stack)
            if arrived:
                denom = canonical_denomination(stack.resource_type)
                denom_value = to_copper({denom: 1})
                take = min(int(stack.amount), max(1, math.ceil(remaining / max(1, denom_value))))
                stack.amount -= take
                if stack.amount <= 0:
                    if stack in stockpile_manager.stacks:
                        stockpile_manager.stacks.remove(stack)
                    stockpile_manager.mark_totals_dirty()
                villager.inventory[denom] = int(villager.inventory.get(denom, 0)) + take
                compact_currency_wallet(villager.inventory)
                if to_copper(normalize_wallet(villager.inventory)) >= amount:
                    villager.carpenter_refund_phase = "RETURN"
            return
        # 3) Abstract household wallets (family purse + member pockets).
        for wallet in CarpenterSystem._family_abstract_wallets(from_family, villager_manager):
            remaining = amount - to_copper(normalize_wallet(villager.inventory))
            if remaining <= 0:
                break
            take = min(remaining, to_copper(normalize_wallet(wallet)))
            if take > 0:
                CarpenterSystem._move_exact_value(wallet, villager.inventory, take)
        if to_copper(normalize_wallet(villager.inventory)) >= amount:
            villager.carpenter_refund_phase = "RETURN"
            return
        # 4) Lord Treasury backstop: the refund must not vanish if the
        # carpenter's household is wiped out.
        from game.systems.economy.lord_treasury import LordTreasurySystem
        remaining = amount - to_copper(normalize_wallet(villager.inventory))
        treasury_value = LordTreasurySystem.value(furniture_manager)
        take = min(remaining, treasury_value)
        if take > 0:
            LordTreasurySystem.withdraw_covering(furniture_manager, villager.inventory, take)
        villager.carpenter_refund_phase = "RETURN"

