# Taxes-Due (Village Building Game Prototype)

Prototipe awal game desktop *Village Building* berbasis **Python & Pygame** (dipersiapkan untuk nanti di-compile ke `.exe`).

## Struktur Proyek
```
Taxes-Due/
├── main.py            # Entry point & game loop utama
├── run_game.bat       # Launcher cepat (double click untuk main)
└── game/
    ├── config.py      # Pengaturan window, resolusi, FPS, dan warna
    ├── player.py      # Entitas karakter dummy (lingkaran, WASD, arah hadap, bobbing)
    ├── camera.py      # Smooth 2D Camera follow
    └── world.py       # Grid desa & area Town Center (0, 0)
```

## Kontrol
- **W, A, S, D** atau **Tombol Panah**: Menggerakkan karakter
- **Close Window**: Keluar dari game

## Cara Menjalankan
Cukup jalankan:
```bash
python main.py
```
Atau klik ganda `run_game.bat`.
