"""Population-scaled, staggered decision ticks for individual AI actors."""

from game.config import (
    AI_ACTIVE_MAX_INTERVAL_SECONDS,
    AI_DECISION_MAX_INTERVAL_SECONDS,
    AI_DECISION_REFERENCE_POPULATION,
    AI_DECISION_TICK_INTERVAL_SECONDS,
)


class AISimulationScheduler:
    """Run each actor's existing state machine at a configurable, staggered cadence."""

    @staticmethod
    def interval_for_population(population):
        reference = max(1, int(AI_DECISION_REFERENCE_POPULATION))
        base_interval = max(0.001, float(AI_DECISION_TICK_INTERVAL_SECONDS))
        max_interval = max(base_interval, float(AI_DECISION_MAX_INTERVAL_SECONDS))
        scale = max(1.0, max(0, int(population)) / reference)
        return min(max_interval, base_interval * scale)

    @staticmethod
    def active_interval_for_population(population, base_active=None):
        """Scale moving-actor tick interval gently at huge populations; render interpolation keeps 60 FPS smooth."""
        reference = max(1, int(AI_DECISION_REFERENCE_POPULATION) * 2)
        base = max(0.001, float(base_active or AI_DECISION_TICK_INTERVAL_SECONDS))
        max_active = max(base, float(AI_ACTIVE_MAX_INTERVAL_SECONDS))
        scale = max(1.0, max(0, int(population)) / reference)
        return min(max_active, base * scale)

    @staticmethod
    def update_actors(actors, dt, interval, update_actor, active_interval=None):
        """Advance every actor's accumulated simulation time, staggering expensive state updates."""
        actor_count = len(actors)
        if actor_count <= 0:
            return 0

        interval = max(0.001, float(interval))
        active_interval = max(0.001, float(active_interval or interval))
        updates = 0
        for index, actor in enumerate(actors):
            actor_interval = (
                active_interval
                if getattr(actor, "is_moving", False) or getattr(actor, "is_waiting_for_path", False)
                else interval
            )
            if not hasattr(actor, "_ai_tick_accumulator"):
                actor._ai_tick_phase = index / actor_count
                actor._ai_tick_delay = actor_interval * actor._ai_tick_phase
                actor._ai_tick_accumulator = 0.0
                actor._ai_tick_interval = actor_interval
            else:
                actor._ai_tick_phase = getattr(actor, "_ai_tick_phase", index / actor_count)
                actor._ai_tick_interval = actor_interval

            frame_dt = max(0.0, dt)
            delay = max(0.0, float(getattr(actor, "_ai_tick_delay", 0.0)))
            delay_consumed = min(frame_dt, delay)
            actor._ai_tick_delay = delay - delay_consumed
            frame_dt -= delay_consumed
            elapsed = max(0.0, float(getattr(actor, "_ai_tick_accumulator", 0.0))) + frame_dt
            steps = 0
            while elapsed >= actor_interval and steps < 2:
                actor._ai_render_previous_position = (actor.x, actor.y)
                update_actor(actor, actor_interval)
                updates += 1
                elapsed -= actor_interval
                steps += 1
                actor_interval = (
                    active_interval
                    if getattr(actor, "is_moving", False) or getattr(actor, "is_waiting_for_path", False)
                    else interval
                )
                actor._ai_tick_interval = actor_interval
            actor._ai_tick_accumulator = min(elapsed, actor_interval)
        return updates

    @staticmethod
    def render_alpha(actor, interval):
        interval = max(0.001, float(getattr(actor, "_ai_tick_interval", interval)))
        elapsed = max(0.0, float(getattr(actor, "_ai_tick_accumulator", 0.0)))
        return min(1.0, elapsed / interval)

    @staticmethod
    def render_position(actor, alpha):
        previous = getattr(actor, "_ai_render_previous_position", (actor.x, actor.y))
        alpha = max(0.0, min(1.0, float(alpha)))
        return (
            previous[0] + (actor.x - previous[0]) * alpha,
            previous[1] + (actor.y - previous[1]) * alpha,
        )
