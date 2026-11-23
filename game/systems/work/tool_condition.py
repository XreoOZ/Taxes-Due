"""Per-unit tool condition lifecycle: PRISTINE -> GOOD -> WORN -> DAMAGED -> BROKEN.

Every TOOL-category item unit carries one condition label, stored on the
inventory owner's ``tool_conditions`` dict as ``{item_name: [cond, ...]}``
aligned by index with the item count in ``owner.inventory`` (or a stack's
``amount``). Lists are lazily reconciled, so plain ``inventory[name] += n``
transfers stay safe: new units default to PRISTINE and surplus tail entries
are dropped.

Every ``TOOL_CONDITION_CHECK_EVERY_DAYS`` in-game days each unit rolls
``TOOL_CONDITION_DEGRADE_CHANCE`` to drop one stage; BROKEN units are deleted.
"""
import random

from game.data.config import (
    ITEM_CATEGORIES,
    TOOL_CONDITION_STAGES,
    TOOL_CONDITION_DEGRADE_CHANCE,
    TOOL_CONDITION_CHECK_EVERY_DAYS,
)

PRISTINE = TOOL_CONDITION_STAGES[0]
BROKEN = TOOL_CONDITION_STAGES[-1]


def _is_tool_item(item_name):
    return ITEM_CATEGORIES.get(item_name) == "TOOL" or \
        ITEM_CATEGORIES.get(str(item_name).replace(" ", "_")) == "TOOL"


def _conditions_of(owner):
    conds = getattr(owner, "tool_conditions", None)
    if not isinstance(conds, dict):
        conds = {}
        try:
            owner.tool_conditions = conds
        except Exception:
            pass
    return conds


def _inventory_count(owner, item_name):
    inv = getattr(owner, "inventory", None)
    if isinstance(inv, dict):
        return max(0, int(inv.get(item_name, 0) or 0))
    # Loose stockpile stack: resource_type + amount.
    if getattr(owner, "resource_type", None) == item_name:
        return max(0, int(getattr(owner, "amount", 0) or 0))
    return 0


def _set_inventory_count(owner, item_name, count):
    inv = getattr(owner, "inventory", None)
    if isinstance(inv, dict):
        if count <= 0:
            inv.pop(item_name, None)
        else:
            inv[item_name] = count
        return
    if getattr(owner, "resource_type", None) == item_name:
        owner.amount = count


class ToolConditionSystem:
    _last_check_day = None

    @classmethod
    def sync_owner(cls, owner):
        """Pad/truncate condition lists so they match inventory counts."""
        conds = _conditions_of(owner)
        inv = getattr(owner, "inventory", None)
        if not isinstance(inv, dict):
            return
        for item_name in list(inv.keys()):
            if not _is_tool_item(item_name):
                continue
            count = max(0, int(inv.get(item_name, 0) or 0))
            lst = conds.setdefault(item_name, [])
            while len(lst) < count:
                lst.append(PRISTINE)
            if len(lst) > count:
                del lst[count:]
            if count <= 0:
                conds.pop(item_name, None)
        for item_name in list(conds.keys()):
            if item_name not in inv or int(inv.get(item_name, 0) or 0) <= 0:
                conds.pop(item_name, None)

    @classmethod
    def conditions_for(cls, owner, item_name):
        cls.sync_owner(owner)
        return list(_conditions_of(owner).get(item_name, []))

    @classmethod
    def register_new_units(cls, owner, item_name, amount):
        """Explicitly mark freshly crafted/bought units as PRISTINE."""
        if amount <= 0 or not _is_tool_item(item_name):
            return
        cls.sync_owner(owner)
        lst = _conditions_of(owner).setdefault(item_name, [])
        lst.extend([PRISTINE] * int(amount))

    @classmethod
    def _iter_tool_owners(cls, villager_manager, furniture_manager,
                          building_manager, stockpile_manager):
        if villager_manager:
            for v in villager_manager.get_all_villagers():
                yield v
        if furniture_manager:
            for f in getattr(furniture_manager, "furnitures", []):
                yield f
        if building_manager:
            for b in getattr(building_manager, "buildings", []):
                yield b
        if stockpile_manager:
            for s in getattr(stockpile_manager, "stacks", []):
                yield s

    @classmethod
    def daily_tick(cls, day_number, villager_manager=None, furniture_manager=None,
                   building_manager=None, stockpile_manager=None):
        """Every TOOL_CONDITION_CHECK_EVERY_DAYS days, each tool unit rolls
        TOOL_CONDITION_DEGRADE_CHANCE to drop one stage; BROKEN units vanish."""
        day_number = int(day_number or 1)
        interval = max(1, int(TOOL_CONDITION_CHECK_EVERY_DAYS))
        if cls._last_check_day is None:
            cls._last_check_day = day_number
            return
        if day_number - cls._last_check_day < interval:
            return
        cls._last_check_day = day_number

        for owner in cls._iter_tool_owners(villager_manager, furniture_manager,
                                           building_manager, stockpile_manager):
            cls.sync_owner(owner)
            conds = _conditions_of(owner)
            changed = False
            for item_name in list(conds.keys()):
                if not _is_tool_item(item_name):
                    continue
                count = _inventory_count(owner, item_name)
                lst = conds.get(item_name) or []
                new_lst = []
                removed = 0
                for cond in lst[:count]:
                    if cond == BROKEN:
                        removed += 1
                        changed = True
                        continue
                    if random.random() < TOOL_CONDITION_DEGRADE_CHANCE:
                        idx = TOOL_CONDITION_STAGES.index(cond)
                        cond = TOOL_CONDITION_STAGES[min(idx + 1, len(TOOL_CONDITION_STAGES) - 1)]
                        changed = True
                    new_lst.append(cond)
                if removed or changed:
                    conds[item_name] = new_lst
                    _set_inventory_count(owner, item_name, count - removed)
                    if count - removed <= 0:
                        conds.pop(item_name, None)
            if changed and hasattr(owner, "say") and getattr(owner, "say", None):
                try:
                    owner.say("Some of my tools are wearing out.", duration=2.0)
                except Exception:
                    pass
