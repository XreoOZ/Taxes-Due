"""
Immigration System — Notice Board attraction & immigrant household queue.

Flow:
  1. Landlord posts an immigration notice on a Notice Board furniture
     (reward gold per household + Post/Cancel via Town Ledger > Immigrant).
  2. Each in-game day with an active posting rolls IMMIGRATION_DAILY_SPAWN_CHANCE;
     on success 1..IMMIGRATION_MAX_HOUSEHOLDS_PER_DAY households are scheduled
     at random times during that day.
  3. Scheduled households spawn at the map edge in a random direction from the
     board, walk to queue slots in front of the board, and WAIT there.
  4. Landlord reviews the queue in the Immigrant tab: ACCEPT registers the
     household (homeless) and pays the reward via a Lord-Treasury grant order;
     REJECT makes them leave. Households left unattended for
     IMMIGRATION_PATIENCE_DAYS leave on their own. If the board is destroyed,
     moved, or stored, its queue disperses.

*** ESTABLISHED — DO NOT REGRESS ***
Pending immigrant members are Villager objects that are intentionally NOT in
villager_manager.families until accepted — they must never run normal villager
AI, consume needs, or appear in household census while waiting.
"""

import math
import random
import pygame

from game.data.config import (
    TILE_SIZE,
    IMMIGRATION_DAILY_SPAWN_CHANCE,
    IMMIGRATION_MIN_HOUSEHOLDS_PER_DAY,
    IMMIGRATION_MAX_HOUSEHOLDS_PER_DAY,
    IMMIGRATION_MIN_HOUSEHOLD_SIZE,
    IMMIGRATION_MAX_HOUSEHOLD_SIZE,
    IMMIGRATION_PATIENCE_DAYS,
    IMMIGRATION_SPAWN_DISTANCE_TILES,
    IMMIGRATION_DESPAWN_DISTANCE_TILES,
    IMMIGRATION_QUEUE_SLOTS_PER_ROW,
    IMMIGRATION_QUEUE_SLOT_SPACING,
    IMMIGRATION_QUEUE_ROW_SPACING,
    IMMIGRATION_MEMBER_JITTER,
    IMMIGRATION_DEFAULT_REWARD_GOLD,
)
from game.entities.villagers import Family, Villager
from game.ui.ui_theme import ui_font
from game.world.island import is_land_tile

STATE_TRAVELING = "TRAVELING"
STATE_WAITING = "WAITING"
STATE_LEAVING = "LEAVING"

_immigration_system = None


def get_immigration_system():
    global _immigration_system
    if _immigration_system is None:
        _immigration_system = ImmigrationSystem()
    return _immigration_system


class ImmigrationSystem:
    def __init__(self):
        self.postings = {}          # board_id -> posting dict
        self.pending = []           # list of pending household dicts
        self._counter = 0
        self.font_bubble = None

    # ------------------------------------------------------------------
    # Postings
    # ------------------------------------------------------------------
    def get_posting(self, board_id):
        return self.postings.get(board_id)

    def notice_boards(self, furniture_manager):
        """All placed (not dropped/stored) notice boards."""
        if not furniture_manager:
            return []
        return [
            f for f in getattr(furniture_manager, "furnitures", [])
            if getattr(f, "furniture_type", None) == "notice_board"
            and not getattr(f, "is_dropped", False)
            and getattr(f, "stored_in_id", None) is None
        ]

    def board_exists(self, board_id, furniture_manager):
        return any(getattr(f, "id", None) == board_id for f in self.notice_boards(furniture_manager))

    def set_reward(self, board_id, reward_gold):
        posting = self.postings.setdefault(board_id, self._new_posting())
        posting["reward_gold"] = max(0, int(reward_gold))

    def post(self, board_id):
        posting = self.postings.setdefault(board_id, self._new_posting())
        posting["posted"] = True
        posting["posted_day"] = getattr(self, "_current_day_number", 1)

    def cancel_post(self, board_id):
        posting = self.postings.get(board_id)
        if posting:
            posting["posted"] = False

    def is_posted(self, board_id):
        posting = self.postings.get(board_id)
        return bool(posting and posting.get("posted"))

    def reward_for(self, board_id):
        posting = self.postings.get(board_id)
        if posting and posting.get("reward_gold") is not None:
            return int(posting["reward_gold"])
        return IMMIGRATION_DEFAULT_REWARD_GOLD

    @staticmethod
    def _new_posting():
        return {
            "reward_gold": IMMIGRATION_DEFAULT_REWARD_GOLD,
            "posted": False,
            "posted_day": 1,
            "rolled_day": 0,
            "arrival_times": [],        # sorted absolute day-floats for today
        }

    # ------------------------------------------------------------------
    # Queue helpers
    # ------------------------------------------------------------------
    def households_for_board(self, board_id, states=(STATE_TRAVELING, STATE_WAITING)):
        return [h for h in self.pending
                if h["board_id"] == board_id and h["state"] in states]

    def find_household(self, household_id):
        return next((h for h in self.pending if h["id"] == household_id), None)

    def _queue_slot_pos(self, board, slot_index, tile_size=TILE_SIZE):
        """World position of queue slot `slot_index` in front of (south of) the board."""
        bw = max(1, int(getattr(board, "footprint_dimensions", (1, 1))[0]))
        bh = max(1, int(getattr(board, "footprint_dimensions", (1, 1))[1]))
        gx, gy = board.grid_x, board.grid_y
        row = slot_index // IMMIGRATION_QUEUE_SLOTS_PER_ROW
        col = slot_index % IMMIGRATION_QUEUE_SLOTS_PER_ROW
        # Center the row under the board footprint.
        row_start = row * IMMIGRATION_QUEUE_SLOTS_PER_ROW
        row_count = max(0, min(IMMIGRATION_QUEUE_SLOTS_PER_ROW,
                               len(self.pending) - row_start))
        start_offset = (bw * tile_size - row_count * IMMIGRATION_QUEUE_SLOT_SPACING) / 2.0
        x = gx * tile_size + start_offset + col * IMMIGRATION_QUEUE_SLOT_SPACING + IMMIGRATION_QUEUE_SLOT_SPACING / 2.0
        y = (gy + bh + 0.6 + row * IMMIGRATION_QUEUE_ROW_SPACING) * tile_size
        return (x, y)

    # ------------------------------------------------------------------
    # Spawning
    # ------------------------------------------------------------------
    def _current_day_float(self, day_cycle):
        if not day_cycle:
            return 1.0
        return float(getattr(day_cycle, "day_number", 1)) + float(getattr(day_cycle, "current_hour", 0.0)) / 24.0

    def _find_spawn_pos(self, board, tile_size=TILE_SIZE):
        """Random point on land at ~IMMIGRATION_SPAWN_DISTANCE_TILES from the board."""
        bx = (board.grid_x + 0.5) * tile_size
        by = (board.grid_y + 0.5) * tile_size
        dist_px = IMMIGRATION_SPAWN_DISTANCE_TILES * tile_size
        for _ in range(24):
            ang = random.uniform(0, math.pi * 2)
            dist = dist_px * random.uniform(0.9, 1.15)
            wx, wy = bx + math.cos(ang) * dist, by + math.sin(ang) * dist
            gx, gy = int(wx // tile_size), int(wy // tile_size)
            if is_land_tile(gx, gy):
                return (wx, wy)
        # Fallback: spiral search near board for any land tile.
        for r in range(2, IMMIGRATION_SPAWN_DISTANCE_TILES):
            for ang_i in range(16):
                ang = ang_i / 16.0 * math.pi * 2
                gx = int(board.grid_x + math.cos(ang) * r)
                gy = int(board.grid_y + math.sin(ang) * r)
                if is_land_tile(gx, gy):
                    return ((gx + 0.5) * tile_size, (gy + 0.5) * tile_size)
        return (bx + dist_px, by)

    def _spawn_household(self, board, day_cycle, villager_manager):
        size = random.randint(IMMIGRATION_MIN_HOUSEHOLD_SIZE, IMMIGRATION_MAX_HOUSEHOLD_SIZE)
        fam = villager_manager.generate_starter_family(size)
        # Pull the family OUT of the census — it only joins on ACCEPT.
        if fam in villager_manager.families:
            villager_manager.families.remove(fam)
        villager_manager.invalidate_villager_cache()

        spawn_x, spawn_y = self._find_spawn_pos(board)
        sx, sy = board.get_world_pos()
        # Queue slot = position among currently queued households for this board.
        slot_index = len(self.households_for_board(board.id))

        for i, m in enumerate(fam.members):
            m.x = spawn_x + random.uniform(-IMMIGRATION_MEMBER_JITTER, IMMIGRATION_MEMBER_JITTER)
            m.y = spawn_y + random.uniform(-IMMIGRATION_MEMBER_JITTER, IMMIGRATION_MEMBER_JITTER)
            m.is_moving = False
            m.current_path = []
            m.path_index = 0
            m.path_target = None
            m.task = "IMMIGRANT"
            m._immigrant_index = i

        self._counter += 1
        hh = {
            "id": f"imm_{self._counter}",
            "family": fam,
            "board_id": board.id,
            "slot_index": slot_index,
            "state": STATE_TRAVELING,
            "arrival_day": self._current_day_float(day_cycle),
            "leave_dir": None,
            "reward_gold": self.reward_for(board.id),
        }
        self.pending.append(hh)
        return hh

    # ------------------------------------------------------------------
    # Accept / Reject
    # ------------------------------------------------------------------
    def accept(self, household_id, villager_manager, servant_manager=None):
        hh = self.find_household(household_id)
        if not hh or hh["state"] not in (STATE_TRAVELING, STATE_WAITING):
            return False
        fam = hh["family"]
        # Officially join the census (homeless until a permit is issued).
        fam.assigned_permit_id = None
        fam.members = [m for m in fam.members if getattr(m, "is_alive", True)]
        for m in fam.members:
            m.task = "IDLE"
            m.is_moving = False
            m.current_path = []
        villager_manager.families.append(fam)
        villager_manager.invalidate_villager_cache()
        # Pay the reward: Lord Treasury -> household via servant grant order.
        reward = int(hh.get("reward_gold", 0))
        if reward > 0 and servant_manager is not None:
            order = {"family_id": fam.id, "item_type": "Gold", "amount": reward,
                     "in_transit": 0, "delivered": 0}
            # Deliver at the household's current position (they are homeless,
            # so the default chest/permit lookup would drop coins at the player).
            leader = fam.members[0] if fam.members else None
            if leader is not None:
                order["dest_pos"] = (leader.x, leader.y)
            servant_manager.grant_orders.append(order)
        self.pending.remove(hh)
        self._reindex_slots(hh["board_id"])
        return True

    def reject(self, household_id):
        hh = self.find_household(household_id)
        if not hh or hh["state"] not in (STATE_TRAVELING, STATE_WAITING):
            return False
        hh["state"] = STATE_LEAVING
        hh["leave_dir"] = random.uniform(0, math.pi * 2)
        return True

    def _reindex_slots(self, board_id):
        queued = [h for h in self.pending
                  if h["board_id"] == board_id and h["state"] in (STATE_TRAVELING, STATE_WAITING)]
        queued.sort(key=lambda h: h.get("slot_index", 0))
        for i, h in enumerate(queued):
            h["slot_index"] = i

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt, day_cycle, furniture_manager, villager_manager,
               servant_manager=None, building_manager=None, player=None,
               all_entities=None):
        if dt <= 0:
            return
        self._current_day_number = getattr(day_cycle, "day_number", 1) if day_cycle else 1
        day_float = self._current_day_float(day_cycle)
        boards = {b.id: b for b in self.notice_boards(furniture_manager)}

        # 1. Daily spawn rolls for active postings.
        for board_id, board in boards.items():
            posting = self.postings.get(board_id)
            if not posting or not posting.get("posted"):
                continue
            today = self._current_day_number
            if posting.get("rolled_day") != today:
                posting["rolled_day"] = today
                # Roll once per day: on success schedule ALL of today's arrivals
                # at random times spread across the remaining day.
                count = 0
                if random.random() < IMMIGRATION_DAILY_SPAWN_CHANCE:
                    count = random.randint(
                        IMMIGRATION_MIN_HOUSEHOLDS_PER_DAY,
                        IMMIGRATION_MAX_HOUSEHOLDS_PER_DAY)
                day_start = float(today)
                earliest = max(day_float, day_start + 0.05)
                latest = day_start + 1.0 - 0.02
                times = []
                if count > 0 and earliest < latest:
                    times = sorted(random.uniform(earliest, latest) for _ in range(count))
                posting["arrival_times"] = times
            # Fire any arrivals whose scheduled time has come.
            while posting.get("arrival_times") and day_float >= posting["arrival_times"][0]:
                posting["arrival_times"].pop(0)
                self._spawn_household(board, day_cycle, villager_manager)

        # 2. Drop postings for boards that no longer exist.
        for board_id in list(self.postings.keys()):
            if board_id not in boards:
                del self.postings[board_id]

        # 3. Update pending households.
        entities = list(all_entities) if all_entities else []
        for hh in list(self.pending):
            board = boards.get(hh["board_id"])
            fam = hh["family"]
            members = [m for m in fam.members if getattr(m, "is_alive", True)]
            if not members:
                self.pending.remove(hh)
                continue

            # Board gone (destroyed/moved/stored) -> everyone leaves.
            if board is None and hh["state"] in (STATE_TRAVELING, STATE_WAITING):
                hh["state"] = STATE_LEAVING
                hh["leave_dir"] = random.uniform(0, math.pi * 2)

            if hh["state"] in (STATE_TRAVELING, STATE_WAITING):
                # Unattended for a full day -> leaves on its own.
                if day_float - hh.get("arrival_day", day_float) >= IMMIGRATION_PATIENCE_DAYS:
                    hh["state"] = STATE_LEAVING
                    hh["leave_dir"] = random.uniform(0, math.pi * 2)

            # Anchor point: the board while it exists, else first member.
            anchor = board if board is not None else members[0]
            ax, ay = anchor.get_world_pos() if hasattr(anchor, "get_world_pos") else (anchor.x, anchor.y)

            if hh["state"] == STATE_LEAVING and hh.get("leave_target") is None:
                if hh.get("leave_dir") is None:
                    hh["leave_dir"] = random.uniform(0, math.pi * 2)
                # Fixed far-away target so _move_towards does not re-path every frame.
                hh["leave_target"] = (ax + math.cos(hh["leave_dir"]) * IMMIGRATION_DESPAWN_DISTANCE_TILES * 2 * TILE_SIZE,
                                      ay + math.sin(hh["leave_dir"]) * IMMIGRATION_DESPAWN_DISTANCE_TILES * 2 * TILE_SIZE)

            # Per-member movement.
            all_alive = entities + [m for m in members]
            for m in members:
                if hh["state"] == STATE_LEAVING:
                    # Walk to a fixed far target, then despawn once beyond range.
                    dist_board = math.hypot(m.x - ax, m.y - ay)
                    if dist_board > IMMIGRATION_DESPAWN_DISTANCE_TILES * TILE_SIZE:
                        m.is_moving = False
                        continue
                    lt = hh.get("leave_target")
                    if lt is None:
                        lt = (m.x + math.cos(hh["leave_dir"]) * TILE_SIZE,
                              m.y + math.sin(hh["leave_dir"]) * TILE_SIZE)
                    m._move_towards(lt[0], lt[1], dt, arrival_dist=TILE_SIZE,
                                    all_entities=all_alive, player=player,
                                    building_manager=building_manager,
                                    furniture_manager=furniture_manager)
                    continue

                if hh["state"] == STATE_TRAVELING and board is not None:
                    slot_pos = self._queue_slot_pos(board, hh["slot_index"])
                    jx = math.sin(m._immigrant_index * 2.3) * IMMIGRATION_MEMBER_JITTER
                    jy = math.cos(m._immigrant_index * 1.7) * IMMIGRATION_MEMBER_JITTER
                    tx, ty = slot_pos[0] + jx, slot_pos[1] + jy
                    arrived = m._move_towards(tx, ty, dt, arrival_dist=14,
                                              all_entities=all_alive, player=player,
                                              building_manager=building_manager,
                                              furniture_manager=furniture_manager)
                    if arrived:
                        m.is_moving = False
                else:
                    # WAITING: stand at slot, tiny idle shuffle disabled.
                    m.is_moving = False
                    m.current_path = []

            # All members arrived -> WAITING.
            if hh["state"] == STATE_TRAVELING and board is not None:
                if all(math.hypot(m.x - (self._queue_slot_pos(board, hh["slot_index"])[0]),
                                  m.y - (self._queue_slot_pos(board, hh["slot_index"])[1])) < TILE_SIZE
                       for m in members):
                    hh["state"] = STATE_WAITING

            # Despawn leaving households out of view.
            if hh["state"] == STATE_LEAVING:
                cx, cy = ax, ay
                far = all(math.hypot(m.x - cx, m.y - cy) > IMMIGRATION_DESPAWN_DISTANCE_TILES * TILE_SIZE
                          for m in members)
                if far:
                    self.pending.remove(hh)
                    self._reindex_slots(hh["board_id"])

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    def draw(self, surface, camera, tile_size=TILE_SIZE):
        self._ensure_font()
        for hh in self.pending:
            for m in hh["family"].members:
                if not getattr(m, "is_alive", True):
                    continue
                radius = max(0, float(getattr(m, "radius", 0)))
                if not camera.is_world_rect_visible(m.x - radius, m.y - radius, radius * 2, radius * 2):
                    continue
                m.draw(surface, camera, self.font_bubble)

    def _ensure_font(self):
        if self.font_bubble is None:
            self.font_bubble = ui_font(16)

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------
    def serialize(self):
        return {
            "postings": {
                bid: {
                    "reward_gold": int(p.get("reward_gold", IMMIGRATION_DEFAULT_REWARD_GOLD)),
                    "posted": bool(p.get("posted")),
                    "posted_day": int(p.get("posted_day", 1)),
                    "rolled_day": int(p.get("rolled_day", 0)),
                    "arrival_times": list(p.get("arrival_times") or []),
                } for bid, p in self.postings.items()
            },
            "pending": [self._serialize_household(h) for h in self.pending],
            "counter": self._counter,
        }

    def _serialize_household(self, hh):
        fam = hh["family"]
        return {
            "id": hh["id"],
            "board_id": hh["board_id"],
            "slot_index": hh.get("slot_index", 0),
            "state": hh["state"],
            "arrival_day": hh.get("arrival_day"),
            "leave_dir": hh.get("leave_dir"),
            "reward_gold": hh.get("reward_gold"),
            "family": {
                "id": fam.id,
                "surname": fam.surname,
                "members": [
                    {
                        "id": m.id,
                        "first_name": getattr(m, "first_name", ""),
                        "last_name": getattr(m, "last_name", ""),
                        "gender": getattr(m, "gender", "Male"),
                        "age": getattr(m, "age", 30),
                        "generation": getattr(m, "generation", 2),
                        "role": getattr(m, "role", "Citizen"),
                        "family_id": fam.id,
                        "x": m.x,
                        "y": m.y,
                        "is_alive": getattr(m, "is_alive", True),
                    } for m in fam.members
                ],
            },
        }

    def deserialize(self, data, villager_manager):
        self.postings = {}
        for bid, p in (data.get("postings") or {}).items():
            base = self._new_posting()
            base.update({k: v for k, v in p.items() if k in base})
            self.postings[bid] = base
        self.pending = []
        self._counter = int(data.get("counter", 0))
        for h in (data.get("pending") or []):
            fd = h.get("family") or {}
            members = []
            for md in fd.get("members", []):
                members.append(Villager(
                    md.get("id", f"vil_imm_{self._counter}"),
                    md.get("first_name", "Immigrant"),
                    md.get("last_name", ""),
                    md.get("gender", "Male"),
                    int(md.get("age", 30)),
                    int(md.get("generation", 2)),
                    md.get("role", "Citizen"),
                    fd.get("id"),
                    x=float(md.get("x", 0.0)),
                    y=float(md.get("y", 0.0)),
                ))
                members[-1].is_alive = bool(md.get("is_alive", True))
                members[-1].task = "IMMIGRANT"
                members[-1]._immigrant_index = len(members) - 1
            fam = Family(fd.get("id", f"fam_imm_{self._counter}"),
                          fd.get("surname", "Immigrant"), members,
                          assigned_permit_id=None)
            self.pending.append({
                "id": h.get("id", f"imm_{self._counter}"),
                "family": fam,
                "board_id": h.get("board_id"),
                "slot_index": int(h.get("slot_index", 0)),
                "state": h.get("state", STATE_WAITING),
                "arrival_day": h.get("arrival_day"),
                "leave_dir": h.get("leave_dir"),
                "reward_gold": h.get("reward_gold"),
            })
            self._counter += 1
        # Ensure pending family ids never collide with the census counter.
        if villager_manager is not None:
            for hh in self.pending:
                fam = hh["family"]
                if fam.id in {f.id for f in villager_manager.families}:
                    fam.id = f"{fam.id}_imm"
                    for m in fam.members:
                        m.family_id = fam.id
