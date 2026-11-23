# Project Rules & Architecture Guidelines

Terapkan aturan arsitektur berikut dalam setiap kodingan yang kamu buat di proyek ini:

## 1. MODULAR & PLUG-AND-PLAY
- Pisahkan sistem berdasarkan fungsinya (misal: `player.py`, `camera.py`, `world.py`, `menu.py`, `config.py`).
- Setiap modul harus berupa class/komponen independen yang bisa dicopot, diganti, atau dimatikan tanpa membuat modul lain error.
- Jangan gunakan variabel global untuk saling bertukar data antarmodul; gunakan parameter atau return value.
- Hindari circular import.

## 2. ZERO HARDCODE & CONFIG-DRIVEN
- DILARANG menggunakan "magic numbers" (angka koordinat mati, speed, warna, ukuran statis di dalam fungsi logika).
- Semua parameter dinamis, nilai default, dan konstanta WAJIB masuk ke file konfigurasi (`game/config.py`) atau dictionary data yang mudah diedit.
- Posisi UI dan render harus selalu dihitung secara dinamis (relatif terhadap ukuran layar/viewport), bukan koordinat absolut kaku.

## 3. LEAN CODE (AGILE & FAST)
- Jaga agar setiap file tetap ramping (fokus pada 1 tanggung jawab / Single Responsibility Principle). Jangan pernah menumpuk semua logika di satu file besar.
- Jangan membuat kode over-engineered atau menambahkan fitur yang tidak diminta ("Jangan ngide").
- Bangun fitur secara minimalis, bersih, teruji, tapi siap di-extend kapan saja.

## 4. UNIVERSAL TRANSACTION PRIMITIVES (Wajib Dipakai)

Semua pertukaran uang/barang antar-entity WAJIB lewat `game/systems/economy/transactions.py`:

- `collect_coins(carrier, family_id, amount_copper, ...)` — ambil koin ke kantong carrier. Sumber: chest (harus ≤3 tile), ground coin stacks (≤3 tile), pocket member (kedua pihak harus di dalam permit household). Jangan pernah drain wallet member/chest dari jarak jauh.
- `pay_coins(sender, recipient_wallet, amount_copper)` — bayar exact value dengan denominasi asli + kembalian (pakai `calculate_payment_and_change`/`execute_currency_transfer`).
- `query_stock()` / `query_material_stock()` / `household_coin_total_copper()` — cek stok household di SEMUA sumber fisik (chest + stacks + pockets), read-only.
- `deliver_goods(carrier, family_id, items, ...)` — serahkan barang: chest keluarga, atau owner-tagged loose stack di tile permit household (fallback chestless). Jangan drop di tile luar permit.

Aturan: uang = koin fisik berdenominasi yang dipindahkan saat carrier berada di lokasi sumber. Tidak ada "abstract wallet" transfer jarak jauh, tidak ada rewrite total wallet, tidak ada pembelian remote tanpa villager berjalan ke market. Wallet kanonik untuk villager/chest = `inventory` (`villager.currency`/`chest.currency` hanyalah shadow legacy — lipat ke inventory, jangan tulis ke dua-duanya).
