"""Help / Codex modal — two-level mechanics guide.

Index view lists all topics; clicking one opens its detailed page with a
Back button. Content lives in HELP_SECTIONS below for easy editing.
"""

import pygame

from game.data.config import (
    COLOR_MODAL_BG, COLOR_MODAL_BORDER, COLOR_TEXT_TITLE, COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
)

# ---------------------------------------------------------------------------
# Codex content. Each section: (title, [paragraph strings]).
# ---------------------------------------------------------------------------
HELP_SECTIONS = [
    ("HOW TO START", [
        "You are the Lord of a small village. Your goals: grow the population,",
        "produce food and goods, collect taxes, and keep your people happy.",
        "",
        "1. Claim land with PERMITS (build menu -> Permit). Permits define",
        "   where houses, farms, and storage may be placed.",
        "2. Your household already has a house, farm plot, market stall,",
        "   storage yard, and a Treasury Chest with starting coins.",
        "3. Assign jobs to your villagers (click a villager -> Job).",
        "4. Place workplaces: Builder Workbench, Woodsman Lodge, Miner",
        "   Workstation, Toolmaker Workbench — each needs a worker of",
        "   the matching job to function.",
        "5. Open the MARKET stall and list items for sale. Villagers will",
        "   haul goods to it and customers will buy them.",
        "6. Survive the first days: keep food in storage, keep villagers",
        "   fed and watered, and expand slowly.",
    ]),
    ("CONTROLS", [
        "WASD / Arrow keys — pan camera (hold Shift for faster pan).",
        "Mouse wheel — zoom in / out.",
        "Left click — select villager, building, furniture, or stack.",
        "Right click — context actions (Move, Destroy, Household, etc).",
        "M — toggle the world map overlay.",
        "ESC — open this menu (Resume, Save, Load, Help, Main Menu).",
        "R — rotate building/furniture placement.",
        "Enter — confirm placement / dialog.",
        "Speed buttons (bottom-right) — pause, 1x, 2x, 3x game speed.",
    ]),
    ("PERMITS & LAND", [
        "Permits are legal claims on tiles. Nothing can be built or farmed",
        "outside a permit.",
        "- FARM permit: crop tiles. Assign workers to it.",
        "- HOUSE permit: where household homes may be placed.",
        "- STORAGE permit: where household storage chests may stand.",
        "- LANDLORD_STORAGE preset: the lord's private storage yard —",
        "  ONLY servants may take items from or store items into it.",
        "Drag to paint permit tiles, Enter to confirm, ESC to cancel.",
    ]),
    ("VILLAGERS & FAMILIES", [
        "Villagers live in families (households). Each family has its own",
        "home, storage chest, and shared possessions.",
        "Needs decay over time: HUNGER, THIRST, and TOILET. Villagers seek",
        "food, water, and toilets on their own — keep supplies stocked or",
        "they will get sick and unhappy.",
        "Families span up to 3 generations (grandparents, parents,",
        "adult offspring). Generation is descriptive only — every member",
        "can hold any job regardless of age.",
        "Click a villager to open their panel: job assignment, schedule,",
        "inventory, and family info.",
        "Click a family name (Raport > Families) to manage the household,",
        "view possessions, or assign its market stall.",
    ]),
    ("JOBS", [
        "Every villager has ONE job. Jobs determine their daily routine and",
        "what they do during WORK hours.",
        "- Farmer: works crops on the family farm permit.",
        "- Builder: builds furniture and public structures for commissions.",
        "- Toolmaker: smelts iron and forges tools at the Toolmaker",
        "  Workbench.",
        "- Woodsman: chops trees at the Woodsman Lodge (needs Felling Axe",
        "  and Spade).",
        "- Miner: extracts ore at a Miner Workstation placed on a mine",
        "  deposit (needs Pickaxe and Sledgehammer).",
        "- Gravedigger: buries the dead at the cemetery.",
        "- Tax Collector: gathers socage taxes on collection days.",
        "Some jobs REQUIRE specific tools. If a villager lacks their tools,",
        "they show MISSING TOOL and cannot work — buy tools at the market",
        "or have a Toolmaker forge them.",
    ]),
    ("DAILY SCHEDULE", [
        "Villagers follow a 24-hour schedule you can edit per villager:",
        "WORK, LEISURE, SLEEP, PRAYER, and ANY (do whatever is needed).",
        "They sleep in their family beds at night, eat when hungry, and",
        "work only during WORK/ANY slots.",
        "If a WORK slot has genuinely no work available (no crops, no",
        "orders, no stock targets), the villager uses the time for needs",
        "and chores instead of standing idle.",
    ]),
    ("FARMING", [
        "1. Place crops on farm-permit tiles (select the farm, choose crop).",
        "2. Farmers TILL the soil, PLANT seeds, WATER daily, and HARVEST",
        "   when ripe.",
        "3. Unwatered crops wilt; untilled tiles produce nothing.",
        "4. Harvested food goes to the family storage automatically.",
        "Keep a food surplus — hungry villagers lose happiness and may",
        "refuse to work.",
    ]),
    ("FORESTRY & MINING", [
        "Woodsman Lodge (4x4 camp): costs 20 Wood + 10 Stone, built via a",
        "Builder commission (1 hour). Place it on open ground. A Woodsman",
        "assigned to it fells nearby mature trees and can replant them",
        "(Plant a Tree toggle).",
        "Miner Workstation (5x5): costs 20 Stone + 10 Wood, 1 hour build.",
        "Must be placed EXACTLY on a mine deposit. Output depends on the",
        "mine type: Stone Mine -> Stone, Iron Mine -> Iron Ore, etc.",
        "Both stations keep their own stock; set quotas in the Raport.",
        "Iron Mine is rare-ish — keep exploring the island for one.",
    ]),
    ("TOOLMAKER & IRON CHAIN", [
        "The full metal chain:",
        "  Iron Mine -> Iron Ore ->(smelt) Iron Bar ->(forge) Tools",
        "",
        "Smelting: 1 Iron Ore + 1 Wood = 1 Iron Bar. Takes 10 ingame",
        "minutes per bar, target stock 10 bars, max 10 bars per day.",
        "If the household chest lacks ore or wood, the Toolmaker buys",
        "supplies at the nearest market automatically.",
        "",
        "Forging: 2 Wood + 3 Iron Bar per tool, 1-2 ingame hours RNG",
        "per unit. Order any quantity from the Forge Catalogue (click",
        "the workbench). Finished tools are delivered to the payer's",
        "storage.",
        "",
        "Every tool unit has a CONDITION: PRISTINE > GOOD > WORN >",
        "DAMAGED > BROKEN. Every 2 days each unit rolls a 30% chance to",
        "drop one stage; BROKEN tools are destroyed. This applies to ALL",
        "tools everywhere — stock up or re-forge regularly.",
        "Condition does NOT reduce tool performance and there is no",
        "repair — worn tools work the same until they break. It exists",
        "purely to keep the iron supply chain alive.",
    ]),
    ("BUILDER COMMISSIONS", [
        "Builders take COMMISSIONS: furniture and public structures are",
        "built to order, not placed instantly.",
        "Flow: order -> payment -> materials -> build (1 hour for stations)",
        "-> complete.",
        "",
        "HOUSEHOLD orders: a family member pays the fee from the family",
        "chest (own-family orders are FREE labor — materials only).",
        "LANDLORD orders: you pay from the Treasury Chest; a servant",
        "physically carries the coins to the builder.",
        "",
        "If the artisan dies or loses the job, PAID commissions are",
        "refunded automatically via an errand. Materials already",
        "delivered are NOT refunded.",
        "Builder Workbench -> Catalogue lets you order furniture for",
        "your household. Notice Boards and Confession Boxes are",
        "public — only Builders may construct them.",
    ]),
    ("ECONOMY & MONEY", [
        "Currency is three-tiered: GOLD > SILVER > COPPER coins.",
        "Every wallet (villager, family chest, market, treasury) stores",
        "its own coins — money does NOT teleport between them.",
        "",
        "MARKETS are buildings with their own inventory, currency, and",
        "prices. Two types:",
        "- LANDLORD market: YOU set the prices manually. Use Restock to",
        "  pull items from storage into the stall, Withdraw to take",
        "  them back out as loose stacks (a servant hauls them home).",
        "- HOUSEHOLD market: a family runs the stall. Assign it in the",
        "  family panel; they sell a PERCENTAGE of their current stock",
        "  per item (e.g. 10% of 100 potatoes = up to 10 for sale).",
        "  The percentage follows their stock live — sell-outs",
        "  automatically replenish the next batch.",
        "",
        "PRICING: on household stalls, prices auto-adjust to the PHYSICAL",
        "stock inside the market — more stock = cheaper, less = dearer.",
        "Items sitting in a home chest or in transit do NOT affect the",
        "price; only goods actually on the stall do.",
        "",
        "Villagers and servants physically CARRY goods to and from",
        "markets — nothing teleports. If the stall is far or blocked,",
        "hauling takes real time.",
    ]),
    ("SERVANTS", [
        "Servants are your private staff. They live in the Treasury",
        "household area and obey only you.",
        "- HAUL loose item stacks into storage (auto-assigned).",
        "- BUY orders: send a servant to a market stall to purchase",
        "  goods with treasury coins.",
        "- COMMISSION COURIER: carry commission coins from the Treasury",
        "  Chest to builders/artisans.",
        "Servants may enter the LORD'S STORAGE — no villager or artisan",
        "may take items or coins from it directly.",
        "Servants can phase through walls and narrow gaps to reach",
        "targets, but still cannot walk on water or off the map.",
    ]),
    ("TAXATION", [
        "The Tax Collector gathers SOCAGE TAX from households on",
        "scheduled collection days. Keep the collector supplied and",
        "households will pay from their wealth.",
        "Taxes fund your treasury — the engine of your public works.",
        "Check the Raport > Economy tab for tax and market ledgers.",
    ]),
    ("RELIGION & DEATH", [
        "Churches and Confession Boxes serve the faithful. Villagers",
        "with religious needs seek them out; a Confession can lift",
        "mood or resolve guilt.",
        "When a villager dies, the family enters a recovery period —",
        "their storage and jobs are held until affairs are settled.",
        "The Gravedigger buries corpses at the cemetery; overflow",
        "corpses queue if no gravedigger is available.",
        "Happiness affects productivity: miserable villagers slack",
        "and may leave. Keep food, water, religion, and tools provided.",
    ]),
    ("IMMIGRATION", [
        "New families arrive at the NOTICE BOARD looking for land.",
        "They wait, travel to your village, and settle if you have",
        "space and prosperity.",
        "Keep a Notice Board standing to keep the immigration flow",
        "going — more families = more workers = more taxes.",
        "Track arrivals in Raport > Immigrant tab.",
    ]),
    ("MARKET MODAL & SELLING", [
        "Click a market stall to open its profile:",
        "- SELL tab: pick items with the multi-select picker (icons,",
        "  checkboxes, scroll). Ownership is validated — you can only",
        "  list what the stall actually holds.",
        "- Household stalls show a per-item SALE % field (0-100).",
        "- BUY orders send servants/villagers to purchase goods.",
        "Prices on household stalls update as stock changes; landlord",
        "stall prices are yours to set.",
    ]),
    ("CONSTRUCTION & DEMOLITION", [
        "Most structures go through the commission pipeline: blueprint",
        "-> payment -> material delivery -> build time -> complete.",
        "Nothing is instant except a few small items.",
        "Right-click any furniture/building for MOVE or DESTROY.",
        "Destroying dumps contents onto the ground and refunds part of",
        "the materials. Furniture can BREAK over time — repair or",
        "replace it.",
        "Workstations (lodge, mine, toolbench) can be damaged and",
        "need maintenance via their orders.",
    ]),
    ("SAVING & LOADING", [
        "ESC -> Save Game / Load Game. Saves are unlimited named",
        "files in the saves/ folder — name them anything.",
        "Autosave runs every 5 real-time minutes as autosave-dayNN,",
        "keeping only the 3 newest files.",
        "Delete any save from the Load screen (with confirmation).",
        "Old saves auto-migrate: Carpenter was renamed Builder and all",
        "saved references upgrade on load.",
    ]),
    ("CHEATS & DEBUG", [
        "ESC -> Active Cheat -> password unlocks session cheats:",
        "Add Item (inject any item), Add Family, and debug tools.",
        "M opens the world map overlay. Path debug overlay exists for",
        "development (villager path visualization).",
    ]),
    ("TIPS FOR SURVIVAL", [
        "- First priority: FOOD. A starving village dies.",
        "- Second: TOOLS. Farmers need hoes, miners need pickaxes —",
        "  and tools BREAK over time.",
        "- Third: MORE FAMILIES. One family cannot fill every job.",
        "- Keep the Treasury funded — public commissions and servant",
        "  errands all draw from it.",
        "- Household stalls are free money once stocked: assign a",
        "  stall, set sale %, and let villagers haul surplus goods.",
        "- If a servant seems stuck, check if it is inside a solid",
        "  building — it will path out on its own.",
    ]),
]


class HelpModal:
    """Two-level codex: index list -> per-topic detail page."""

    def __init__(self):
        self.is_open = False
        self.view = "index"          # "index" | "detail"
        self.detail_index = 0
        self.scroll_y = 0.0
        self.max_scroll = 0.0
        self.modal_rect = None
        self.viewport_rect = None
        self.close_rect = None
        self.back_rect = None
        self.topic_rects = []         # (rect, section_index) rebuilt each draw
        self._fonts_ready = False
        self.font_title = None
        self.font_head = None
        self.font_body = None
        self.font_small = None

    def _ensure_fonts(self):
        if self._fonts_ready:
            return
        self.font_title = pygame.font.SysFont("Segoe UI", 20, bold=True)
        self.font_head = pygame.font.SysFont("Segoe UI", 15, bold=True)
        self.font_body = pygame.font.SysFont("Segoe UI", 13)
        self.font_small = pygame.font.SysFont("Segoe UI", 11)
        self._fonts_ready = True

    def open(self):
        self.is_open = True
        self.view = "index"
        self.detail_index = 0
        self.scroll_y = 0.0
        self._kb_cursor = 0

    def close(self):
        self.is_open = False
        self.view = "index"
        self.scroll_y = 0.0
        self._kb_cursor = 0

    def _clamp_scroll(self):
        self.scroll_y = max(0.0, min(self.scroll_y, self.max_scroll))

    def handle_event(self, event):
        if not self.is_open:
            return None
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.view == "detail":
                    self.view = "index"
                    self.scroll_y = 0.0
                else:
                    self.close()
                return "close"
            if self.view == "index" and event.key in (pygame.K_UP, pygame.K_DOWN):
                # Keyboard cursor through the topic list.
                direction = 1 if event.key == pygame.K_DOWN else -1
                self._kb_cursor = getattr(self, "_kb_cursor", 0) + direction
                self._kb_cursor = max(0, min(self._kb_cursor, len(HELP_SECTIONS) - 1))
                # Keep cursor row visible.
                row_h = 44
                row_top = self._kb_cursor * row_h
                if row_top < self.scroll_y:
                    self.scroll_y = row_top
                elif row_top + row_h > self.scroll_y + self.viewport_rect.height:
                    self.scroll_y = row_top + row_h - self.viewport_rect.height
                self._clamp_scroll()
                return "scroll"
            if self.view == "index" and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                idx = getattr(self, "_kb_cursor", 0)
                self.view = "detail"
                self.detail_index = idx
                self.scroll_y = 0.0
                return "open_topic"
            step = 48 if event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN) else 24
            direction = -1 if event.key in (pygame.K_UP, pygame.K_PAGEUP) else 1
            self.scroll_y += direction * step
            self._clamp_scroll()
            return "scroll"
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.close_rect and self.close_rect.collidepoint(event.pos):
                self.close()
                return "close"
            if self.view == "detail" and self.back_rect and self.back_rect.collidepoint(event.pos):
                self.view = "index"
                self.scroll_y = 0.0
                return "back"
            if self.view == "index":
                for rect, idx in self.topic_rects:
                    if rect.collidepoint(event.pos):
                        self.view = "detail"
                        self.detail_index = idx
                        self.scroll_y = 0.0
                        return "open_topic"
                if self.viewport_rect and self.viewport_rect.collidepoint(event.pos):
                    return "scroll_area"
                return "blocked"
            if self.viewport_rect and self.viewport_rect.collidepoint(event.pos):
                return "scroll_area"
            return "blocked"
        if event.type == pygame.MOUSEWHEEL:
            if self.viewport_rect and self.viewport_rect.collidepoint(pygame.mouse.get_pos()):
                self.scroll_y -= event.y * 36
                self._clamp_scroll()
                return "scroll"
        return None

    # ------------------------------------------------------------------
    def draw(self, surface):
        if not self.is_open:
            return
        self._ensure_fonts()
        screen_w, screen_h = surface.get_size()
        modal_w = min(720, screen_w - 40)
        modal_h = min(600, screen_h - 40)
        mx = (screen_w - modal_w) // 2
        my = (screen_h - modal_h) // 2
        self.modal_rect = pygame.Rect(mx, my, modal_w, modal_h)

        shade = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 180))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, COLOR_MODAL_BG, self.modal_rect, border_radius=12)
        pygame.draw.rect(surface, COLOR_MODAL_BORDER, self.modal_rect, width=2, border_radius=12)

        title_txt = ("VILLAGE CODEX" if self.view == "index"
                     else HELP_SECTIONS[self.detail_index][0])
        title = self.font_title.render(title_txt, True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + 24, my + 16))
        sub_txt = ("Select a topic to read the details" if self.view == "index"
                   else "Mechanics guide")
        sub = self.font_small.render(sub_txt, True, COLOR_TEXT_MUTED)
        surface.blit(sub, (mx + 26, my + 46))

        self.close_rect = pygame.Rect(mx + modal_w - 40, my + 14, 26, 26)
        pygame.draw.rect(surface, (30, 41, 59), self.close_rect, border_radius=5)
        x_txt = self.font_head.render("X", True, COLOR_TEXT_MAIN)
        surface.blit(x_txt, (self.close_rect.centerx - x_txt.get_width() // 2,
                             self.close_rect.centery - x_txt.get_height() // 2))

        pad = 20
        self.viewport_rect = pygame.Rect(mx + pad, my + 70, modal_w - pad * 2,
                                         modal_h - 70 - 14)
        old_clip = surface.get_clip()
        surface.set_clip(self.viewport_rect)

        if self.view == "index":
            self._draw_index(surface)
        else:
            self._draw_detail(surface)

        surface.set_clip(old_clip)

        # Back button pinned in the header (detail view only).
        self.back_rect = None
        if self.view == "detail":
            self.back_rect = pygame.Rect(mx + modal_w - 130, my + 12, 84, 30)
            b_hover = self.back_rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (55, 65, 81) if b_hover else (30, 41, 59),
                             self.back_rect, border_radius=6)
            pygame.draw.rect(surface, (71, 85, 105), self.back_rect, width=1, border_radius=6)
            b_txt = self.font_small.render("< Topics", True, COLOR_TEXT_MAIN)
            surface.blit(b_txt, (self.back_rect.centerx - b_txt.get_width() // 2,
                                 self.back_rect.centery - b_txt.get_height() // 2))

        self._draw_scrollbar(surface)

        hint = self.font_small.render(
            "ESC to go back/close — mouse wheel or arrows to scroll",
            True, COLOR_TEXT_MUTED)
        surface.blit(hint, (mx + 24, my + modal_h - 26))

    # ------------------------------------------------------------------
    def _draw_index(self, surface):
        self.topic_rects = []
        row_h = 44
        mouse_pos = pygame.mouse.get_pos()
        for i, (sec_title, _paras) in enumerate(HELP_SECTIONS):
            row_y = self.viewport_rect.y + i * row_h - self.scroll_y
            if row_y + row_h < self.viewport_rect.y or row_y > self.viewport_rect.bottom:
                continue
            row = pygame.Rect(self.viewport_rect.x, row_y,
                              self.viewport_rect.width, row_h - 6)
            self.topic_rects.append((row, i))
            kb_sel = (self.view == "index" and i == getattr(self, "_kb_cursor", 0))
            hover = row.collidepoint(mouse_pos) or kb_sel
            pygame.draw.rect(surface, (30, 58, 95) if hover else (15, 23, 42),
                             row, border_radius=8)
            pygame.draw.rect(surface, (71, 85, 105) if not hover else (125, 211, 252),
                             row, width=2 if kb_sel else 1, border_radius=8)
            txt = self.font_head.render(sec_title, True,
                                        COLOR_TEXT_TITLE if hover else COLOR_TEXT_MAIN)
            surface.blit(txt, (row.x + 16, row.centery - txt.get_height() // 2))
            arrow = self.font_body.render(">", True, COLOR_TEXT_MUTED if not hover else (125, 211, 252))
            surface.blit(arrow, (row.right - 26, row.centery - arrow.get_height() // 2))
        self.max_scroll = max(0.0, len(HELP_SECTIONS) * row_h - self.viewport_rect.height)
        self._clamp_scroll()

    def _draw_detail(self, surface):
        _title, paras = HELP_SECTIONS[self.detail_index]
        line_h = 18
        content_h = len(paras) * line_h + 10
        cy = self.viewport_rect.y + 8 - self.scroll_y
        for para in paras:
            if para == "":
                cy += line_h // 2
                continue
            txt = self.font_body.render(para, True, COLOR_TEXT_MAIN)
            surface.blit(txt, (self.viewport_rect.x + 8, cy))
            cy += line_h
        self.max_scroll = max(0.0, content_h - self.viewport_rect.height)
        self._clamp_scroll()

    def _draw_scrollbar(self, surface):
        if self.max_scroll <= 0 or not self.viewport_rect:
            return
        track = pygame.Rect(self.viewport_rect.right + 4, self.viewport_rect.y, 6,
                            self.viewport_rect.height)
        pygame.draw.rect(surface, (30, 41, 59), track, border_radius=3)
        if self.view == "index":
            content_h = len(HELP_SECTIONS) * 44
        else:
            content_h = len(HELP_SECTIONS[self.detail_index][1]) * 18 + 10
        ratio = min(1.0, self.viewport_rect.height / max(1.0, content_h))
        thumb_h = max(24, int(self.viewport_rect.height * ratio))
        thumb_y = self.viewport_rect.y + int(
            (self.viewport_rect.height - thumb_h) * (self.scroll_y / self.max_scroll))
        pygame.draw.rect(surface, (100, 116, 139),
                         (track.x, thumb_y, 6, thumb_h), border_radius=3)
