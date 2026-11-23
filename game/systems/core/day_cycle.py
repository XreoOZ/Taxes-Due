"""
Day & Night Cycle System (Configurable In-Game Day Length & Ambient Lighting)
"""
from game.ui.ui_theme import ui_font, upx

import math
import time
import pygame
from game.data.config import DEDICATED_JOBS
from game.config import (
    DAY_LENGTH_OPTIONS,
    DEFAULT_DAY_LENGTH_INDEX,
    COLOR_HUD_BG,
    COLOR_HUD_BORDER,
    STARTING_HOUR,
    NIGHT_START_HOUR,
    NIGHT_END_HOUR,
    WEEKDAY_NAMES,
    VILLAGER_HUD_COUNT_REFRESH_SECONDS,
    HOURS_PER_DAY,
    MINUTES_PER_HOUR,
    DAY_CYCLE_LIGHTING,
)

class DayCycleSystem:
    def __init__(self):
        self.options = DAY_LENGTH_OPTIONS
        self.day_length_index = DEFAULT_DAY_LENGTH_INDEX
        self.day_length_seconds = self.options[self.day_length_index]["seconds"]

        self.day_number = 1
        # Mulai permainan pada jam awal konfigurasi
        self.time_seconds = (STARTING_HOUR / HOURS_PER_DAY) * self.day_length_seconds

        self.font_clock = None
        self.font_sub = None
        self._ambient_overlay_surface = None
        self._ambient_overlay_key = None
        self._population_cache_expiry = 0.0
        self._population_cache = (0, 0)
        self._hud_text_cache_key = None
        self._hud_text_cache = None
        self._hud_background_cache = {}

    def _ambient_surface(self, screen_w, screen_h, color):
        key = (screen_w, screen_h, color)
        if self._ambient_overlay_surface is None or self._ambient_overlay_surface.get_size() != (screen_w, screen_h):
            self._ambient_overlay_surface = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
            self._ambient_overlay_key = None
        if self._ambient_overlay_key != key:
            self._ambient_overlay_surface.fill(color)
            self._ambient_overlay_key = key
        return self._ambient_overlay_surface

    def _init_fonts(self):
        if self.font_clock is None:
            self.font_clock = ui_font(13, bold=True)
            self.font_sub = ui_font(11, bold=True)

    def set_day_length_index(self, index):
        """Mengubah durasi hari secara dinamis (10 menit, 20 menit, 30 menit)"""
        if 0 <= index < len(self.options):
            ratio = self.time_seconds / max(1.0, self.day_length_seconds)
            self.day_length_index = index
            self.day_length_seconds = self.options[index]["seconds"]
            self.time_seconds = ratio * self.day_length_seconds

    def update(self, dt):
        """Memajukan waktu berdasarkan delta time yang telah diskalakan dengan kecepatan game"""
        self.time_seconds += dt
        days_passed = 0
        if self.time_seconds >= self.day_length_seconds:
            days_passed = int(self.time_seconds // self.day_length_seconds)
            self.day_number += days_passed
            self.time_seconds = self.time_seconds % self.day_length_seconds
        return days_passed

    def get_time_ratio(self):
        """Mengembalikan progress waktu dalam 1 hari (0.0 s/d 1.0)"""
        return (self.time_seconds / max(1.0, self.day_length_seconds)) % 1.0

    @property
    def current_hour(self):
        """Current fractional hour of the day (0.0 to 24.0)"""
        return self.get_time_ratio() * HOURS_PER_DAY

    def get_clock_time(self):
        """Mengembalikan tuple (hour, minute, formatted_str, is_night)"""
        ratio = self.get_time_ratio()
        total_hours = ratio * HOURS_PER_DAY
        hour = int(total_hours) % int(HOURS_PER_DAY)
        minute = int((total_hours * MINUTES_PER_HOUR) % MINUTES_PER_HOUR)
        is_night = (hour < NIGHT_END_HOUR or hour >= NIGHT_START_HOUR)
        time_str = f"{hour:02d}:{minute:02d}"
        return hour, minute, time_str, is_night

    def get_weekday_name(self):
        """Return the informational weekday label for the current in-game day."""
        return WEEKDAY_NAMES[(max(1, self.day_number) - 1) % len(WEEKDAY_NAMES)]

    def get_ambient_overlay(self, screen_w, screen_h):
        """Menghitung overlay pencahayaan siang/malam yang halus (natural lighting)"""
        hour, minute, _, _ = self.get_clock_time()
        time_float = hour + (minute / MINUTES_PER_HOUR)
        lighting = DAY_CYCLE_LIGHTING
        daylight_start = lighting["daylight_start_hour"]
        sunset_start = lighting["sunset_start_hour"]
        night_start = NIGHT_START_HOUR
        sunrise_start = lighting["sunrise_start_hour"]

        # 06:00 - 18:00 : Siang cerah (Clear daylight, alpha = 0)
        # 18:00 - 20:00 : Senja / Sunset (Transisi orange ke dusk)
        # 20:00 - 04:30 : Malam (Deep blue moonlight, alpha ~110 agar tetap terlihat jelas)
        # 04:30 - 06:00 : Fajar / Sunrise (Transisi pagi)
        if daylight_start <= time_float < sunset_start:
            # Siang terang
            return None
        elif sunset_start <= time_float < night_start:
            # Senja (Sunset)
            prog = (time_float - sunset_start) / (night_start - sunset_start)
            start_color = lighting["sunset_start_color"]
            end_color = lighting["sunset_end_color"]
            r, g, b = (int(start + (end - start) * prog)
                       for start, end in zip(start_color, end_color))
            alpha_start, alpha_end = lighting["sunset_alpha"]
            alpha = int(alpha_start + (alpha_end - alpha_start) * prog)
            return self._ambient_surface(screen_w, screen_h, (r, g, b, alpha))
        elif time_float >= night_start or time_float < sunrise_start:
            # Malam hari (Moonlight)
            return self._ambient_surface(screen_w, screen_h, lighting["night_color"])
        elif sunrise_start <= time_float < daylight_start:
            # Fajar (Sunrise)
            prog = (time_float - sunrise_start) / (daylight_start - sunrise_start)
            alpha = int(lighting["sunrise_alpha"] * (1.0 - prog))
            return self._ambient_surface(
                screen_w, screen_h, (*lighting["sunrise_color"], alpha)
            )

        return None

    def draw_hud(self, surface, villager_manager=None):
        """Render floating Clock & Calendar HUD di bagian atas layar"""
        self._init_fonts()
        screen_w, _ = surface.get_size()

        hour, minute, time_str, is_night = self.get_clock_time()

        now = time.monotonic()
        if now >= self._population_cache_expiry:
            villagers = villager_manager.get_all_villagers() if villager_manager else []
            living = (villager for villager in villagers if getattr(villager, "is_alive", True))
            assigned_count = sum(
                1 for villager in living
                if getattr(villager, "job", None) in DEDICATED_JOBS
                and getattr(villager, "job", None) != "Unassigned"
            )
            living_count = sum(1 for villager in villagers if getattr(villager, "is_alive", True))
            self._population_cache = (living_count - assigned_count, assigned_count)
            self._population_cache_expiry = now + VILLAGER_HUD_COUNT_REFRESH_SECONDS
        unassigned_count, assigned_count = self._population_cache
        text_key = (self.day_number, time_str, unassigned_count, assigned_count)
        if self._hud_text_cache_key != text_key:
            self._hud_text_cache_key = text_key
            self._hud_text_cache = (
                self.font_clock.render(f"Day {self.day_number}  {time_str}", True, (241, 245, 249)),
                self.font_sub.render(f"Unassigned {unassigned_count}", True, (203, 213, 225)),
                self.font_sub.render(f"Assigned {assigned_count}", True, (134, 239, 172)),
            )
        day_surface, unassigned_surface, assigned_surface = self._hud_text_cache
        padding = self.font_sub.size("  ")[0]
        gap = max(3, self.font_sub.get_height() // 3)
        card_h = max(self.font_sub.get_height(), self.font_clock.get_height()) + padding
        card_y = 16
        day_w = day_surface.get_width() + padding * 2 + 26
        unassigned_w = unassigned_surface.get_width() + padding * 2
        assigned_w = assigned_surface.get_width() + padding * 2
        card_specs = (
            (day_w, day_surface, True),
            (unassigned_w, unassigned_surface, False),
            (assigned_w, assigned_surface, False),
        )
        total_w = sum(spec[0] for spec in card_specs) + gap * (len(card_specs) - 1)
        card_x = min(16, max(0, screen_w - total_w))

        # Procedural Sun / Moon Vector Icon (Zero missing glyphs)
        first_card_x = card_x
        icon_cx = first_card_x + padding
        icon_cy = card_y + card_h // 2
        if is_night:
            pygame.draw.circle(surface, (226, 232, 240), (icon_cx, icon_cy), 7)
            pygame.draw.circle(surface, COLOR_HUD_BG, (icon_cx + 3, icon_cy - 2), 6)
        else:
            pygame.draw.circle(surface, (245, 158, 11), (icon_cx, icon_cy), 7)
            pygame.draw.circle(surface, (254, 240, 138), (icon_cx, icon_cy), 5)

        for width, text_surface, has_icon in card_specs:
            card = pygame.Rect(card_x, card_y, width, card_h)
            pygame.draw.rect(surface, COLOR_HUD_BG, card, border_radius=8)
            pygame.draw.rect(surface, COLOR_HUD_BORDER, card, width=1, border_radius=8)
            text_x = card.centerx - text_surface.get_width() // 2
            if has_icon:
                text_x = card_x + padding * 2 + 14
            surface.blit(text_surface, (text_x, card.centery - text_surface.get_height() // 2))
            card_x = card.right + gap
