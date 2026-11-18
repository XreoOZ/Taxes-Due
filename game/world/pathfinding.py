"""
A* Grid Pathfinding System (Obstacle & Wall Avoidance, Building Doors, Collinear Waypoint Smoothing,
Predetermined Route Lines with Directional Arrows, and Same-Target Claim Prioritization)
"""

import math
import heapq
import time
import pygame
from game.config import (
    TILE_SIZE,
    COLOR_PATH_VILLAGER,
    COLOR_PATH_SERVANT,
    COLOR_PATH_TARGET_RING,
    PATH_LINE_WIDTH,
    PATH_ARROW_SPACING,
    PATH_WAYPOINT_TOLERANCE,
    PATH_SEGMENT_COLLISION_RADIUS,
    PATH_MAX_ASTAR_ITERATIONS,
    PATH_RESERVATION_CLEARANCE,
    PATH_WAIT_RECHECK_INTERVAL,
    PATH_RESERVATION_TIMEOUT
)

def get_tiles_along_segment(p1, p2, tile_size=TILE_SIZE):
    """
    Mengembalikan set koordinat petak (gx, gy) yang dilintasi oleh segmen garis p1 -> p2
    termasuk margin radius karakter untuk mencegah tabrakan fisik.
    """
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    dist = math.hypot(dx, dy)
    tiles = set()
    if dist < 0.001:
        tiles.add((int(math.floor(x1 / tile_size)), int(math.floor(y1 / tile_size))))
        return tiles

    step_size = tile_size * 0.35
    num_steps = max(1, int(math.ceil(dist / step_size)))
    margin = 16.0

    for s in range(num_steps + 1):
        t = s / num_steps
        x = x1 + dx * t
        y = y1 + dy * t
        gx = int(math.floor(x / tile_size))
        gy = int(math.floor(y / tile_size))
        tiles.add((gx, gy))

        frac_x = x - gx * tile_size
        frac_y = y - gy * tile_size
        if frac_x < margin:
            tiles.add((gx - 1, gy))
        elif frac_x > tile_size - margin:
            tiles.add((gx + 1, gy))
        if frac_y < margin:
            tiles.add((gx, gy - 1))
        elif frac_y > tile_size - margin:
            tiles.add((gx, gy + 1))

    return tiles

def ccw(A, B, C):
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

def segments_intersect(p1, p2, p3, p4):
    """
    Memeriksa apakah dua segmen garis (p1, p2) dan (p3, p4) saling bersilangan.
    """
    if (abs(p1[0] - p3[0]) < 1.0 and abs(p1[1] - p3[1]) < 1.0) or \
       (abs(p1[0] - p4[0]) < 1.0 and abs(p1[1] - p4[1]) < 1.0) or \
       (abs(p2[0] - p3[0]) < 1.0 and abs(p2[1] - p3[1]) < 1.0) or \
       (abs(p2[0] - p4[0]) < 1.0 and abs(p2[1] - p4[1]) < 1.0):
        return False
    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)) and (ccw(p1, p2, p3) != ccw(p1, p2, p4))

def dist_point_to_segment(p, a, b):
    px, py = p
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)

def dist_segment_to_segment(p1, p2, p3, p4):
    """
    Menghitung jarak terpendek antara dua segmen garis.
    Mengembalikan 0.0 jika kedua segmen bersilangan.
    """
    if segments_intersect(p1, p2, p3, p4):
        return 0.0
    return min(
        dist_point_to_segment(p1, p3, p4),
        dist_point_to_segment(p2, p3, p4),
        dist_point_to_segment(p3, p1, p2),
        dist_point_to_segment(p4, p1, p2)
    )

class Pathfinder:
    def __init__(self, building_manager=None):
        self.building_manager = building_manager

    def is_segment_clear(self, p1, p2, building_manager=None, radius=PATH_SEGMENT_COLLISION_RADIUS, tile_size=TILE_SIZE, furniture_manager=None, exclude_tile=None):
        """
        Memvalidasi segmen garis antara p1=(x1, y1) dan p2=(x2, y2) terhadap seluruh rect dinding dan perabotan.
        Mengembalikan True jika segmen bebas benturan, False jika menabrak dinding atau rintangan.
        """
        if p1 == p2:
            return True
        bm = building_manager or self.building_manager
        x1, y1 = p1
        x2, y2 = p2
        margin = max(0.0, radius - 4.0)

        if bm:
            all_walls = bm.get_all_wall_rects(tile_size)
            if all_walls:
                # Abaikan benturan jika segmen berada tepat di koridor celah kusen pintu bangunan
                is_door_transit = any(
                    b.is_in_door_threshold(x1, y1, tile_size) and b.is_in_door_threshold(x2, y2, tile_size)
                    for b in getattr(bm, "buildings", []) if getattr(b, "door_pos", None)
                )
                if not is_door_transit:
                    for wr in all_walls:
                        inflated = wr.inflate(margin * 2, margin * 2) if margin > 0 else wr
                        if inflated.clipline(x1, y1, x2, y2):
                            return False

        # Validasi perabotan (Bed, Chest) terpasang - rute tidak boleh memotong menembus ranjang
        if furniture_manager and hasattr(furniture_manager, "get_furniture_rects"):
            furn_rects = furniture_manager.get_furniture_rects(tile_size=tile_size, exclude_tile=exclude_tile)
            for fr in furn_rects:
                if fr.collidepoint(x1, y1) or fr.collidepoint(x2, y2):
                    continue
                if fr.clipline(x1, y1, x2, y2):
                    return False

        return True

    def can_traverse_edge(self, x1, y1, x2, y2, building_manager=None, furniture_manager=None, avoid_tiles=None):
        """
        Mengecek apakah entitas dapat melangkah dari petak (x1, y1) ke petak tetangga (x2, y2).
        Memeriksa dinding bangunan dan memastikan hanya bisa masuk/keluar lewat pintu resmi,
        serta menghindari rintangan dan node yang dihindari (avoid_tiles).
        """
        if avoid_tiles and (x2, y2) in avoid_tiles:
            return False

        bm = building_manager or self.building_manager
        if not bm:
            return True

        # 1. Bangunan solid tanpa pintu (misal: Well 2x2) tidak dapat ditembus sama sekali
        b2 = bm.get_building_at(x2, y2)
        if b2 and (getattr(b2, "is_solid", False) or getattr(b2, "building_type", "") == "well" or not getattr(b2, "door_pos", None)):
            return False

        b1 = bm.get_building_at(x1, y1)

        # 2. Jika kedua petak sama-sama di luar, atau keduanya di dalam bangunan yang sama: bebas lewat
        if b1 == b2:
            return True

        # 3. Transisi dari LUAR ke DALAM bangunan b2
        if b1 is None and b2 is not None:
            if not b2.door_pos:
                return False
            # Hanya boleh menyeberang jika petak tujuan adalah celah pintu
            if (x2, y2) != b2.door_pos:
                return False
            # Arah masuk harus tegak lurus sesuai sisi pintu
            dx = x1 - x2
            dy = y1 - y2
            side = b2.door_side
            if side == "top" and (dx != 0 or dy != -1):
                return False
            elif side == "bottom" and (dx != 0 or dy != 1):
                return False
            elif side == "left" and (dx != -1 or dy != 0):
                return False
            elif side == "right" and (dx != 1 or dy != 0):
                return False
            return True

        # 4. Transisi dari DALAM bangunan b1 ke LUAR
        if b1 is not None and b2 is None:
            if not b1.door_pos:
                return False
            # Hanya boleh menyeberang keluar jika petak asal adalah celah pintu
            if (x1, y1) != b1.door_pos:
                return False
            # Arah keluar harus tegak lurus sesuai sisi pintu
            dx = x2 - x1
            dy = y2 - y1
            side = b1.door_side
            if side == "top" and (dx != 0 or dy != -1):
                return False
            elif side == "bottom" and (dx != 0 or dy != 1):
                return False
            elif side == "left" and (dx != -1 or dy != 0):
                return False
            elif side == "right" and (dx != 1 or dy != 0):
                return False
            return True

        # 5. Tidak boleh menyeberang langsung antar dua bangunan berbeda tanpa lewat luar
        return False

    def find_path(self, start_world, target_world, building_manager=None, tile_size=TILE_SIZE, furniture_manager=None, avoid_tiles=None):
        """
        Mencari rute bebas rintangan dari start_world (x, y) ke target_world (x, y) menggunakan A*.
        Memvalidasi walkability terhadap dinding, pintu, dan rintangan dinamis.
        Mengembalikan daftar waypoint world coordinates [(wx, wy), ...].
        """
        sx, sy = start_world
        tx, ty = target_world

        start_tile = (int(math.floor(sx / tile_size)), int(math.floor(sy / tile_size)))
        target_tile = (int(math.floor(tx / tile_size)), int(math.floor(ty / tile_size)))

        if start_tile == target_tile:
            return [(tx, ty)]

        bm = building_manager or self.building_manager

        # Jika target_tile berada pada sumur (Well), arahkan ke petak kosong terdekat di luarnya untuk interaksi
        b_tar = bm.get_building_at(target_tile[0], target_tile[1]) if bm else None
        if b_tar and getattr(b_tar, "building_type", "") == "well":
            adj_candidates = [
                (target_tile[0] + 1, target_tile[1]), (target_tile[0] - 1, target_tile[1]),
                (target_tile[0], target_tile[1] + 1), (target_tile[0], target_tile[1] - 1)
            ]
            valid_adj = [t for t in adj_candidates if not bm.get_building_at(t[0], t[1])]
            if valid_adj:
                target_tile = min(valid_adj, key=lambda t: abs(t[0] - start_tile[0]) + abs(t[1] - start_tile[1]))
        elif b_tar and (getattr(b_tar, "is_solid", False) or not getattr(b_tar, "door_pos", None)):
            # Bangunan tertutup tanpa pintu: target di dalam tidak dapat dijangkau dari luar
            b_start = bm.get_building_at(start_tile[0], start_tile[1]) if bm else None
            if b_start != b_tar:
                return []

        # Pastikan target_tile dan start_tile tidak diblokir oleh rute sendiri
        filtered_avoid = set(avoid_tiles) if avoid_tiles else set()
        if furniture_manager and hasattr(furniture_manager, "get_occupied_tiles"):
            furn_tiles = furniture_manager.get_occupied_tiles(exclude_tile=target_tile)
            filtered_avoid.update(furn_tiles)

        if target_tile in filtered_avoid:
            filtered_avoid.remove(target_tile)
        if start_tile in filtered_avoid:
            filtered_avoid.remove(start_tile)

        # Algoritma A* Search
        h_start = abs(start_tile[0] - target_tile[0]) + abs(start_tile[1] - target_tile[1])
        open_heap = [(h_start, h_start, start_tile)]
        came_from = {}
        g_score = {start_tile: 0}
        closed_set = set()

        max_iterations = PATH_MAX_ASTAR_ITERATIONS
        iterations = 0
        found = False

        while open_heap and iterations < max_iterations:
            iterations += 1
            f, h, current = heapq.heappop(open_heap)

            if current == target_tile:
                found = True
                break

            if current in closed_set:
                continue
            closed_set.add(current)

            cx, cy = current
            neighbors = [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]

            for n in neighbors:
                if n in closed_set:
                    continue

                if not self.can_traverse_edge(cx, cy, n[0], n[1], bm, furniture_manager=furniture_manager, avoid_tiles=filtered_avoid):
                    continue

                step_cost = 1.0
                tentative_g = g_score[current] + step_cost
                if tentative_g < g_score.get(n, float('inf')):
                    came_from[n] = current
                    g_score[n] = tentative_g
                    h_val = abs(n[0] - target_tile[0]) + abs(n[1] - target_tile[1])
                    f_val = tentative_g + h_val
                    heapq.heappush(open_heap, (f_val, h_val, n))

        if not found:
            # Jika target tidak dapat dijangkau bebas rintangan, kembalikan rute kosong (AI akan menunggu rute dibuka)
            return []

        # Rekonstruksi urutan petak
        path_tiles = [current]
        while current in came_from:
            current = came_from[current]
            path_tiles.append(current)
        path_tiles.reverse()

        # Konversi jalur petak ke waypoint world coordinates
        raw_waypoints = []
        for i in range(1, len(path_tiles)):
            pt = path_tiles[i]
            prev_pt = path_tiles[i - 1]
            b_cur = bm.get_building_at(pt[0], pt[1]) if bm else None
            b_prev = bm.get_building_at(prev_pt[0], prev_pt[1]) if bm else None

            if b_cur and not b_prev and pt == getattr(b_cur, "door_pos", None):
                # Masuk pintu: lewati titik outside pintu, threshold tengah, lalu inside pintu
                d_out = b_cur.get_door_world_outside(tile_size)
                d_thresh = b_cur.get_door_world_threshold(tile_size)
                d_in = b_cur.get_door_world_inside(tile_size)
                raw_waypoints.append(d_out)
                raw_waypoints.append(d_thresh)
                raw_waypoints.append(d_in)
            elif b_prev and not b_cur and prev_pt == getattr(b_prev, "door_pos", None):
                # Keluar pintu: lewati titik inside pintu, threshold tengah, lalu outside pintu
                d_in = b_prev.get_door_world_inside(tile_size)
                d_thresh = b_prev.get_door_world_threshold(tile_size)
                d_out = b_prev.get_door_world_outside(tile_size)
                raw_waypoints.append(d_in)
                raw_waypoints.append(d_thresh)
                raw_waypoints.append(d_out)
            else:
                raw_waypoints.append(((pt[0] + 0.5) * tile_size, (pt[1] + 0.5) * tile_size))

        # Hanya tambahkan target akhir eksak jika path benar-benar berhasil menemukan rute ke target
        if found:
            if not raw_waypoints or raw_waypoints[-1] != (tx, ty):
                raw_waypoints.append((tx, ty))

        # Haluskan waypoint kolinear dengan validasi segment collision
        return self._simplify_waypoints(raw_waypoints, bm=bm, tile_size=tile_size, furniture_manager=furniture_manager, exclude_tile=target_tile)

    def _simplify_waypoints(self, waypoints, bm=None, tile_size=TILE_SIZE, furniture_manager=None, exclude_tile=None):
        """Menyederhanakan waypoint yang berada pada satu garis lurus dengan validasi bebas tabrakan dinding & perabotan"""
        if len(waypoints) <= 2:
            return list(waypoints)

        simplified = [waypoints[0]]
        for i in range(1, len(waypoints) - 1):
            p_prev = simplified[-1]
            p_curr = waypoints[i]
            p_next = waypoints[i + 1]

            # JANGAN sederhanakan waypoint yang merupakan titik lintasan pintu bangunan
            if bm and any(b.is_in_door_threshold(p_curr[0], p_curr[1], tile_size) for b in getattr(bm, "buildings", []) if getattr(b, "door_pos", None)):
                simplified.append(p_curr)
                continue

            # Cek apakah p_curr kolinear (horizontal atau vertikal sejajar) dengan p_prev dan p_next
            dx1 = p_curr[0] - p_prev[0]
            dy1 = p_curr[1] - p_prev[1]
            dx2 = p_next[0] - p_curr[0]
            dy2 = p_next[1] - p_curr[1]

            is_collinear_x = (abs(dx1) < 0.1 and abs(dx2) < 0.1 and (dy1 * dy2 > 0))
            is_collinear_y = (abs(dy1) < 0.1 and abs(dy2) < 0.1 and (dx1 * dx2 > 0))

            if is_collinear_x or is_collinear_y:
                # Validasi apakah garis langsung p_prev ke p_next bebas benturan dinding & perabotan
                if self.is_segment_clear(p_prev, p_next, bm, tile_size=tile_size, furniture_manager=furniture_manager, exclude_tile=exclude_tile):
                    continue

            simplified.append(p_curr)

        # Pastikan segmen langsung ke waypoints[-1] bebas benturan
        if bm and not self.is_segment_clear(simplified[-1], waypoints[-1], bm, tile_size=tile_size, furniture_manager=furniture_manager, exclude_tile=exclude_tile):
            if len(waypoints) >= 2 and waypoints[-2] != simplified[-1]:
                simplified.append(waypoints[-2])

        simplified.append(waypoints[-1])
        return simplified


class PathReservation:
    """
    Menyimpan data reservasi rute aktif untuk satu entitas AI.
    Menyinkronkan segmen garis yang terlihat di layar dengan reservasi ruang pergerakan.
    """
    def __init__(self, entity_id, seq, waypoints, start_pos, target_tile, exclusive_target=False):
        self.entity_id = str(entity_id)
        self.seq = seq
        self.created_at = time.time()
        self.last_update = time.time()
        self.waypoints = list(waypoints)
        self.current_pos = tuple(start_pos)
        self.target_tile = tuple(target_tile) if target_tile else None
        self.exclusive_target = bool(exclusive_target)
        self.path_index = 0
        self.segments = []
        self.reserved_tiles = set()
        self.recompute_geometry()

    def update_progress(self, current_pos, current_path, path_index):
        self.last_update = time.time()
        self.current_pos = tuple(current_pos)
        self.waypoints = list(current_path)
        self.path_index = path_index
        self.recompute_geometry()

    def recompute_geometry(self):
        """
        Menghitung ulang segmen garis aktif dan petak navigasi yang direservasi
        berdasarkan waypoint tersisa (garis yang terlihat di layar).
        """
        remaining_pts = [self.current_pos] + self.waypoints[self.path_index:]
        self.segments = []
        self.reserved_tiles = set()

        cur_gx = int(math.floor(self.current_pos[0] / TILE_SIZE))
        cur_gy = int(math.floor(self.current_pos[1] / TILE_SIZE))
        self.reserved_tiles.add((cur_gx, cur_gy))

        for i in range(len(remaining_pts) - 1):
            p1 = remaining_pts[i]
            p2 = remaining_pts[i + 1]
            self.segments.append((p1, p2))
            seg_tiles = get_tiles_along_segment(p1, p2, TILE_SIZE)
            self.reserved_tiles.update(seg_tiles)


class GlobalPathRegistry:
    """
    Sistem manajemen reservasi rute, deteksi konflik, dan antrean prioritas AI.
    Aturan:
    1. A visible pathfinding line means the path is occupied/reserved by an AI.
    2. Other AI must not use or cross that reserved path.
    3. First-Come, First-Served priority: AI with earlier reservation proceeds; others wait.
    4. Zero hardcode, generic and dynamic for all entities and maps.
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = GlobalPathRegistry()
        return cls._instance

    def __init__(self):
        # reservations: { entity_id: PathReservation }
        self.reservations = {}
        # waiting_queue: [ (entity_id, target_tile, timestamp) ]
        self.waiting_queue = []
        # claims: { (gx, gy): (entity_id, sequence_id, timestamp) } for target exclusivity
        self.claims = {}
        self.seq_counter = 0

    def clear(self):
        self.reservations.clear()
        self.waiting_queue.clear()
        self.claims.clear()
        self.seq_counter = 0

    def reset(self):
        self.clear()

    def clean_stale_reservations(self, timeout=PATH_RESERVATION_TIMEOUT):
        """Menghapus reservasi basi yang tidak pernah diupdate melebihi batas waktu (timeout)"""
        now = time.time()
        stale_eids = [eid for eid, res in self.reservations.items() if (now - res.last_update) > timeout]
        for eid in stale_eids:
            self.release_reservation(eid)
        # Bersihkan juga antrean menunggu yang basi (> 2.0s)
        self.waiting_queue = [w for w in self.waiting_queue if (now - w[2]) < 2.0]

    def get_all_reserved_tiles(self, exclude_entity=None):
        """Mengembalikan gabungan set seluruh petak grid yang direservasi oleh AI lain"""
        self.clean_stale_reservations()
        ex_str = str(exclude_entity) if exclude_entity is not None else None
        res_tiles = set()
        for eid, res in self.reservations.items():
            if ex_str and eid == ex_str:
                continue
            res_tiles.update(res.reserved_tiles)
        return res_tiles

    def get_all_reserved_segments(self, exclude_entity=None):
        """Mengembalikan daftar seluruh segmen garis rute aktif milik AI lain"""
        self.clean_stale_reservations()
        ex_str = str(exclude_entity) if exclude_entity is not None else None
        segs = []
        for eid, res in self.reservations.items():
            if ex_str and eid == ex_str:
                continue
            segs.extend(res.segments)
        return segs

    def _get_door_direction(self, pts, door_pos, bm):
        """Menentukan arah perlintasan pintu ('ENTERING' dari luar ke dalam, atau 'EXITING' dari dalam ke luar)"""
        if not bm or not pts or len(pts) < 2:
            return None
        b = bm.get_building_at(door_pos[0], door_pos[1])
        if not b:
            return None
        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            gx1 = int(math.floor(p1[0] / TILE_SIZE))
            gy1 = int(math.floor(p1[1] / TILE_SIZE))
            gx2 = int(math.floor(p2[0] / TILE_SIZE))
            gy2 = int(math.floor(p2[1] / TILE_SIZE))
            if (gx1, gy1) == door_pos or (gx2, gy2) == door_pos:
                in1 = b.occupies_tile(gx1, gy1)
                in2 = b.occupies_tile(gx2, gy2)
                if not in1 and in2:
                    return "ENTERING"
                elif in1 and not in2:
                    return "EXITING"
        return None

    def find_conflicts(self, entity_id, candidate_waypoints, current_pos, target_tile, clearance=PATH_RESERVATION_CLEARANCE, building_manager=None, exclusive_target=False):
        """
        Mendeteksi konflik rute antara rute kandidat dengan reservasi aktif entitas lain:
        1. Target tile yang sama (Exclusive task/bed claim, hanya jika exclusive_target=True)
        2. Celah pintu sempit (Doorway bottleneck) yang sedang dilewati arah berlawanan (Head-on)
        JALUR TANAH TERBUKA TIDAK DIBLOKIR: banyak AI dapat berjalan beriringan di lahan terbuka.
        """
        eid_str = str(entity_id)
        candidate_pts = [current_pos] + list(candidate_waypoints)
        candidate_segments = [(candidate_pts[i], candidate_pts[i + 1]) for i in range(len(candidate_pts) - 1)]
        candidate_tiles = set()
        for p1, p2 in candidate_segments:
            candidate_tiles.update(get_tiles_along_segment(p1, p2, TILE_SIZE))

        cur_gx = int(math.floor(current_pos[0] / TILE_SIZE))
        cur_gy = int(math.floor(current_pos[1] / TILE_SIZE))

        door_tiles = set()
        bm = building_manager
        if bm:
            for b in getattr(bm, "buildings", []):
                if getattr(b, "door_pos", None):
                    door_tiles.add(b.door_pos)

        conflicts = []
        for other_eid, res in self.reservations.items():
            if other_eid == eid_str:
                continue

            # 1. Target collision (Hanya untuk petak eksklusif, misal ranjang, petak ladang tunggal)
            if target_tile and res.target_tile and target_tile == res.target_tile:
                if exclusive_target or getattr(res, "exclusive_target", False):
                    conflicts.append((other_eid, "TARGET_CONFLICT", res))
                    continue

            # 2. Celah pintu sempit (Doorway bottleneck)
            shared_tiles = candidate_tiles.intersection(res.reserved_tiles)
            shared_doors = shared_tiles.intersection(door_tiles)
            if shared_doors:
                door = next(iter(shared_doors))
                my_dir = self._get_door_direction(candidate_pts, door, bm)
                other_dir = self._get_door_direction(res.waypoints, door, bm)
                # Jika berpapasan arah berlawanan di celah kusen pintu yang sama (head-on collision):
                if my_dir and other_dir and my_dir != other_dir:
                    conflicts.append((other_eid, "DOORWAY_CONFLICT", res))
                    continue
                # Jika entitas lain sudah sangat dekat/sedang melangkah di kusen pintu:
                d_cx = (door[0] + 0.5) * TILE_SIZE
                d_cy = (door[1] + 0.5) * TILE_SIZE
                if math.hypot(res.current_pos[0] - d_cx, res.current_pos[1] - d_cy) < 28.0 and \
                   math.hypot(current_pos[0] - d_cx, current_pos[1] - d_cy) < 28.0:
                    conflicts.append((other_eid, "DOORWAY_THRESHOLD_JAM", res))
                    continue

        return conflicts

    def request_path_reservation(self, entity_id, waypoints, current_pos, target_tile, building_manager=None, exclusive_target=False):
        """
        Meminta reservasi rute secara atomik dengan First-Come, First-Served priority.
        Mengembalikan (True, reservation) jika berhasil, atau (False, conflicts) jika gagal.
        """
        eid_str = str(entity_id)
        self.clean_stale_reservations()

        # Bersihkan entri lama milik diri sendiri dari antrean sebelum mengevaluasi antrean
        self.waiting_queue = [w for w in self.waiting_queue if w[0] != eid_str]

        # Prioritas antrean menunggu: jika ada entitas lain yang mendahului dalam antrean menuju petak sama
        if exclusive_target and self.waiting_queue:
            head_eid, head_target, _ = self.waiting_queue[0]
            if head_eid != eid_str and head_target == target_tile:
                return False, [("QUEUE_PRIORITY", head_eid)]

        conflicts = self.find_conflicts(eid_str, waypoints, current_pos, target_tile, building_manager=building_manager, exclusive_target=exclusive_target)
        if conflicts:
            if exclusive_target:
                self.register_waiting(eid_str, target_tile)
            return False, conflicts

        # Tidak ada konflik! Daftarkan reservasi baru
        self.seq_counter += 1
        res = PathReservation(eid_str, self.seq_counter, waypoints, current_pos, target_tile, exclusive_target=exclusive_target)
        self.reservations[eid_str] = res

        # Hapus dari antrean menunggu jika sebelumnya sedang menunggu
        self.waiting_queue = [w for w in self.waiting_queue if w[0] != eid_str]

        # Juga catat claim target untuk kompatibilitas jika eksklusif
        if target_tile and exclusive_target:
            self.register_claim(eid_str, target_tile)

        return True, res

    def update_entity_progress(self, entity_id, current_pos, current_path, path_index):
        """Memperbarui posisi entitas dan menyusutkan segmen yang telah dilewati"""
        eid_str = str(entity_id)
        if eid_str in self.reservations:
            self.reservations[eid_str].update_progress(current_pos, current_path, path_index)

    def release_reservation(self, entity_id):
        """Melepaskan reservasi rute ketika entitas sampai di tujuan atau membatalkan gerakan"""
        eid_str = str(entity_id)
        if eid_str in self.reservations:
            res = self.reservations.pop(eid_str)
            if res.target_tile:
                self.release_claim(eid_str, res.target_tile)
        else:
            self.release_claim(eid_str)
        self.waiting_queue = [w for w in self.waiting_queue if w[0] != eid_str]

    def register_waiting(self, entity_id, target_tile=None):
        """Mendaftarkan entitas ke antrean menunggu dengan timestamp kedatangan (FIFO)"""
        eid_str = str(entity_id)
        for w in self.waiting_queue:
            if w[0] == eid_str:
                return
        self.waiting_queue.append((eid_str, target_tile, time.time()))

    def is_path_blocked_for(self, entity_id, start_pos, target_pos):
        """
        Cepat mengecek apakah target_tile atau jalur langsung saat ini masih direservasi oleh AI lain.
        Digunakan oleh waiting AI untuk bangun lebih cepat begitu jalur bebas.
        """
        eid_str = str(entity_id)
        tgt_gx = int(math.floor(target_pos[0] / TILE_SIZE))
        tgt_gy = int(math.floor(target_pos[1] / TILE_SIZE))
        for other_eid, res in self.reservations.items():
            if other_eid == eid_str:
                continue
            if getattr(res, "exclusive_target", False) and (res.target_tile == (tgt_gx, tgt_gy) or (tgt_gx, tgt_gy) in res.reserved_tiles):
                return True
        return False

    def register_claim(self, entity_id, target_tile):
        """Mendaftarkan target petak tujuan. Mengembalikan sequence number (urutan kemunculan garis)."""
        if not target_tile or not entity_id:
            return 0
        eid_str = str(entity_id)
        if target_tile not in self.claims:
            self.claims[target_tile] = []

        for claimant, seq, _ in self.claims[target_tile]:
            if claimant == eid_str:
                return seq

        self.seq_counter += 1
        self.claims[target_tile].append((eid_str, self.seq_counter, time.time()))
        return self.seq_counter

    def release_claim(self, entity_id, target_tile=None):
        """Melepas klaim target petak saat tugas selesai atau dibatalkan"""
        eid_str = str(entity_id)
        if target_tile:
            if target_tile in self.claims:
                self.claims[target_tile] = [c for c in self.claims[target_tile] if c[0] != eid_str]
                if not self.claims[target_tile]:
                    del self.claims[target_tile]
        else:
            for t in list(self.claims.keys()):
                self.claims[t] = [c for c in self.claims[t] if c[0] != eid_str]
                if not self.claims[t]:
                    del self.claims[t]

    def has_priority(self, entity_id, target_tile, my_seq, exclusive_target=True):
        """Memeriksa apakah entity memiliki prioritas (garisnya muncul lebih awal dari entitas lain)."""
        if not exclusive_target:
            return True
        if not target_tile or target_tile not in self.claims or not self.claims[target_tile]:
            return True
        first_claimant, min_seq, _ = min(self.claims[target_tile], key=lambda c: c[1])
        if first_claimant == str(entity_id):
            return True
        return my_seq <= min_seq


def draw_ai_paths(surface, camera, villagers=None, servants=None, show_lines=True):
    """
    Merender jalur garis predetermined pathfinding lengkap dengan panah penunjuk arah 
    dan target destination reticle. Sinkron 100% dengan reservasi rute GlobalPathRegistry.
    Dapat diaktifkan / dimatikan lewat tombol ON/OFF HUD.
    """
    if not show_lines:
        return

    all_actors = []
    if villagers:
        for v in villagers:
            all_actors.append((v, COLOR_PATH_VILLAGER, f"{v.first_name} [{getattr(v, 'task', 'MOVE')}]"))
    if servants:
        for s in servants:
            all_actors.append((s, COLOR_PATH_SERVANT, f"Servant [{getattr(s, 'state', 'MOVE')}]"))

    font_tag = pygame.font.SysFont("Segoe UI", 10, bold=True)

    for actor, color, label in all_actors:
        waypoints = getattr(actor, "current_path", None)
        path_idx = getattr(actor, "path_index", 0)
        is_waiting = getattr(actor, "is_waiting_for_path", False)
        is_idle = (getattr(actor, "state", "") == "IDLE" or
                   getattr(actor, "task", "") in ("IDLE", "LEISURE") or
                   not getattr(actor, "is_alive", True))

        # Jika sedang menunggu jalur dibebaskan oleh AI lain, tampilkan tag [WAITING ROUTE]
        # Hanya untuk pekerja aktif yang sedang menunggu rute, bukan karakter santai/idle
        if is_waiting and not is_idle and (not waypoints or path_idx >= len(waypoints)):
            screen_pos = camera.world_to_screen(actor.x, actor.y)
            wait_tag = f"{getattr(actor, 'first_name', 'Servant')} [WAITING ROUTE]"
            tag_surf = font_tag.render(wait_tag, True, (255, 230, 120))
            tag_w = tag_surf.get_width() + 8
            tag_h = 16
            tag_bg = pygame.Rect(int(screen_pos[0] - tag_w // 2), int(screen_pos[1] - 28), tag_w, tag_h)
            pygame.draw.rect(surface, (15, 23, 42, 220), tag_bg, border_radius=4)
            pygame.draw.rect(surface, (234, 179, 8), tag_bg, width=1, border_radius=4)
            surface.blit(tag_surf, (tag_bg.x + 4, tag_bg.y + 1))
            continue

        if not waypoints or path_idx >= len(waypoints):
            continue

        # Titik-titik rute: dari posisi karakter saat ini ke waypoint yang tersisa (persis reservasi aktif)
        points = [(actor.x, actor.y)] + waypoints[path_idx:]
        if len(points) < 2:
            continue

        screen_pts = [camera.world_to_screen(px, py) for px, py in points]

        # 1. Gambar garis rute predetermined berkesinambungan
        if len(screen_pts) >= 2:
            pygame.draw.lines(surface, color, False, screen_pts, PATH_LINE_WIDTH)

        # 2. Gambar panah penunjuk arah sepanjang segmen garis
        for i in range(len(screen_pts) - 1):
            p1 = screen_pts[i]
            p2 = screen_pts[i + 1]
            seg_dx = p2[0] - p1[0]
            seg_dy = p2[1] - p1[1]
            seg_len = math.hypot(seg_dx, seg_dy)
            if seg_len < 16.0:
                continue

            ux = seg_dx / seg_len
            uy = seg_dy / seg_len
            nx = -uy
            ny = ux

            arrow_spacing = PATH_ARROW_SPACING
            num_arrows = max(1, int(seg_len // arrow_spacing))
            for a_idx in range(1, num_arrows + 1):
                dist_on_seg = (a_idx - 0.5) * (seg_len / num_arrows)
                ax = p1[0] + ux * dist_on_seg
                ay = p1[1] + uy * dist_on_seg

                tip = (ax + ux * 6, ay + uy * 6)
                left_barb = (ax - ux * 5 + nx * 5, ay - uy * 5 + ny * 5)
                right_barb = (ax - ux * 5 - nx * 5, ay - uy * 5 - ny * 5)
                center_notch = (ax - ux * 2, ay - uy * 2)

                pygame.draw.polygon(surface, color, [tip, left_barb, center_notch, right_barb])

        # 3. Gambar Reticle / Target Pin di titik tujuan akhir
        target_s = screen_pts[-1]
        pygame.draw.circle(surface, COLOR_PATH_TARGET_RING, (int(target_s[0]), int(target_s[1])), 8, width=2)
        pygame.draw.circle(surface, (255, 255, 255), (int(target_s[0]), int(target_s[1])), 3)

        # Label tag kecil di atas target
        tag_surf = font_tag.render(label, True, (255, 255, 255))
        tag_w = tag_surf.get_width() + 8
        tag_h = 16
        tag_bg = pygame.Rect(int(target_s[0] - tag_w // 2), int(target_s[1] - 24), tag_w, tag_h)
        pygame.draw.rect(surface, (15, 23, 42, 220), tag_bg, border_radius=4)
        pygame.draw.rect(surface, color, tag_bg, width=1, border_radius=4)
        surface.blit(tag_surf, (tag_bg.x + 4, tag_bg.y + 1))

