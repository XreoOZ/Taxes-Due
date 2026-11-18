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
