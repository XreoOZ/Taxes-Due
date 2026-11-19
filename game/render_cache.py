"""Small cached alpha surfaces shared by the software-rendered world sprites."""

from functools import lru_cache

import pygame


@lru_cache(maxsize=512)
def alpha_fill_surface(width, height, color):
    surface = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
    surface.fill(color)
    return surface


@lru_cache(maxsize=256)
def ellipse_surface(width, height, color):
    width, height = max(1, width), max(1, height)
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.ellipse(surface, color, (0, 0, width, height))
    return surface


@lru_cache(maxsize=128)
def inset_rect_surface(width, height, color, inset, border_radius):
    width, height = max(1, width), max(1, height)
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    rect = pygame.Rect(inset, inset, max(1, width - inset), max(1, height - inset))
    pygame.draw.rect(surface, color, rect, border_radius=border_radius)
    return surface
