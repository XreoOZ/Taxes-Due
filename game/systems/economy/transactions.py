"""
Universal Transaction Primitives (Config-Driven, Zero Hardcode)
================================================================
Satu layer untuk SEMUA pertukaran fisik antar-entity di game ini:

    collect_coins()   — ambil koin rumah tangga ke kantong carrier
    pay_coins()       — bayar exact value dengan koin asli + kembalian
    query_stock()     — total item milik household di SEMUA sumber fisik
    take_stock()      — ambil item dari sumber fisik terdekat
    deliver_goods()   — serahkan barang ke chest keluarga / tile permit
                        (fallback chestless: owner-tagged loose stack)

Aturan universal (dipakai semua job, tanpa hardcode per-job):
  - Uang = koin fisik berdenominasi. Tidak ada transfer "abstract wallet"
    jarak jauh; setiap pemindahan terjadi saat carrier berada di lokasi
    sumber (chest, ground stack, atau member serumah yang satu rumah).
  - Barang = item fisik di inventory/chest/ground stack. Tidak ada
    teleportasi: deliver_goods selalu lewat chest atau drop di tile
    permit household.
  - Affordability boleh "abstract" (hitung semua sumber), tapi COLLECTION
    selalu fisik — fungsi di file ini hanya memindahkan koin yang memang
    bisa dijangkau carrier saat itu juga.
"""

from game.data.config import TILE_SIZE, VILLAGER_INVENTORY_CAPACITY, EXCHANGE_RATES
from game.systems.economy.currency import (
    canonical_denomination,
    compact_currency_wallet,
    normalize_wallet,
    to_copper,
    transfer_currency_value,
    calculate_payment_and_change,
    execute_currency_transfer,
    CURRENCY_DENOMINATIONS,
)

_DENOM_RATE = {d: EXCHANGE_RATES.get(d, 1) for d in CURRENCY_DENOMINATIONS}


def household_chest(family_id, furniture_manager):
    """Storage chest milik keluarga, atau None."""
    if furniture_manager is None or family_id is None:
        return None
    try:
        return furniture_manager.get_storage_for_family(str(family_id))
    except Exception:
        return None


def family_loose_stacks(family_id, stockpile_manager):
    """Semua ground stack milik household (owner_type='villager', owner_id=family)."""
    fid = str(family_id or "")
    if not stockpile_manager or not fid:
        return []
    return [
        s for s in getattr(stockpile_manager, "stacks", [])
        if getattr(s, "owner_type", None) == "villager"
        and str(getattr(s, "owner_id", "")) == fid
    ]


def query_stock(family_id, item_name, furniture_manager=None,
                villager_manager=None, stockpile_manager=None,
                include_member_pockets=True):
    """
    Total item `item_name` milik household di SEMUA sumber fisik:
    chest + ground stacks milik keluarga + kantong member hidup (+family purse).
    Read-only — dipakai untuk cek material/food/water/coins secara universal.
    """
    total = 0

    def _add_wallet(wallet):
        nonlocal total
        if not isinstance(wallet, dict):
            return
        if canonical_denomination(item_name):
            total += int(wallet.get(item_name, 0) or 0)
        else:
            total += int(wallet.get(item_name, 0) or 0)

    chest = household_chest(family_id, furniture_manager)
    if chest is not None:
        _add_wallet(getattr(chest, "inventory", {}))

    for stack in family_loose_stacks(family_id, stockpile_manager):
        if getattr(stack, "resource_type", None) == item_name:
            total += int(getattr(stack, "available_amount", getattr(stack, "amount", 0)) or 0)

    if include_member_pockets and villager_manager is not None:
        fam = None
        try:
            fam = villager_manager.get_family_by_id(str(family_id))
        except Exception:
            fam = None
        if fam is not None:
            purse = getattr(fam, "currency", None)
            if isinstance(purse, dict):
                _add_wallet(purse)
            for member in getattr(fam, "members", []) or []:
                if not getattr(member, "is_alive", True):
                    continue
                _add_wallet(getattr(member, "inventory", {}))

    return total


def household_coin_total_copper(family_id, furniture_manager=None,
                                villager_manager=None, stockpile_manager=None):
    """Total nilai koin household dalam copper — SEMUA sumber fisik."""
    total = 0
    chest = household_chest(family_id, furniture_manager)
    if chest is not None:
        total += to_copper(getattr(chest, "inventory", {}))
    for stack in family_loose_stacks(family_id, stockpile_manager):
        d = canonical_denomination(getattr(stack, "resource_type", ""))
        if d and getattr(stack, "amount", 0) > 0:
            total += int(stack.amount) * _DENOM_RATE.get(d, 1)
    if villager_manager is not None:
        fam = None
        try:
            fam = villager_manager.get_family_by_id(str(family_id))
        except Exception:
            fam = None
        if fam is not None:
            cur = getattr(fam, "currency", None)
            if isinstance(cur, dict):
                total += to_copper(cur)
            for member in getattr(fam, "members", []) or []:
                if getattr(member, "is_alive", True):
                    total += to_copper(getattr(member, "inventory", {}))
    return total


def collect_coins(carrier, family_id, amount_copper, furniture_manager=None,
                  villager_manager=None, stockpile_manager=None,
                  building_manager=None, permit_manager=None):
    """
    Pindahkan koin senilai `amount_copper` dari sumber fisik household ke
    `carrier.inventory`. Sumber (urutan): kantong carrier sendiri → chest
    keluarga → loose coin stacks milik keluarga → kantong member serumah.

    CATATAN FISIK: fungsi ini memindahkan koin antar-wallet; caller WAJIB
    sudah berada di lokasi sumber (sudah berjalan ke chest / stack) atau
    serumah dengan member tersebut. Pocket member lain hanya diambil bila
    member itu serumah (jarak ≤ TILE_SIZE*2) — bukan telepathy.

    Returns: (success: bool, message: str)
    """
    pocket = getattr(carrier, "inventory", None)
    if not isinstance(pocket, dict):
        return False, "Carrier has no inventory."
    need = max(0, int(amount_copper))
    have = to_copper(normalize_wallet(pocket))
    if have >= need:
        return True, "Carrier already holds enough coins."
    deficit = need - have

    fid = str(family_id or getattr(carrier, "family_id", "") or "")

    # 1. Chest keluarga (caller berjalan ke sini)
    chest = household_chest(fid, furniture_manager)
    chest_inv = getattr(chest, "inventory", None) if chest is not None else None
    if isinstance(chest_inv, dict):
        c = to_copper(normalize_wallet(chest_inv))
        if c > 0:
            ok, _ = transfer_currency_value(chest_inv, pocket, min(deficit, c))
            deficit = need - to_copper(normalize_wallet(pocket))
            if deficit <= 0:
                return True, "Collected coins from household chest."

    # 2. Loose coin stacks milik keluarga di tanah
    sm = stockpile_manager or getattr(carrier, "stockpile_manager", None)
    for stack in family_loose_stacks(fid, sm):
        if deficit <= 0:
            break
        d = canonical_denomination(getattr(stack, "resource_type", ""))
        if not d:
            continue
        avail = int(getattr(stack, "available_amount", getattr(stack, "amount", 0)) or 0)
        if avail <= 0:
            continue
        # Ambil denominasi apa adanya — stack.amount dalam unit koin.
        rate = _DENOM_RATE.get(d, 1)
        take_val = min(deficit, avail * rate)
        # transfer_currency_value butuh wallet dict; stack bukan dict —
        # pindahkan manual per-unit koin.
        remaining_val = take_val
        while remaining_val > 0 and getattr(stack, "amount", 0) > 0:
            pocket[d] = pocket.get(d, 0) + 1
            stack.amount -= 1
            remaining_val -= rate
        if getattr(stack, "amount", 0) <= 0 and hasattr(sm, "stacks"):
            try:
                sm.stacks.remove(stack)
            except ValueError:
                pass
        deficit = need - to_copper(normalize_wallet(pocket))
    if deficit <= 0:
        return True, "Collected coins from household ground stacks."

    # 3. Kantong member serumah — fisik: member harus benar-benar berada
    #    di dalam area permit household (atau sangat dekat jika permit
    #    tidak diketahui). Member yang sedang dinas luar tidak bisa
    #    "menitipkan" koin dari jauh.
    vm = villager_manager or getattr(carrier, "villager_manager", None)
    pm = permit_manager or getattr(carrier, "permit_manager", None)
    permit_tiles = None
    if pm is not None and fid:
        try:
            fam_for_permit = vm.get_family_by_id(fid) if vm is not None else None
            pid = getattr(fam_for_permit, "assigned_permit_id", None)
            permit = next((p for p in getattr(pm, "permits", [])
                           if str(getattr(p, "id", "")) == str(pid)), None)
            tiles = getattr(permit, "tiles", None)
            if tiles:
                permit_tiles = set(tiles)
        except Exception:
            permit_tiles = None
    near_radius = TILE_SIZE * 2
    if vm is not None:
        try:
            fam = vm.get_family_by_id(fid)
        except Exception:
            fam = None
        if fam is not None:
            cx, cy = getattr(carrier, "x", 0), getattr(carrier, "y", 0)
            for member in getattr(fam, "members", []) or []:
                if deficit <= 0:
                    break
                if member is carrier or not getattr(member, "is_alive", True):
                    continue
                minv = getattr(member, "inventory", None)
                if not isinstance(minv, dict):
                    continue
                mx, my = getattr(member, "x", None), getattr(member, "y", None)
                if mx is None or my is None:
                    continue
                reachable = False
                if permit_tiles is not None:
                    m_tile = (int(mx // TILE_SIZE), int(my // TILE_SIZE))
                    reachable = m_tile in permit_tiles
                else:
                    reachable = ((mx - cx) ** 2 + (my - cy) ** 2) ** 0.5 <= near_radius
                if not reachable:
                    continue
                c = to_copper(normalize_wallet(minv))
                if c > 0:
                    ok, _ = transfer_currency_value(minv, pocket, min(deficit, c))
                    deficit = need - to_copper(normalize_wallet(pocket))
    if deficit <= 0:
        return True, "Collected coins from household members."
    return False, "Household does not have enough reachable coins."


def pay_coins(sender, recipient_wallet, amount_copper, recipient_entity=None):
    """
    Bayar `amount_copper` dari `sender.inventory` ke `recipient_wallet`
    (dict wallet entity lain, mis. chest.inventory / builder.inventory).
    Memakai koin berdenominasi asli + mekanisme kembalian yang sama dengan
    pasar (calculate_payment_and_change) — conservation terverifikasi.

    `recipient_entity` opsional: jika recipient adalah entity dengan
    inventory dict, pass wallet-nya langsung sebagai recipient_wallet.
    Returns: (success, message)
    """
    s_inv = getattr(sender, "inventory", None)
    if not isinstance(s_inv, dict):
        return False, "Sender has no inventory."
    if not isinstance(recipient_wallet, dict):
        return False, "Recipient wallet unavailable."
    amount = max(0, int(amount_copper))
    if amount <= 0:
        return True, "Zero payment."
    ok, payment, change, msg = calculate_payment_and_change(
        normalize_wallet(s_inv), amount, recipient_wallet
    )
    if not ok:
        return False, msg
    ok2, _, _, tmsg = execute_currency_transfer(s_inv, recipient_wallet, payment, change)
    if not ok2:
        return False, tmsg
    compact_currency_wallet(s_inv)
    compact_currency_wallet(recipient_wallet)
    return True, f"Paid {amount}c."


def query_material_stock(family_id, materials, furniture_manager=None,
                         villager_manager=None, stockpile_manager=None):
    """
    Total per-material milik household di semua sumber fisik.
    Returns dict {material: total_count} — dipakai semua job untuk cek
    'apakah material sudah ada' tanpa peduli chest/inventory/stack.
    """
    out = {}
    for mat in materials:
        out[mat] = query_stock(
            family_id, mat, furniture_manager, villager_manager,
            stockpile_manager, include_member_pockets=True)
    return out


def deliver_goods(carrier, family_id, items, furniture_manager=None,
                  stockpile_manager=None, permit_manager=None,
                  building_manager=None, ref_x=None, ref_y=None):
    """
    Serahkan `items` ({item: qty}) ke household `family_id` secara fisik:
      1. chest keluarga → store_item per item
      2. chestless → owner-tagged loose stack DI DALAM tile permit
         household (resolve_household_ground_drop_tile), fallback ke
         posisi carrier.
    Menghapus item dari carrier.inventory. Returns (delivered_dict, leftover_dict).
    """
    delivered, leftover = {}, {}
    inv = getattr(carrier, "inventory", None)
    if not isinstance(inv, dict):
        return {}, dict(items)
    chest = household_chest(family_id, furniture_manager)

    for item, qty in items.items():
        have = int(inv.get(item, 0) or 0)
        take = min(have, int(qty))
        if take <= 0:
            leftover[item] = int(qty)
            continue
        if chest is not None:
            chest.store_item(item, take)
            delivered[item] = take
        else:
            # chestless: drop di tile permit household
            gx, gy = None, None
            if permit_manager is not None and ref_x is not None:
                try:
                    from game.world.permits import resolve_household_ground_drop_tile
                    tile = resolve_household_ground_drop_tile(
                        str(family_id), permit_manager, building_manager,
                        furniture_manager=furniture_manager,
                        ref_x=ref_x, ref_y=ref_y)
                    if tile:
                        gx, gy = tile
                except Exception:
                    gx = gy = None
            if gx is None:
                gx = int((ref_x if ref_x is not None else getattr(carrier, "x", 0)) // TILE_SIZE)
                gy = int((ref_y if ref_y is not None else getattr(carrier, "y", 0)) // TILE_SIZE)
            sm = stockpile_manager or getattr(carrier, "stockpile_manager", None)
            if sm is not None and hasattr(sm, "drop_resource"):
                sm.drop_resource(item, take, gx, gy,
                                 owner_type="villager", owner_id=str(family_id))
                delivered[item] = take
            else:
                leftover[item] = int(qty)
                continue
        inv[item] -= take
        if inv[item] <= 0:
            inv.pop(item, None)
        if take < int(qty):
            leftover[item] = int(qty) - take
    return delivered, leftover


def inventory_room(inventory):
    """Sisa slot inventory (non-kurrency) — wrapper universal."""
    from game.systems.economy.household_inventory import get_inventory_room
    return get_inventory_room(inventory if isinstance(inventory, dict) else {})
