"""Shared typable-number field state for UI modals.

Replaces click-per-step "(-) value (+)" steppers: the user clicks a value
box, types digits directly, and commits with Enter or by clicking away.

*** ESTABLISHED — DO NOT REGRESS ***
All numeric UI inputs (permits, prayer hours, workplace quotas, church tax,
socage tax, market prices/stock, grant quantities) route through this
component — the user explicitly demanded direct typing everywhere. Do not
reintroduce -/+ steppers for numeric values.
"""

import pygame


class NumberInputState:
    """Tracks the single active numeric text field of a modal."""

    def __init__(self, max_digits=6):
        self.active_key = None
        self.text = ""
        self.replace = False
        self.max_digits = max_digits

    @property
    def active(self):
        return self.active_key is not None

    def focus(self, key, current):
        self.active_key = key
        self.text = str(int(current))
        self.replace = True

    def cancel(self):
        self.active_key = None
        self.text = ""
        self.replace = False

    def value(self):
        text = self.text.strip()
        return int(text) if text.isdigit() else None

    def handle_keydown(self, event):
        """Route a KEYDOWN event while a field is active.

        Returns "edit" | "commit" | "cancel". Unrecognized keys are
        swallowed so game hotkeys don't fire while typing.
        """
        if self.active_key is None:
            return None
        if event.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
            self.replace = False
            return "edit"
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return "commit"
        if event.key == pygame.K_ESCAPE:
            return "cancel"
        if event.unicode.isdigit():
            if self.replace:
                self.text = event.unicode
                self.replace = False
            elif len(self.text) < self.max_digits:
                self.text += event.unicode
        return "edit"
