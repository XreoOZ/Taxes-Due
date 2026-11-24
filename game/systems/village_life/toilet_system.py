"""
Toilet Building & Bodily Hygiene System (Agent 3)

Manages the gameplay logic for the Toilet building:
1. 1x1 Footprint, 5 Wood cost, No permit required.
2. Need Toilet decay, urgent threshold detection (<= 20%), and task interruption.
3. Nearest toilet searching & fair FIFO queuing with lateral staggered queue offsets.
4. Timed toilet usage, bodily need restoration (100%), and safe toilet release.
5. Task resumption (resumes interrupted activity or falls back to idle/schedule).
6. Robust fault tolerance: destroyed toilets, full queues, or missing facilities.
"""

import math
import time
from game.config import (
    TILE_SIZE,
    AI_NEED_MAX,
    AI_CRITICAL_NEED_THRESHOLD,
    AI_NEED_TOILET_DECAY_PER_DAY,
    AI_NEED_TOILET_URGENT_THRESHOLD,
    AI_NEED_TOILET_RESTORE,
    AI_NEED_SEEK_COOLDOWN_SECONDS,
    TOILET_USE_DURATION_SECONDS,
    TOILET_QUEUE_DISTANCE_PENALTY,
    TOILET_OCCUPIED_DISTANCE_PENALTY,
    TOILET_REEVALUATE_INTERVAL_SECONDS,
    TOILET_REEVALUATE_SCORE_MARGIN,
)
from game.world.navigation.navigation import find_nearest_target

TOILET_INTERACTION_RADIUS = 28.0


class ToiletSystem:
    _instance = None

    def __init__(self):
        self.active_users = {}   # toilet_id -> villager_id
        self.toilet_queues = {}  # toilet_id -> [villager_id, ...]
        self.user_timers = {}    # toilet_id -> elapsed_seconds

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ToiletSystem()
        return cls._instance

    @classmethod
    def get_completed_toilets(cls, building_manager):
        """Returns all completed, active Toilet buildings in the settlement."""
        if not building_manager:
            return []
        return [
            b for b in getattr(building_manager, "buildings", [])
            if (getattr(b, "building_type", "") == "toilet"
                and getattr(b, "is_available_for_use", True)
                and not getattr(b, "is_under_construction", False))
        ]

    @classmethod
    def calculate_toilet_score(cls, villager, toilet):
        """
        Calculates the weighted cost/score for a villager to use a toilet.
        Lower score is better.
        Score = Distance + Occupancy Penalty + (Queue Count * Queue Penalty).
        """
        if not toilet:
            return float("inf")

        pos = toilet.get_center_world(TILE_SIZE)
        if not pos:
            return float("inf")

        dx = pos[0] - getattr(villager, "x", 0.0)
        dy = pos[1] - getattr(villager, "y", 0.0)
        dist = math.hypot(dx, dy)

        vid_str = str(getattr(villager, "id", villager))
        active_user = getattr(toilet, "toilet_active_user", None) or getattr(toilet, "occupied_by", None)

        # If the inquiring villager is already the active user inside, score is just current distance
        if active_user == vid_str:
            return dist

        # Occupancy penalty: someone else is currently using it
        occ_penalty = TOILET_OCCUPIED_DISTANCE_PENALTY if active_user is not None else 0.0

        # Queue penalty: count others waiting ahead in queue
        queue = getattr(toilet, "toilet_queue", [])
        queue_count = sum(1 for q_vid in queue if q_vid != vid_str)
        queue_penalty = queue_count * TOILET_QUEUE_DISTANCE_PENALTY

        return dist + occ_penalty + queue_penalty

    @classmethod
    def find_best_toilet(cls, villager, building_manager, furniture_manager=None):
        """
        Finds the most suitable toilet for a villager using queue-aware cost scoring:
        - Balances geometric distance and waiting queue length to prevent bottlenecks.
        Returns: (toilet_building, is_free) or (None, False)
        """
        toilets = cls.get_completed_toilets(building_manager)
        if not toilets:
            return None, False

        best_toilet = None
        best_score = float("inf")
        vid_str = str(getattr(villager, "id", villager))

        for toilet in toilets:
            score = cls.calculate_toilet_score(villager, toilet)
            if score < best_score:
                best_score = score
                best_toilet = toilet

        if not best_toilet:
            return None, False

        active_user = getattr(best_toilet, "toilet_active_user", None) or getattr(best_toilet, "occupied_by", None)
        queue = getattr(best_toilet, "toilet_queue", [])
        is_free = (active_user is None or active_user == vid_str) and (not queue or queue == [vid_str])
        return best_toilet, is_free

    @classmethod
    def get_queue_position(cls, toilet, queue_idx, tile_size=TILE_SIZE):
        """
        Calculates a safe lateral queue position in front of the toilet.
        Staggers queue positions laterally so waiting villagers do not block doorways or roads.
        """
        if not toilet or not getattr(toilet, "tiles", None):
            return 0.0, 0.0

        min_tile = min(toilet.tiles, key=lambda t: (t[1], t[0]))
        cx = (min_tile[0] + 0.5) * tile_size
        cy = (min_tile[1] + 0.5) * tile_size

        # Queue extends south (bottom) from the 1x1 booth
        dist_offset = tile_size * (1.1 + queue_idx * 0.45)
        lateral_offset = 14.0 if (queue_idx % 2 == 1) else -14.0
        return cx + lateral_offset, cy + dist_offset

    @classmethod
    def request_toilet_access(cls, arg1, arg2, tile_size=TILE_SIZE):
        """
        Requests entry to a toilet:
        - If toilet is free and villager is first in line: grants immediate entry (True, target_pos).
        - If toilet is occupied or queue exists ahead: enqueues villager and returns queue position (False, queue_pos).
        """
        if hasattr(arg1, "toilet_queue") or hasattr(arg1, "building_type"):
            toilet, villager = arg1, arg2
        else:
            villager, toilet = arg1, arg2

        if not toilet or not villager:
            return False, None

        vid_str = str(getattr(villager, "id", villager))
        if not hasattr(toilet, "toilet_queue"):
            toilet.toilet_queue = []
        if not hasattr(toilet, "toilet_active_user"):
            toilet.toilet_active_user = None

        # Already active user inside
        if toilet.toilet_active_user == vid_str or getattr(toilet, "occupied_by", None) == vid_str:
            toilet.toilet_active_user = vid_str
            toilet.occupied_by = vid_str
            return True, None

        # Toilet is free and queue is empty or villager is first
        if toilet.toilet_active_user is None and getattr(toilet, "occupied_by", None) is None:
            if not toilet.toilet_queue or toilet.toilet_queue[0] == vid_str:
                toilet.toilet_active_user = vid_str
                toilet.occupied_by = vid_str
                toilet.toilet_use_timer = 0.0
                if toilet.toilet_queue and toilet.toilet_queue[0] == vid_str:
                    toilet.toilet_queue.pop(0)
                return True, None

        # Toilet is occupied or there is someone ahead in queue -> join queue
        if vid_str not in toilet.toilet_queue:
            toilet.toilet_queue.append(vid_str)
        q_idx = toilet.toilet_queue.index(vid_str)
        q_pos = cls.get_queue_position(toilet, q_idx, tile_size=tile_size)
        return False, q_pos

    @classmethod
    def release_toilet(cls, arg1, arg2):
        """Releases the toilet reservation when the user finishes or aborts."""
        if hasattr(arg1, "toilet_queue") or hasattr(arg1, "building_type"):
            toilet, villager = arg1, arg2
        else:
            villager, toilet = arg1, arg2

        if not toilet:
            return
        vid_str = str(getattr(villager, "id", villager))
        if getattr(toilet, "toilet_active_user", None) == vid_str:
            toilet.toilet_active_user = None
            toilet.toilet_use_timer = 0.0
        if getattr(toilet, "occupied_by", None) == vid_str:
            toilet.occupied_by = None
        if hasattr(toilet, "toilet_queue") and vid_str in toilet.toilet_queue:
            toilet.toilet_queue.remove(vid_str)

    @classmethod
    def update_toilet(cls, toilet, dt):
        """Updates toilet state and advances queues."""
        if not toilet:
            return
        if not hasattr(toilet, "toilet_queue"):
            toilet.toilet_queue = []
        if not hasattr(toilet, "toilet_active_user"):
            toilet.toilet_active_user = None
        if not hasattr(toilet, "toilet_use_timer"):
            toilet.toilet_use_timer = 0.0

        if toilet.toilet_active_user:
            toilet.toilet_use_timer += dt
            # Safety timeout: if a user is inside > 15s (stuck/dead), release toilet
            if toilet.toilet_use_timer > 15.0:
                toilet.toilet_active_user = None
                toilet.toilet_use_timer = 0.0

    @classmethod
    def execute_villager_toilet_routine(cls, villager, dt, building_manager, all_entities=None, player=None, furniture_manager=None):
        """
        Executes the toilet routine for a villager in task SEEKING_TOILET.
        Returns True if the routine is active/handled, False otherwise.
        """
        if getattr(villager, "task", "") != "SEEKING_TOILET":
            return False

        toilet = getattr(villager, "target_toilet", None)

        # Validate targeted toilet still exists
        all_toilets = cls.get_completed_toilets(building_manager)
        if toilet not in all_toilets:
            toilet, _ = cls.find_best_toilet(villager, building_manager, furniture_manager)
            villager.target_toilet = toilet
            if not toilet:
                # No toilet facility available in settlement: preserve need, wait/idle politely
                villager.say("I desperately need a Toilet, Lord! Please build an outhouse.", duration=2.5)
                villager._resume_or_idle_after_need()
                villager._set_need_seek_cooldown(
                    AI_NEED_SEEK_COOLDOWN_SECONDS,
                    task="SEEKING_TOILET",
                )
                return True

        # Dynamic load balancing re-evaluation:
        # Periodically check if another toilet has become significantly better (e.g. current one is backlogged).
        villager.toilet_reeval_timer = getattr(villager, "toilet_reeval_timer", 0.0) + dt
        if villager.toilet_reeval_timer >= TOILET_REEVALUATE_INTERVAL_SECONDS:
            villager.toilet_reeval_timer = 0.0
            vid_str = str(getattr(villager, "id", villager))
            active_user = getattr(toilet, "toilet_active_user", None) or getattr(toilet, "occupied_by", None)
            is_actively_relieving = (active_user == vid_str and getattr(villager, "toilet_use_timer", 0.0) > 0.0)
            if not is_actively_relieving and len(all_toilets) > 1:
                alt_toilet, _ = cls.find_best_toilet(villager, building_manager, furniture_manager)
                if alt_toilet and alt_toilet != toilet:
                    curr_score = cls.calculate_toilet_score(villager, toilet)
                    alt_score = cls.calculate_toilet_score(villager, alt_toilet)
                    if alt_score + TOILET_REEVALUATE_SCORE_MARGIN < curr_score:
                        was_in_queue = (
                            hasattr(toilet, "toilet_queue")
                            and vid_str in getattr(toilet, "toilet_queue", [])
                        )
                        cls.release_toilet(villager, toilet)
                        toilet = alt_toilet
                        villager.target_toilet = alt_toilet
                        if was_in_queue and not getattr(villager, "speech_text", None):
                            villager.say("Line is too long, heading to another toilet!", duration=1.8)

        can_enter, target_pos = cls.request_toilet_access(villager, toilet, tile_size=TILE_SIZE)
        if not target_pos:
            target_pos = toilet.get_center_world(TILE_SIZE)

        if not can_enter:
            # Waiting in queue
            arrived_queue = villager._move_towards(
                target_pos[0], target_pos[1], dt,
                arrival_dist=12.0,
                all_entities=all_entities,
                player=player,
                building_manager=building_manager,
                furniture_manager=furniture_manager,
                exclusive_target=False,
            )
            if arrived_queue:
                villager.is_moving = False
                if not getattr(villager, "speech_text", None):
                    villager.say("Waiting in line for the Toilet...", duration=2.0)
            return True

        # Can enter: move into toilet interior
        cx, cy = toilet.get_center_world(TILE_SIZE)
        arrived = villager._move_towards(
            cx, cy, dt,
            arrival_dist=10.0,
            all_entities=all_entities,
            player=player,
            building_manager=building_manager,
            furniture_manager=furniture_manager,
            exclusive_target=False,
            interaction_target=toilet,
        )

        if arrived:
            villager.is_moving = False
            villager.toilet_use_timer = getattr(villager, "toilet_use_timer", 0.0) + dt
            if not getattr(villager, "speech_text", None) and villager.toilet_use_timer < 0.5:
                villager.say("Relieving nature's call...", duration=1.8)

            if villager.toilet_use_timer >= TOILET_USE_DURATION_SECONDS:
                # Need satisfied!
                villager.need_toilet = float(AI_NEED_TOILET_RESTORE)
                villager.toilet_use_timer = 0.0
                cls.release_toilet(villager, toilet)
                villager.target_toilet = None
                villager.say("Refreshed and relieved!", duration=1.8)
                villager._resume_or_idle_after_need()

        return True
