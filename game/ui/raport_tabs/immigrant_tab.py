"""RaportUI tab view — extracted from ui_raport.py (mixin)."""

import pygame
from game.config import COLOR_TEXT_MUTED, COLOR_TEXT_TITLE


class ImmigrantMixin:
    def _draw_immigrant_tab(self, surface, mx, cy, villager_manager, permit_manager, furniture_manager=None, day_cycle=None):
        """Immigration — Notice Board posting & waiting household queue.

        The landlord posts a notice (reward gold per household), immigrant
        households physically arrive at the board and queue, and the landlord
        accepts (they join the census, reward paid via Lord Treasury grant) or
        rejects (they leave). Households unattended for a full day leave alone.
        """
        from game.systems.village_life.immigration_system import (
            get_immigration_system, STATE_TRAVELING, STATE_WAITING,
        )
        imm = get_immigration_system()
        mouse_pos = pygame.mouse.get_pos()
        self.immigrant_post_btn_rect = None
        self.immigrant_cancel_btn_rect = None
        self.immigrant_action_btns = {}

        title = self.font_title.render("IMMIGRATION — NOTICE BOARD", True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + 24, cy - 4))

        boards = imm.notice_boards(furniture_manager)
        if not boards:
            msg = self.font_body.render(
                "No Notice Board placed. Build one via Buildings > Public Structure "
                "(Wood x10, ~1h builder build, max 1 per village).", True, COLOR_TEXT_MUTED)
            surface.blit(msg, (mx + 24, cy + 34))
            return

        board = boards[0]
        board_name = getattr(board, "name", None) or getattr(board, "type_cfg", {}).get("name", "Notice Board")
        posted = imm.is_posted(board.id)
        reward = imm.reward_for(board.id)
        queued = [h for h in imm.pending
                  if h["board_id"] == board.id and h["state"] in (STATE_TRAVELING, STATE_WAITING)]

        y_cur = cy + 30
        # --- Posting status card ---
        card = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 66)
        pygame.draw.rect(surface, (24, 34, 52), card, border_radius=7)
        pygame.draw.rect(surface, (51, 65, 85), card, width=1, border_radius=7)

        status_col = (34, 197, 94) if posted else (245, 158, 11)
        status_txt = "POSTED — immigrants may arrive each day (30% chance)" if posted \
            else "NOT POSTED — no immigrants will come"
        surface.blit(self.font_sub.render(f"{board_name}: {status_txt}", True, status_col),
                     (card.x + 14, card.y + 10))
        surface.blit(self.font_body.render(
            "Reward per household (gold, paid on Accept):", True, COLOR_TEXT_MUTED),
            (card.x + 14, card.y + 30))

        rew_key = ("num", "immigrant_reward", board.id)
        rew_rect = pygame.Rect(card.x + 252, card.y + 26, 52, 26)
        self.num_fields[rew_key] = {"rect": rew_rect, "kind": "immigrant_reward",
                                    "payload": board.id, "min": 0, "max": 999}
        self._draw_num_input(surface, rew_key, rew_rect, reward)

        # Post / Cancel button
        btn_w, btn_h = 110, 26
        if posted:
            btn_rect = pygame.Rect(card.right - btn_w - 14, card.y + 20, btn_w, btn_h)
            self.immigrant_cancel_btn_rect = btn_rect
            hov = btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (127, 29, 29) if hov else (153, 27, 27), btn_rect, border_radius=6)
            bt = self.font_badge.render("Cancel Post", True, (255, 255, 255))
        else:
            btn_rect = pygame.Rect(card.right - btn_w - 14, card.y + 20, btn_w, btn_h)
            self.immigrant_post_btn_rect = btn_rect
            hov = btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (22, 101, 52) if hov else (20, 83, 45), btn_rect, border_radius=6)
            bt = self.font_badge.render("Post Notice", True, (255, 255, 255))
        pygame.draw.rect(surface, (100, 116, 139), btn_rect, width=1, border_radius=6)
        surface.blit(bt, (btn_rect.centerx - bt.get_width() // 2, btn_rect.centery - bt.get_height() // 2))
        y_cur += card.height + 16

        # --- Waiting queue ---
        surface.blit(self.font_sub.render(
            f"Waiting Immigrant Households ({len(queued)}):", True, (241, 245, 249)),
            (mx + 24, y_cur))
        y_cur += 22

        if not queued:
            empty_r = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 44)
            pygame.draw.rect(surface, (24, 34, 52), empty_r, border_radius=6)
            hint = "Post a notice — households that arrive will queue here for your review."
            surface.blit(self.font_body.render(hint, True, COLOR_TEXT_MUTED),
                         (empty_r.x + 16, empty_r.y + 14))
            y_cur += 54
        else:
            day_num = getattr(day_cycle, "day_number", 1) if day_cycle else 1
            for hh in queued:
                fam = hh["family"]
                hh_card = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 52)
                pygame.draw.rect(surface, (24, 34, 52), hh_card, border_radius=7)
                pygame.draw.rect(surface, (51, 65, 85), hh_card, width=1, border_radius=7)

                state_txt = "Arrived" if hh["state"] == STATE_WAITING else "On the way"
                arrived_day = int(hh.get("arrival_day") or day_num)
                members = [m for m in fam.members if getattr(m, "is_alive", True)]
                size_txt = f"{len(members)} member(s)"
                surface.blit(self.font_sub.render(
                    f"The {fam.surname} Family — {size_txt} — {state_txt} (Day {arrived_day})",
                    True, (241, 245, 249)), (hh_card.x + 14, hh_card.y + 8))
                surface.blit(self.font_body.render(
                    f"Reward on accept: {hh.get('reward_gold', reward)} gold  ·  "
                    "Homeless until a household deed is issued.",
                    True, COLOR_TEXT_MUTED), (hh_card.x + 14, hh_card.y + 27))

                a_rect = pygame.Rect(hh_card.right - 190, hh_card.y + 12, 80, 26)
                r_rect = pygame.Rect(hh_card.right - 100, hh_card.y + 12, 80, 26)
                self.immigrant_action_btns[hh["id"]] = (a_rect, r_rect)
                for rect, label, bg, border in (
                    (a_rect, "Accept", (22, 101, 52), (74, 222, 128)),
                    (r_rect, "Reject", (127, 29, 29), (248, 113, 113)),
                ):
                    hov = rect.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, tuple(min(255, c + 20) for c in bg) if hov else bg,
                                     rect, border_radius=6)
                    pygame.draw.rect(surface, border, rect, width=1, border_radius=6)
                    bt = self.font_badge.render(label, True, (255, 255, 255))
                    surface.blit(bt, (rect.centerx - bt.get_width() // 2,
                                      rect.centery - bt.get_height() // 2))
                y_cur += hh_card.height + 8

