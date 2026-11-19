"""
Day & Night Cycle System (Configurable In-Game Day Length & Ambient Lighting)
"""

import math
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
)

class DayCycleSystem:
    def __init__(self):
        self.options = DAY_LENGTH_OPTIONS
        self.day_length_index = DEFAULT_DAY_LENGTH_INDEX
        self.day_length_seconds = self.options[self.day_length_index]["seconds"]

        self.day_number = 1
        # Mulai permainan pada jam awal konfigurasi
        self.time_seconds = (STARTING_HOUR / 24.0) * self.day_length_seconds

        self.font_clock = None
        self.font_sub = None

    def _init_fonts(self):
        if self.font_clock is None:
            self.font_clock = pygame.font.SysFont("Segoe UI", 13, bold=True)
            self.font_sub = pygame.font.SysFont("Segoe UI", 11, bold=True)

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
        return self.get_time_ratio() * 24.0

    def get_clock_time(self):
        """Mengembalikan tuple (hour, minute, formatted_str, is_night)"""
        ratio = self.get_time_ratio()
        total_hours = ratio * 24.0
        hour = int(total_hours) % 24
        minute = int((total_hours * 60) % 60)
        is_night = (hour < NIGHT_END_HOUR or hour >= NIGHT_START_HOUR)
        time_str = f"{hour:02d}:{minute:02d}"
        return hour, minute, time_str, is_night

    def get_weekday_name(self):
        """Return the informational weekday label for the current in-game day."""
        return WEEKDAY_NAMES[(max(1, self.day_number) - 1) % len(WEEKDAY_NAMES)]

    def get_ambient_overlay(self, screen_w, screen_h):
        """Menghitung overlay pencahayaan siang/malam yang halus (natural lighting)"""
        hour, minute, _, _ = self.get_clock_time()
        time_float = hour + (minute / 60.0)

        # 06:00 - 18:00 : Siang cerah (Clear daylight, alpha = 0)
        # 18:00 - 20:00 : Senja / Sunset (Transisi orange ke dusk)
        # 20:00 - 04:30 : Malam (Deep blue moonlight, alpha ~110 agar tetap terlihat jelas)
        # 04:30 - 06:00 : Fajar / Sunrise (Transisi pagi)
        overlay_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)

        if 6.0 <= time_float < 18.0:
            # Siang terang
            return None
        elif 18.0 <= time_float < 20.0:
            # Senja (Sunset)
            prog = (time_float - 18.0) / 2.0  # 0.0 -> 1.0
            r = int(245 - 200 * prog)
            g = int(140 - 100 * prog)
            b = int(60 + 50 * prog)
            alpha = int(30 + 70 * prog)
            overlay_surf.fill((r, g, b, alpha))
            return overlay_surf
        elif time_float >= 20.0 or time_float < 4.5:
            # Malam hari (Moonlight)
            overlay_surf.fill((15, 23, 42, 110))
            return overlay_surf
        elif 4.5 <= time_float < 6.0:
            # Fajar (Sunrise)
            prog = (time_float - 4.5) / 1.5  # 0.0 -> 1.0
            alpha = int(110 * (1.0 - prog))
            overlay_surf.fill((251, 191, 36, alpha))
            return overlay_surf

        return None

    def draw_hud(self, surface, villager_manager=None):
        """Render floating Clock & Calendar HUD di bagian atas layar"""
        self._init_fonts()
        screen_w, _ = surface.get_size()

        hour, minute, time_str, is_night = self.get_clock_time()

        villagers = villager_manager.get_all_villagers() if villager_manager else []
        living = [villager for villager in villagers if getattr(villager, "is_alive", True)]
        known_jobs = set(DEDICATED_JOBS)
        assigned_count = sum(
            1 for villager in living
            if getattr(villager, "job", None) in known_jobs and getattr(villager, "job", None) != "Unassigned"
        )
        unassigned_count = len(living) - assigned_count
        day_surface = self.font_clock.render(f"Day {self.day_number}", True, (241, 245, 249))
        unassigned_surface = self.font_sub.render(f"Unassigned {unassigned_count}", True, (203, 213, 225))
        assigned_surface = self.font_sub.render(f"Assigned {assigned_count}", True, (134, 239, 172))
        clock_surface = self.font_clock.render(time_str, True, (56, 189, 248))
        chip_padding = self.font_sub.size("  ")[0]
        chip_gap = max(2, self.font_sub.get_height() // 3)
        chip_h = max(self.font_sub.get_height(), self.font_clock.get_height()) + chip_padding
        day_chip_w = day_surface.get_width() + chip_padding
        unassigned_chip_w = unassigned_surface.get_width() + chip_padding
        assigned_chip_w = assigned_surface.get_width() + chip_padding
        pill_w = max(
            175,
            34 + day_chip_w + chip_gap + unassigned_chip_w + chip_gap
            + assigned_chip_w + chip_gap + clock_surface.get_width() + 12,
        )
        pill_h = 36
        pill_x = 16
        pill_y = 16

        bg_surf = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pygame.draw.rect(bg_surf, COLOR_HUD_BG, (0, 0, pill_w, pill_h), border_radius=8)
        pygame.draw.rect(bg_surf, COLOR_HUD_BORDER, (0, 0, pill_w, pill_h), width=1, border_radius=8)
        surface.blit(bg_surf, (pill_x, pill_y))

        # Procedural Sun / Moon Vector Icon (Zero missing glyphs)
        icon_cx = pill_x + 20
        icon_cy = pill_y + pill_h // 2
        if is_night:
            pygame.draw.circle(surface, (226, 232, 240), (icon_cx, icon_cy), 7)
            pygame.draw.circle(surface, COLOR_HUD_BG, (icon_cx + 3, icon_cy - 2), 6)
        else:
            pygame.draw.circle(surface, (245, 158, 11), (icon_cx, icon_cy), 7)
            pygame.draw.circle(surface, (254, 240, 138), (icon_cx, icon_cy), 5)

        # Distinct, adjacent status chips inside one shared HUD card.
        chip_x = pill_x + 34
        chip_y = pill_y + (pill_h - chip_h) // 2
        for text_surface, chip_w in (
            (day_surface, day_chip_w),
            (unassigned_surface, unassigned_chip_w),
            (assigned_surface, assigned_chip_w),
        ):
            chip_rect = pygame.Rect(chip_x, chip_y, chip_w, chip_h)
            pygame.draw.rect(surface, (30, 41, 59), chip_rect, border_radius=5)
            surface.blit(
                text_surface,
                (chip_rect.centerx - text_surface.get_width() // 2,
                 chip_rect.centery - text_surface.get_height() // 2),
            )
            chip_x = chip_rect.right + chip_gap
        surface.blit(clock_surface, (pill_x + pill_w - clock_surface.get_width() - 12, pill_y + 8))
