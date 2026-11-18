"""
Market Profile Modal (AGENT 2)
Displays landlord market management, unlimited storage, currency treasury (Copper, Silver, Gold),
market inventory, and interactive selling price editing.
"""

import math
import pygame
from game.data.config import (
    DEFAULT_ITEM_PRICES,
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    RESOURCE_COLORS,
    DENOMINATION_CAP
)
from game.systems.currency import to_copper, normalize_wallet

class MarketProfileModal:
    def __init__(self):
        self.is_open = False
        self.target_market = None
        self.font_title = None
        self.font_sub = None
        self.font_body = None
        self.font_badge = None
        self.font_btn = None

        # Modal bounds (dynamically positioned)
        self.modal_w = 700
        self.modal_h = 490

        # UI interaction rects
        self.close_btn_rect = None
        self.price_dec_btns = {}  # item_name -> pygame.Rect (-1)
        self.price_inc_btns = {}  # item_name -> pygame.Rect (+1)
        self.price_dec5_btns = {} # item_name -> pygame.Rect (-5)
        self.price_inc5_btns = {} # item_name -> pygame.Rect (+5)
        self.stock_dep_btns = {}  # item_name -> pygame.Rect (+10)
        self.stock_with_btns = {} # item_name -> pygame.Rect (-10)

    def _ensure_fonts(self):
        if self.font_title is None:
            self.font_title = pygame.font.SysFont("Segoe UI", 16, bold=True)
            self.font_sub = pygame.font.SysFont("Segoe UI", 12, bold=True)
            self.font_body = pygame.font.SysFont("Segoe UI", 11)
            self.font_badge = pygame.font.SysFont("Segoe UI", 10, bold=True)
            self.font_btn = pygame.font.SysFont("Segoe UI", 11, bold=True)

    def open(self, market_building):
        """Membuka modal profil pasar untuk gedung pasar yang dipilih"""
        if market_building and getattr(market_building, "building_type", "") == "market":
            self.target_market = market_building
            self.is_open = True
            # Pastikan struktur data default terpenuhi
            if not hasattr(market_building, "prices") or not market_building.prices:
                market_building.prices = dict(DEFAULT_ITEM_PRICES)
            if not hasattr(market_building, "inventory") or market_building.inventory is None:
                market_building.inventory = {"Potato": 100}
            if not hasattr(market_building, "currency") or not market_building.currency:
                market_building.currency = {"Copper": 0, "Silver": 0, "Gold": 0}

    def close(self):
        self.is_open = False
        self.target_market = None

    def handle_event(self, event, resources=None, stockpile_manager=None):
        """Menangani klik mouse dan keyboard pada Market Profile"""
        if not self.is_open or not self.target_market:
            return None

        mkt = self.target_market

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
                return "close"

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos

            # Tombol Tutup [X]
            if self.close_btn_rect and self.close_btn_rect.collidepoint(mouse_pos):
                self.close()
                return "close"

            # 1. Edit Harga: [-1] dan [+1]
            for it_name, rect in self.price_dec_btns.items():
                if rect.collidepoint(mouse_pos):
                    cur_p = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 1))
                    mkt.prices[it_name] = max(1, cur_p - 1)
                    return f"price_decreased_{it_name}"

            for it_name, rect in self.price_inc_btns.items():
                if rect.collidepoint(mouse_pos):
                    cur_p = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 1))
                    mkt.prices[it_name] = cur_p + 1
                    return f"price_increased_{it_name}"

            # 2. Edit Harga Cepat: [-5] dan [+5]
            for it_name, rect in self.price_dec5_btns.items():
                if rect.collidepoint(mouse_pos):
                    cur_p = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 1))
                    mkt.prices[it_name] = max(1, cur_p - 5)
                    return f"price_decreased5_{it_name}"

            for it_name, rect in self.price_inc5_btns.items():
                if rect.collidepoint(mouse_pos):
                    cur_p = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 1))
                    mkt.prices[it_name] = cur_p + 5
                    return f"price_increased5_{it_name}"

            # 3. Manajemen Stok: Deposit dari Landlord Storage ke Market
            for it_name, rect in self.stock_dep_btns.items():
                if rect.collidepoint(mouse_pos):
                    target_res = "Food" if it_name in ("Potato", "potato") else it_name
                    avail_stock = 0
                    if stockpile_manager:
                        for s in getattr(stockpile_manager, "stacks", []):
                            if s.owner_type == "landlord" and s.resource_type in (it_name, target_res):
                                avail_stock += s.amount
                    elif resources:
                        avail_stock = resources.get(target_res, resources.get(it_name, 0))

                    transfer_amt = min(10, avail_stock)
                    if transfer_amt > 0:
                        # Kurangi dari landlord stockpile
                        if stockpile_manager:
                            rem = transfer_amt
                            for s in list(getattr(stockpile_manager, "stacks", [])):
                                if s.owner_type == "landlord" and s.resource_type in (it_name, target_res):
                                    taken = stockpile_manager.take_from_stack(s, rem)
                                    rem -= taken
                                    if rem <= 0:
                                        break
                            stockpile_manager.refresh_stacks(resources, None)
                        elif resources:
                            k = target_res if target_res in resources else it_name
                            resources[k] = max(0, resources.get(k, 0) - transfer_amt)

                        mkt.inventory[it_name] = mkt.inventory.get(it_name, 0) + transfer_amt
                        return f"stock_deposited_{it_name}"

            # 4. Manajemen Stok: Withdraw dari Market ke Landlord Storage
            for it_name, rect in self.stock_with_btns.items():
                if rect.collidepoint(mouse_pos):
                    in_market = mkt.inventory.get(it_name, 0)
                    withdraw_amt = min(10, in_market)
                    if withdraw_amt > 0:
                        mkt.inventory[it_name] -= withdraw_amt
                        if mkt.inventory[it_name] <= 0:
                            del mkt.inventory[it_name]

                        target_res = "Food" if it_name in ("Potato", "potato") else it_name
                        if resources is not None:
                            k = target_res if target_res in resources else it_name
                            resources[k] = resources.get(k, 0) + withdraw_amt
                        if stockpile_manager:
                            # Drop di petak market pertama
                            if mkt.tiles:
                                t0 = next(iter(mkt.tiles))
                                stockpile_manager.drop_resource(target_res, withdraw_amt, t0[0], t0[1], owner_type="landlord")
                                stockpile_manager.refresh_stacks(resources, None)
                        return f"stock_withdrawn_{it_name}"

        return None

    def draw(self, surface, resources=None, stockpile_manager=None):
        if not self.is_open or not self.target_market:
            return

        self._ensure_fonts()
        mkt = self.target_market
        sw = surface.get_width()
        sh = surface.get_height()

        # 1. Dark Backdrop Overlay
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        # 2. Main Modal Box (Centered dynamically)
        mx = (sw - self.modal_w) // 2
        my = (sh - self.modal_h) // 2
        modal_rect = pygame.Rect(mx, my, self.modal_w, self.modal_h)

        pygame.draw.rect(surface, COLOR_MODAL_BG, modal_rect, border_radius=10)
        pygame.draw.rect(surface, (245, 158, 11), modal_rect, width=2, border_radius=10)

        # 3. Header: Title, Owner & Close Button
        header_y = my + 18
        title_txt = f"{getattr(mkt, 'name', 'Village Market')} — Market Profile"
        surface.blit(self.font_title.render(title_txt, True, (250, 204, 21)), (mx + 24, header_y))

        # Close [X] Button
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - 38, my + 14, 26, 26)
        c_hover = self.close_btn_rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, (220, 38, 38) if c_hover else (51, 65, 85), self.close_btn_rect, border_radius=5)
        x_lbl = self.font_sub.render("X", True, (255, 255, 255))
        surface.blit(x_lbl, (self.close_btn_rect.centerx - x_lbl.get_width() // 2, self.close_btn_rect.centery - x_lbl.get_height() // 2))

        # Ownership & Management Information
        owner_name = getattr(mkt, "owner", "landlord").capitalize()
        sub_info = f"Controlled by {owner_name}   |   Landlord manages stock & prices   |   Households purchase food"
        surface.blit(self.font_body.render(sub_info, True, COLOR_TEXT_MUTED), (mx + 24, header_y + 26))

        # -------------------------------------------------------------
        # 4. STATS BAR: UNLIMITED CAPACITY & CURRENCY TREASURY
        # -------------------------------------------------------------
        stats_y = header_y + 54
        stats_rect = pygame.Rect(mx + 24, stats_y, self.modal_w - 48, 56)
        pygame.draw.rect(surface, (24, 34, 52), stats_rect, border_radius=6)
        pygame.draw.rect(surface, (71, 85, 105), stats_rect, width=1, border_radius=6)

        # Capacity Badge (UNLIMITED)
        cap_badge_rect = pygame.Rect(stats_rect.x + 14, stats_rect.y + 12, 170, 32)
        pygame.draw.rect(surface, (16, 185, 129), cap_badge_rect, border_radius=5)
        cap_lbl = self.font_sub.render("Storage: ∞ UNLIMITED", True, (255, 255, 255))
        surface.blit(cap_lbl, (cap_badge_rect.centerx - cap_lbl.get_width() // 2, cap_badge_rect.centery - cap_lbl.get_height() // 2))

        # Market Currency Treasury (Gold, Silver, Copper)
        curr = normalize_wallet(getattr(mkt, "currency", {}))
        total_mkt_c = to_copper(curr)

        t_x = cap_badge_rect.right + 24
        t_y = stats_rect.y + 10
        surface.blit(self.font_badge.render("MARKET TREASURY:", True, COLOR_TEXT_MUTED), (t_x, t_y))

        bal_y = t_y + 14
        # Gold
        g_txt = f"{curr['Gold']} Gold"
        surface.blit(self.font_sub.render(g_txt, True, (250, 204, 21)), (t_x, bal_y))
        # Silver
        s_txt = f"{curr['Silver']} Silver"
        surface.blit(self.font_sub.render(s_txt, True, (203, 213, 225)), (t_x + 95, bal_y))
        # Copper
        c_txt = f"{curr['Copper']} Copper"
        surface.blit(self.font_sub.render(c_txt, True, (184, 115, 51)), (t_x + 195, bal_y))
        # Total
        tot_txt = f"(Total: {total_mkt_c}c)"
        surface.blit(self.font_body.render(tot_txt, True, COLOR_TEXT_MUTED), (t_x + 300, bal_y + 1))

        # -------------------------------------------------------------
        # 5. GOODS LIST, STOCK, SELLING PRICES & CONTROLS
        # -------------------------------------------------------------
        list_y = stats_rect.bottom + 16
        sec_title = "MARKET GOODS, ACTIVE SELLING PRICES & STOCK MANAGEMENT:"
        surface.blit(self.font_sub.render(sec_title, True, COLOR_TEXT_TITLE), (mx + 24, list_y))

        # Table Header
        th_y = list_y + 22
        pygame.draw.rect(surface, (30, 41, 59), (mx + 24, th_y, self.modal_w - 48, 24), border_radius=4)
        surface.blit(self.font_badge.render("ITEM", True, COLOR_TEXT_MUTED), (mx + 36, th_y + 4))
        surface.blit(self.font_badge.render("MARKET STOCK", True, COLOR_TEXT_MUTED), (mx + 170, th_y + 4))
        surface.blit(self.font_badge.render("SELLING PRICE", True, COLOR_TEXT_MUTED), (mx + 290, th_y + 4))
        surface.blit(self.font_badge.render("PRICE ADJUSTMENT", True, COLOR_TEXT_MUTED), (mx + 395, th_y + 4))
        surface.blit(self.font_badge.render("MANAGE STOCK", True, COLOR_TEXT_MUTED), (mx + 535, th_y + 4))

        # Reset button rect mappings for this frame
        self.price_dec_btns.clear()
        self.price_inc_btns.clear()
        self.price_dec5_btns.clear()
        self.price_inc5_btns.clear()
        self.stock_dep_btns.clear()
        self.stock_with_btns.clear()

        # Daftar komoditas pasar (Potato sebagai staple utama + generic item definitions)
        market_items = ["Potato"]
        for it in mkt.inventory:
            if it not in market_items:
                market_items.append(it)
        for it in mkt.prices:
            if it not in market_items:
                market_items.append(it)

        row_y = th_y + 30
        row_h = 44
        m_pos = pygame.mouse.get_pos()

        for it_name in market_items:
            stock_qty = mkt.inventory.get(it_name, 0)
            active_price = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 3))

            card_rect = pygame.Rect(mx + 24, row_y, self.modal_w - 48, row_h)
            pygame.draw.rect(surface, (15, 23, 42, 220), card_rect, border_radius=6)
            pygame.draw.rect(surface, (51, 65, 85), card_rect, width=1, border_radius=6)

            # Item Icon & Name
            col = RESOURCE_COLORS.get(it_name, (200, 200, 200))
            pygame.draw.circle(surface, col, (mx + 46, row_y + row_h // 2), 7)
            surface.blit(self.font_sub.render(it_name, True, (241, 245, 249)), (mx + 60, row_y + 12))

            # Stock Quantity
            stock_str = f"{stock_qty} in stock" if stock_qty > 0 else "OUT OF STOCK"
            stock_col = (34, 197, 94) if stock_qty > 0 else (239, 68, 68)
            surface.blit(self.font_sub.render(stock_str, True, stock_col), (mx + 170, row_y + 12))

            # Active Selling Price
            pr_str = f"{active_price} Copper"
            surface.blit(self.font_title.render(pr_str, True, (250, 204, 21)), (mx + 290, row_y + 10))

            # Price Adjustment Buttons ([-5] [-1] [+1] [+5])
            btn_y = row_y + 8
            # [-5]
            btn_m5 = pygame.Rect(mx + 395, btn_y, 28, 26)
            self.price_dec5_btns[it_name] = btn_m5
            h_m5 = btn_m5.collidepoint(m_pos)
            pygame.draw.rect(surface, (71, 85, 105) if h_m5 else (30, 41, 59), btn_m5, border_radius=4)
            pygame.draw.rect(surface, (100, 116, 139), btn_m5, width=1, border_radius=4)
            surface.blit(self.font_badge.render("-5", True, (255, 255, 255)), (btn_m5.x + 6, btn_m5.y + 6))

            # [-1]
            btn_m1 = pygame.Rect(mx + 427, btn_y, 28, 26)
            self.price_dec_btns[it_name] = btn_m1
            h_m1 = btn_m1.collidepoint(m_pos)
            pygame.draw.rect(surface, (220, 38, 38) if h_m1 else (153, 27, 27), btn_m1, border_radius=4)
            surface.blit(self.font_sub.render("-", True, (255, 255, 255)), (btn_m1.x + 10, btn_m1.y + 4))

            # [+1]
            btn_p1 = pygame.Rect(mx + 459, btn_y, 28, 26)
            self.price_inc_btns[it_name] = btn_p1
            h_p1 = btn_p1.collidepoint(m_pos)
            pygame.draw.rect(surface, (22, 163, 74) if h_p1 else (21, 128, 61), btn_p1, border_radius=4)
            surface.blit(self.font_sub.render("+", True, (255, 255, 255)), (btn_p1.x + 8, btn_p1.y + 4))

            # [+5]
            btn_p5 = pygame.Rect(mx + 491, btn_y, 28, 26)
            self.price_inc5_btns[it_name] = btn_p5
            h_p5 = btn_p5.collidepoint(m_pos)
            pygame.draw.rect(surface, (71, 85, 105) if h_p5 else (30, 41, 59), btn_p5, border_radius=4)
            pygame.draw.rect(surface, (100, 116, 139), btn_p5, width=1, border_radius=4)
            surface.blit(self.font_badge.render("+5", True, (255, 255, 255)), (btn_p5.x + 5, btn_p5.y + 6))

            # Stock Management Buttons: [+10 Deposit] and [-10 Withdraw]
            # [+ Deposit 10]
            btn_dep = pygame.Rect(mx + 535, btn_y, 64, 26)
            self.stock_dep_btns[it_name] = btn_dep
            h_dep = btn_dep.collidepoint(m_pos)
            pygame.draw.rect(surface, (37, 99, 235) if h_dep else (30, 58, 138), btn_dep, border_radius=4)
            surface.blit(self.font_badge.render("+10 Stock", True, (255, 255, 255)), (btn_dep.x + 5, btn_dep.y + 6))

            # [- Withdraw 10]
            btn_with = pygame.Rect(mx + 605, btn_y, 64, 26)
            self.stock_with_btns[it_name] = btn_with
            h_with = btn_with.collidepoint(m_pos)
            pygame.draw.rect(surface, (71, 85, 105) if h_with else (51, 65, 85), btn_with, border_radius=4)
            surface.blit(self.font_badge.render("-10 Stock", True, (255, 255, 255)), (btn_with.x + 5, btn_with.y + 6))

            row_y += row_h + 8

        # -------------------------------------------------------------
        # 6. FOOTER: ECONOMIC INSTRUCTION & LANDLORD STOCKPILE SUMMARY
        # -------------------------------------------------------------
        footer_y = my + self.modal_h - 70
        footer_rect = pygame.Rect(mx + 24, footer_y, self.modal_w - 48, 52)
        pygame.draw.rect(surface, (24, 34, 52), footer_rect, border_radius=6)
        pygame.draw.rect(surface, (71, 85, 105), footer_rect, width=1, border_radius=6)

        # Landlord storage summary
        ll_food = 0
        if resources:
            ll_food = resources.get("Food", 0)
        elif stockpile_manager:
            for s in getattr(stockpile_manager, "stacks", []):
                if s.owner_type == "landlord" and s.resource_type in ("Food", "Potato", "potato"):
                    ll_food += s.amount

        info_l1 = f"Landlord Storage: {ll_food} Potatoes available to transfer to Market."
        info_l2 = "AI villagers will automatically walk to this market to purchase food using their own funds when hungry."
        surface.blit(self.font_body.render(info_l1, True, (245, 158, 11)), (footer_rect.x + 12, footer_rect.y + 8))
        surface.blit(self.font_badge.render(info_l2, True, COLOR_TEXT_MUTED), (footer_rect.x + 12, footer_rect.y + 28))
