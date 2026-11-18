"""
Market Purchasing Service & Economy Interface (Owned by AGENT 2)
Provides an atomic, reusable purchasing interface for AGENT 1 (AI needs & hunger)
and other systems to interact with the landlord-controlled market.
"""

import time
from game.data.config import (
    DEFAULT_ITEM_PRICES,
    CURRENCY_DENOMINATIONS,
    DENOMINATION_CAP
)
from game.systems.currency import (
    to_copper,
    from_copper,
    normalize_wallet,
    calculate_payment_and_change,
    execute_currency_transfer,
    canonical_denomination
)

class MarketService:
    """
    Market Purchasing Service (AGENT 2)
    Provides safe, atomic transactions for households purchasing goods from the market.
    """

    @classmethod
    def get_market(cls, building_manager):
        """Mendapatkan gedung MARKET pertama yang sudah selesai dibangun (completed)"""
        if not building_manager:
            return None
        for b in building_manager.buildings:
            if getattr(b, "building_type", "") == "market":
                return b
        return None

    @classmethod
    def get_all_markets(cls, building_manager):
        """Mendapatkan seluruh gedung market aktif"""
        if not building_manager:
            return []
        return [b for b in building_manager.buildings if getattr(b, "building_type", "") == "market"]

    @classmethod
    def get_item_price(cls, item_name, market=None):
        """
        Membaca harga jual aktif terkini untuk suatu item dalam satuan Copper.
        Prioritas: harga yang dikonfigurasi landlord di Market Profile -> DEFAULT_ITEM_PRICES -> 0
        """
        if market and hasattr(market, "prices") and item_name in market.prices:
            return market.prices[item_name]
        return DEFAULT_ITEM_PRICES.get(item_name, 0)

    @classmethod
    def get_market_stock(cls, item_name, market):
        """Mengecek ketersediaan stok barang di pasar"""
        if not market or not hasattr(market, "inventory"):
            return 0
        return market.inventory.get(item_name, 0)

    @classmethod
    def resolve_household_info(cls, household, villager_manager=None):
        """
        Mengurai referensi household (Family, Villager, ID str/int, dict)
        menjadi (family_id, family_obj, villager_obj).
        """
        family_id = None
        family_obj = None
        villager_obj = None

        if hasattr(household, "surname") and hasattr(household, "members"):
            # Family instance
            family_obj = household
            family_id = str(household.id)
        elif hasattr(household, "family_id") and hasattr(household, "first_name"):
            # Villager instance
            villager_obj = household
            family_id = str(household.family_id)
            if villager_manager:
                family_obj = villager_manager.get_family_by_id(family_id)
        elif isinstance(household, (str, int)):
            family_id = str(household)
            if villager_manager:
                family_obj = villager_manager.get_family_by_id(family_id)
        elif isinstance(household, dict):
            family_id = str(household.get("family_id", household.get("id", "")))

        return family_id, family_obj, villager_obj

    @classmethod
    def get_household_funds_and_source(cls, household, furniture_manager=None, villager_manager=None):
        """
        Memeriksa seluruh dana mandiri (Copper, Silver, Gold) milik household:
        Prioritas pengecekan:
        1. Peti penyimpanan keluarga (household_storage chest)
        2. Objek Family (jika memiliki atribut currency / funds / inventory)
        3. Kantong/inventory villager jika passed sebagai villager
        Mengembalikan: (wallet_dict, primary_source_dict)
        """
        fam_id, fam_obj, vil_obj = cls.resolve_household_info(household, villager_manager)
        wallet = {"Copper": 0, "Silver": 0, "Gold": 0}
        source_dict = None

        # 1. Cek household chest
        if furniture_manager and fam_id:
            chest = furniture_manager.get_storage_for_family(fam_id)
            if chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
                has_coins = any(canonical_denomination(k) for k in chest.inventory)
                if has_coins:
                    source_dict = chest.inventory
                    for k, v in chest.inventory.items():
                        c_name = canonical_denomination(k)
                        if c_name:
                            wallet[c_name] += max(0, int(v))
                    return wallet, source_dict

        # 2. Cek family object
        if fam_obj:
            for attr in ("currency", "funds", "inventory"):
                f_wallet = getattr(fam_obj, attr, None)
                if isinstance(f_wallet, dict) and any(canonical_denomination(k) for k in f_wallet):
                    source_dict = f_wallet
                    for k, v in f_wallet.items():
                        c_name = canonical_denomination(k)
                        if c_name:
                            wallet[c_name] += max(0, int(v))
                    return wallet, source_dict

        # 3. Cek villager inventory
        if vil_obj and hasattr(vil_obj, "inventory") and isinstance(vil_obj.inventory, dict):
            has_coins = any(canonical_denomination(k) for k in vil_obj.inventory)
            if has_coins:
                source_dict = vil_obj.inventory
                for k, v in vil_obj.inventory.items():
                    c_name = canonical_denomination(k)
                    if c_name:
                        wallet[c_name] += max(0, int(v))
                return wallet, source_dict

        # Jika chest ada tetapi belum punya koin sama sekali
        if furniture_manager and fam_id:
            chest = furniture_manager.get_storage_for_family(fam_id)
            if chest and hasattr(chest, "inventory"):
                return wallet, chest.inventory

        # Fallback ke family currency jika ada
        if fam_obj:
            if not hasattr(fam_obj, "currency"):
                fam_obj.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
            return wallet, fam_obj.currency

        return wallet, None

    @classmethod
    def can_purchase(cls, household, item_name, quantity=1, building_manager=None, furniture_manager=None, villager_manager=None):
        """
        Validasi pra-transaksi untuk AGENT 1 / AI Needs:
        Mengecek apakah pasar ada, barang tersedia, dan household memiliki dana yang cukup.
        Returns: (can_buy: bool, reason: str, unit_price: int, total_price: int)
        """
        if quantity <= 0:
            return False, "Quantity must be greater than 0", 0, 0

        # Air tidak diperjualbelikan (WIP scope)
        if item_name.strip().lower() == "water":
            return False, "Water sales are WIP. Water purchasing is not available.", 0, 0

        market = cls.get_market(building_manager)
        if not market:
            return False, "No completed market building found in village", 0, 0

        stock = cls.get_market_stock(item_name, market)
        if stock < quantity:
            return False, f"Insufficient market stock: requested {quantity}, available {stock}", 0, 0

        unit_price = cls.get_item_price(item_name, market)
        if unit_price <= 0:
            return False, "Food is never free. Item has no configured valid selling price.", 0, 0

        total_price = unit_price * quantity
        wallet, _ = cls.get_household_funds_and_source(household, furniture_manager, villager_manager)
        total_funds = to_copper(wallet)

        if total_funds < total_price:
            return False, f"Insufficient household funds: has {total_funds}c, price is {total_price}c", unit_price, total_price

        # Cek apakah dapat membentuk kombinasi koin yang valid
        ok, pay, chg, msg = calculate_payment_and_change(wallet, total_price, getattr(market, "currency", None))
        if not ok:
            return False, f"Payment combination error: {msg}", unit_price, total_price

        return True, "Ready for purchase", unit_price, total_price

    @classmethod
    def execute_purchase(cls, household, item_name, quantity=1, building_manager=None, furniture_manager=None, villager_manager=None):
        """
        EKSEKUSI TRANSAKSI PEMBELIAN PASAR SECARA ATOMIK:
        1. Menerima purchasing household & requested food item.
        2. Mengecek ketersediaan stok pasar.
        3. Membaca harga jual aktif terkini (latest configured price).
        4. Memeriksa ketersediaan Copper, Silver, Gold milik household.
        5. Menentukan kombinasi pembayaran yang valid.
        6. Menghitung dan memberikan uang kembalian.
        7. Mentransfer pembayaran ke dana kas pasar.
        8. Mentransfer barang yang dibeli ke tempat penyimpanan household (chest).
        9. Menyelesaikan transaksi secara ATOMIK (all-or-nothing).

        Returns:
            (success: bool, message: str, receipt: dict)
        """
        if quantity <= 0:
            return False, "Quantity must be greater than zero", {}

        # Validasi batas WIP: air tidak dijual
        if item_name.strip().lower() == "water":
            return False, "Water sales are WIP. Water purchasing is not available.", {}

        market = cls.get_market(building_manager)
        if not market:
            return False, "No completed market building found", {}

        # 1. Cek stok pasar
        stock = cls.get_market_stock(item_name, market)
        if stock < quantity:
            return False, f"Insufficient market stock: requested {quantity}, available {stock}", {}

        # 2. Baca harga terkini (Food is NEVER free!)
        unit_price = cls.get_item_price(item_name, market)
        if unit_price <= 0:
            return False, "Food is never free. Selling price must be greater than 0.", {}

        total_price = unit_price * quantity

        # 3. Cek dana household
        wallet, source_dict = cls.get_household_funds_and_source(household, furniture_manager, villager_manager)
        if source_dict is None:
            return False, "Household has no storage chest or wallet to hold funds", {}

        total_funds = to_copper(wallet)
        if total_funds < total_price:
            return False, f"Insufficient funds: household has {total_funds}c, item costs {total_price}c", {}

        # Pastikan market memiliki dictionary currency yang valid
        if not hasattr(market, "currency") or not isinstance(market.currency, dict):
            market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}

        # 4. Tentukan kombinasi pembayaran & uang kembalian
        ok, payment, change, msg = calculate_payment_and_change(wallet, total_price, market.currency)
        if not ok:
            return False, f"Transaction aborted: {msg}", {}

        # 5. Cari target penyimpanan household (Peti / Chest)
        fam_id, fam_obj, vil_obj = cls.resolve_household_info(household, villager_manager)
        dest_chest = None
        if furniture_manager and fam_id:
            dest_chest = furniture_manager.get_storage_for_family(fam_id)

        # 6. ATOMIC COMMIT: Eksekusi transfer koin dan barang secara bersamaan
        # A. Transfer mata uang
        transfer_ok, new_cust_w, new_mkt_w, t_msg = execute_currency_transfer(
            source_dict, market.currency, payment, change
        )
        if not transfer_ok:
            return False, f"Currency transfer failed: {t_msg}", {}

        # B. Kurangi stok pasar
        market.inventory[item_name] -= quantity
        if market.inventory[item_name] <= 0:
            del market.inventory[item_name]

        # C. Masukkan barang ke penyimpanan household
        delivered_to = "chest"
        if dest_chest:
            dest_chest.store_item(item_name, quantity)
        elif vil_obj and hasattr(vil_obj, "inventory"):
            vil_obj.inventory[item_name] = vil_obj.inventory.get(item_name, 0) + quantity
            delivered_to = "villager_inventory"
        elif fam_obj:
            if not hasattr(fam_obj, "inventory"):
                fam_obj.inventory = {}
            fam_obj.inventory[item_name] = fam_obj.inventory.get(item_name, 0) + quantity
            delivered_to = "family_inventory"
        else:
            delivered_to = "source_dict"
            source_dict[item_name] = source_dict.get(item_name, 0) + quantity

        receipt = {
            "success": True,
            "household_id": fam_id,
            "item_name": item_name,
            "quantity": quantity,
            "unit_price_copper": unit_price,
            "total_price_copper": total_price,
            "payment": payment,
            "change": change,
            "household_remaining_funds": new_cust_w,
            "market_funds": dict(market.currency),
            "delivered_to": delivered_to,
            "timestamp": time.time()
        }

        return True, f"Successfully purchased {quantity}x {item_name} for {total_price} Copper.", receipt
