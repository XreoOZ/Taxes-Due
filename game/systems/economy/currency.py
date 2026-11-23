"""
Currency & Economy System (Config-Driven, Zero Hardcode)
Handles denominations (Copper, Silver, Gold), exchange rates, conversions,
change-making, denomination caps, and conservation of value.
"""

from game.data.config import (
    DENOMINATION_CAP,
    CURRENCY_DENOMINATIONS,
    EXCHANGE_RATES,
    DEFAULT_ITEM_PRICES
)

COPPER_PER_SILVER = EXCHANGE_RATES.get("Silver", 10)
SILVER_PER_GOLD = EXCHANGE_RATES.get("Gold", 100) // COPPER_PER_SILVER
COPPER_PER_GOLD = EXCHANGE_RATES.get("Gold", 100)

_COIN_ALIASES = {
    "copper": "Copper",
    "copper coin": "Copper",
    "copper_coin": "Copper",
    "silver": "Silver",
    "silver coin": "Silver",
    "silver_coin": "Silver",
    "gold": "Gold",
    "gold coin": "Gold",
    "gold_coin": "Gold"
}

def canonical_denomination(name):
    """Mengembalikan nama denominasi standar ('Copper', 'Silver', 'Gold') atau None"""
    if not isinstance(name, str):
        return None
    return _COIN_ALIASES.get(name.strip().lower(), None)

def is_currency_item(item_name):
    """Mengecek apakah item merupakan mata uang terdaftar"""
    return canonical_denomination(item_name) is not None

def normalize_wallet(wallet):
    """
    Memastikan wallet memiliki kunci Copper, Silver, Gold dengan nilai integer non-negatif.
    Mendukung alias nama item seperti 'Copper Coin'.
    """
    normalized = {"Copper": 0, "Silver": 0, "Gold": 0}
    if not isinstance(wallet, dict):
        return normalized

    for k, v in wallet.items():
        c_name = canonical_denomination(k)
        if c_name:
            try:
                normalized[c_name] += max(0, int(v))
            except (ValueError, TypeError):
                pass
    denominations = sorted(
        CURRENCY_DENOMINATIONS,
        key=lambda denomination: EXCHANGE_RATES.get(denomination, 0),
    )
    for lower, higher in zip(denominations, denominations[1:]):
        lower_value = EXCHANGE_RATES.get(lower, 0)
        higher_value = EXCHANGE_RATES.get(higher, 0)
        if lower_value <= 0 or higher_value <= lower_value or higher_value % lower_value:
            continue
        conversion_rate = higher_value // lower_value
        converted, normalized[lower] = divmod(normalized[lower], conversion_rate)
        normalized[higher] += converted
    return normalized

def compact_currency_wallet(wallet):
    """Compact coin denominations in-place while preserving unrelated inventory."""
    if not isinstance(wallet, dict):
        return normalize_wallet(wallet)
    compacted = normalize_wallet(wallet)
    for key in list(wallet):
        if canonical_denomination(key):
            del wallet[key]
    wallet.update({denomination: count for denomination, count in compacted.items() if count > 0})
    return compacted

def to_copper(wallet):
    """Menghitung total nilai moneter dalam satuan Copper (1 Gold = 100c, 1 Silver = 10c, 1 Copper = 1c)"""
    w = normalize_wallet(wallet)
    return (
        w["Copper"] * EXCHANGE_RATES.get("Copper", 1) +
        w["Silver"] * EXCHANGE_RATES.get("Silver", 10) +
        w["Gold"] * EXCHANGE_RATES.get("Gold", 100)
    )

def transfer_currency_value(source_wallet, destination_wallet, amount_in_copper):
    """Move the smallest available set of coins whose value covers an amount.

    This is a physical withdrawal, so it transfers whole coins without requiring
    the source wallet to make change. Any excess value can be returned after the
    eventual purchase transaction.
    """
    if not isinstance(source_wallet, dict) or not isinstance(destination_wallet, dict):
        return False, "Currency wallet is unavailable."

    compact_currency_wallet(source_wallet)
    required = max(0, int(amount_in_copper))
    source_value = to_copper(source_wallet)
    if source_value < required:
        return False, f"Insufficient funds: has {source_value}c, needs {required}c."
    if required == 0:
        return True, "No withdrawal needed."

    remaining = required
    selected = {}
    denominations = sorted(
        CURRENCY_DENOMINATIONS,
        key=lambda denomination: EXCHANGE_RATES.get(denomination, 0),
        reverse=True,
    )
    normalized = normalize_wallet(source_wallet)
    for denomination in denominations:
        coin_value = EXCHANGE_RATES.get(denomination, 0)
        if coin_value <= 0:
            continue
        count = min(normalized.get(denomination, 0), (remaining + coin_value - 1) // coin_value)
        if count:
            selected[denomination] = count
            remaining -= count * coin_value
        if remaining <= 0:
            break

    if remaining > 0:
        return False, "Available denominations cannot cover the withdrawal."

    for denomination, count in selected.items():
        amount_left = count
        for source_key in list(source_wallet):
            if canonical_denomination(source_key) != denomination:
                continue
            moved = min(amount_left, max(0, int(source_wallet[source_key])))
            source_wallet[source_key] -= moved
            amount_left -= moved
            if source_wallet[source_key] <= 0:
                del source_wallet[source_key]
            if amount_left <= 0:
                break
        if amount_left > 0:
            return False, "Currency changed before withdrawal completed."
        destination_wallet[denomination] = destination_wallet.get(denomination, 0) + count

    compact_currency_wallet(destination_wallet)
    return True, "Currency transferred."

def from_copper(copper_val):
    """
    Dekomposisi nilai Copper ke denominasi greedy (Gold -> Silver -> Copper).
    Contoh: 197c -> 1 Gold, 9 Silver, 7 Copper; 7c -> 7 Copper; 90c -> 9 Silver.
    """
    val = max(0, int(copper_val))
    g = val // COPPER_PER_GOLD
    rem = val % COPPER_PER_GOLD
    s = rem // COPPER_PER_SILVER
    c = rem % COPPER_PER_SILVER
    return {"Copper": c, "Silver": s, "Gold": g}

def transfer_exact_value(source_wallet, destination_wallet, amount_in_copper):
    """Transfer an exact value between wallets, making denomination change without losing value."""
    if not isinstance(source_wallet, dict) or not isinstance(destination_wallet, dict):
        return False, "Currency wallet is unavailable."
    amount = max(0, int(amount_in_copper))
    source_value = to_copper(source_wallet)
    if source_value < amount:
        return False, "Insufficient funds."
    destination_value = to_copper(destination_wallet)
    source_after = from_copper(source_value - amount)
    destination_after = from_copper(destination_value + amount)
    for wallet, converted in ((source_wallet, source_after), (destination_wallet, destination_after)):
        for key in list(wallet):
            if canonical_denomination(key):
                del wallet[key]
        wallet.update({denom: count for denom, count in converted.items() if count > 0})
    return True, "Currency transferred."

def can_afford(wallet, price_in_copper):
    """Mengecek apakah total nilai moneter dalam dompet mencukupi harga"""
    return to_copper(wallet) >= price_in_copper

def consolidate_wallet(wallet):
    """Return compact denominations without changing the wallet total value."""
    return normalize_wallet(wallet)

def make_change_and_deposit(market_wallet, payment, change):
    """
    Memecah / mengonversi koin pada market wallet untuk mendistribusikan uang kembalian
    secara presisi tanpa membuat defisit saldo negatif pada denominasi mana pun.
    Returns: (success: bool, updated_market_wallet: dict)
    """
    w = normalize_wallet(market_wallet)
    p = normalize_wallet(payment)
    c = normalize_wallet(change)

    # Tambahkan pembayaran ke kas market
    for k in CURRENCY_DENOMINATIONS:
        w[k] += p[k]

    c_need = c["Copper"]
    s_need = c["Silver"]
    g_need = c["Gold"]

    # Pecah Silver ke Copper jika koin Copper kas market kurang untuk kembalian
    if w["Copper"] < c_need:
        deficit_c = c_need - w["Copper"]
        s_to_break = (deficit_c + COPPER_PER_SILVER - 1) // COPPER_PER_SILVER
        if w["Silver"] < s_to_break:
            deficit_s = s_to_break - w["Silver"]
            g_to_break = (deficit_s + SILVER_PER_GOLD - 1) // SILVER_PER_GOLD
            if w["Gold"] < g_to_break:
                return False, market_wallet
            w["Gold"] -= g_to_break
            w["Silver"] += g_to_break * SILVER_PER_GOLD
        w["Silver"] -= s_to_break
        w["Copper"] += s_to_break * COPPER_PER_SILVER

    # Pecah Gold ke Silver jika koin Silver kas market kurang untuk kembalian
    if w["Silver"] < s_need:
        deficit_s = s_need - w["Silver"]
        g_to_break = (deficit_s + SILVER_PER_GOLD - 1) // SILVER_PER_GOLD
        if w["Gold"] < g_to_break:
            return False, market_wallet
        w["Gold"] -= g_to_break
        w["Silver"] += g_to_break * SILVER_PER_GOLD

    if w["Gold"] < g_need:
        return False, market_wallet

    # Kurangi kembalian yang diberikan ke customer
    w["Copper"] -= c_need
    w["Silver"] -= s_need
    w["Gold"] -= g_need

    w = consolidate_wallet(w)
    return True, w

def calculate_change_for_payment(payment_dict, price_in_copper):
    """
    Menghitung kembalian untuk pembayaran yang sudah ditentukan secara spesifik.
    Contoh: Customer membayar 5 Copper untuk harga 3 Copper -> Kembalian 2 Copper.
    """
    p = normalize_wallet(payment_dict)
    pay_val = to_copper(p)
    if pay_val < price_in_copper:
        return None
    change_val = pay_val - price_in_copper
    return from_copper(change_val)

def calculate_payment_and_change(customer_funds, price_in_copper, market_funds=None):
    """
    Menghitung kombinasi pembayaran dan kembalian optimal:
    1. Memeriksa dana mandiri household.
    2. Mendukung pembayaran Copper langsung, Silver langsung, Gold langsung, atau kombinasinya.
    3. Mengutamakan pembayaran pas (change = 0) dan meminimalkan uang kembalian / konversi.
    4. Tidak memaksakan konversi ke Silver.
    5. Menghitung kembalian akurat sesuai nilai tukar resmi.
    6. Menegakkan denomination cap (maks 1000).
    7. Nilai moneter tidak pernah tercipta atau musnah (Zero leakage).

    Returns:
        (success: bool, payment_dict: dict, change_dict: dict, message: str)
    """
    cust = normalize_wallet(customer_funds)
    mkt = normalize_wallet(market_funds) if market_funds is not None else {"Copper": 0, "Silver": 0, "Gold": 0}

    total_cust = to_copper(cust)
    if total_cust < price_in_copper:
        return False, None, None, f"Insufficient funds: has {total_cust}c, needed {price_in_copper}c"

    if price_in_copper <= 0:
        return True, {"Copper": 0, "Silver": 0, "Gold": 0}, {"Copper": 0, "Silver": 0, "Gold": 0}, "Zero price"

    candidates = []

    # 1. Direct Copper Payment (Exact)
    if cust["Copper"] >= price_in_copper:
        candidates.append((price_in_copper, 0, {"Copper": price_in_copper, "Silver": 0, "Gold": 0}))

    # 2. Multi-denomination combinations
    max_g = min(cust["Gold"], (price_in_copper // COPPER_PER_GOLD) + 1)
    for g_pay in range(max_g + 1):
        g_val = g_pay * COPPER_PER_GOLD
        rem_g = max(0, price_in_copper - g_val)
        max_s = min(cust["Silver"], (rem_g // COPPER_PER_SILVER) + 1 if rem_g > 0 else 0)

        for s_pay in range(max_s + 1):
            s_val = s_pay * COPPER_PER_SILVER
            rem_s = max(0, price_in_copper - g_val - s_val)

            # Option A: Exact copper remainder
            if rem_s <= cust["Copper"]:
                c_pay = rem_s
                pay_val = g_val + s_val + c_pay
                if pay_val >= price_in_copper:
                    change_val = pay_val - price_in_copper
                    candidates.append((pay_val, change_val, {"Copper": c_pay, "Silver": s_pay, "Gold": g_pay}))

            # Option B: Partial copper remainder
            for c_pay in {0, min(cust["Copper"], rem_s + 1), cust["Copper"]}:
                pay_val = g_val + s_val + c_pay
                if pay_val >= price_in_copper:
                    change_val = pay_val - price_in_copper
                    cand = (pay_val, change_val, {"Copper": c_pay, "Silver": s_pay, "Gold": g_pay})
                    if cand not in candidates:
                        candidates.append(cand)

    # 3. Direct Silver Payment
    needed_silver = (price_in_copper + COPPER_PER_SILVER - 1) // COPPER_PER_SILVER
    if cust["Silver"] >= needed_silver:
        s_val = needed_silver * COPPER_PER_SILVER
        candidates.append((s_val, s_val - price_in_copper, {"Copper": 0, "Silver": needed_silver, "Gold": 0}))

    # 4. Direct Gold Payment
    needed_gold = (price_in_copper + COPPER_PER_GOLD - 1) // COPPER_PER_GOLD
    if cust["Gold"] >= needed_gold:
        g_val = needed_gold * COPPER_PER_GOLD
        candidates.append((g_val, g_val - price_in_copper, {"Copper": 0, "Silver": 0, "Gold": needed_gold}))

    if not candidates:
        return False, None, None, "No valid payment denomination combination found"

    # Evaluasi & ranking kandidat pembayaran
    # 1. change_val terkecil (0 change = EXACT payment paling diutamakan)
    # 2. total coin count dibayar paling minimal
    candidates.sort(key=lambda item: (
        item[1],  # change_val
        item[2]["Gold"] + item[2]["Silver"] + item[2]["Copper"],
    ))

    for pay_val, change_val, payment in candidates:
        change = from_copper(change_val)

        # Cek apakah market dapat memecah koin dan mendistribusikan kembalian
        ok_mkt, post_mkt = make_change_and_deposit(mkt, payment, change)
        if not ok_mkt:
            continue

        # Cek denomination cap customer setelah transaksi
        cust_c = cust["Copper"] - payment["Copper"] + change["Copper"]
        cust_s = cust["Silver"] - payment["Silver"] + change["Silver"]
        cust_g = cust["Gold"] - payment["Gold"] + change["Gold"]

        post_cust = consolidate_wallet({"Copper": cust_c, "Silver": cust_s, "Gold": cust_g})
        if any(v > DENOMINATION_CAP for v in post_cust.values()):
            continue

        # Cek cap market
        if any(v > DENOMINATION_CAP for v in post_mkt.values()):
            continue

        # Verifikasi kekekalan nilai
        if (to_copper(cust) - to_copper(post_cust)) != price_in_copper:
            continue
        if (to_copper(post_mkt) - to_copper(mkt)) != price_in_copper:
            continue

        return True, payment, change, "Valid payment combination found"

    # Fallback: jika kembalian gagal karena limit cap, cari exact payment saja
    for pay_val, change_val, payment in candidates:
        if change_val == 0:
            ok_mkt, post_mkt = make_change_and_deposit(mkt, payment, {"Copper": 0, "Silver": 0, "Gold": 0})
            if ok_mkt and not any(v > DENOMINATION_CAP for v in post_mkt.values()):
                return True, payment, {"Copper": 0, "Silver": 0, "Gold": 0}, "Exact payment matched"

    return False, None, None, "Market cannot provide change without violating currency caps"

def execute_currency_transfer(sender_funds, recipient_funds, payment, change):
    """
    Mentransfer koin antara sender dan recipient secara atomik.
    Mengembalikan (success: bool, new_sender_funds: dict, new_recipient_funds: dict, message: str).
    """
    s = normalize_wallet(sender_funds)
    r = normalize_wallet(recipient_funds)

    p = normalize_wallet(payment)
    c = normalize_wallet(change)

    # Validasi sender memiliki saldo koin payment
    for denom in CURRENCY_DENOMINATIONS:
        if s[denom] < p[denom]:
            return False, sender_funds, recipient_funds, f"Sender lacks {p[denom]} {denom}"

    # Proses pada recipient menggunakan helper change & deposit
    ok_r, new_r = make_change_and_deposit(r, p, c)
    if not ok_r:
        return False, sender_funds, recipient_funds, "Failed to resolve change in recipient funds"

    # Proses pada sender
    new_s = {
        denom: s[denom] - p[denom] + c[denom]
        for denom in CURRENCY_DENOMINATIONS
    }
    new_s = consolidate_wallet(new_s)

    # Update in-place jika dictionary
    if isinstance(sender_funds, dict):
        for k in CURRENCY_DENOMINATIONS:
            sender_funds[k] = new_s[k]
        compact_currency_wallet(sender_funds)
    if isinstance(recipient_funds, dict):
        for k in CURRENCY_DENOMINATIONS:
            recipient_funds[k] = new_r[k]
        compact_currency_wallet(recipient_funds)

    return True, new_s, new_r, "Transfer successful"
