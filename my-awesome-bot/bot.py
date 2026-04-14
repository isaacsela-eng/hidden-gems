#!/usr/bin/env python3
import sys, json
from collections import deque
import random

# --------------------------- GLOBAL STATE -----------------------------
first_tick = True
tick_counter = 0

known_floor = set()
known_walls = set()
known_gems = {}  # pos -> ttl

last_visit_tile = {}
last_visit_area = {}

area_map = {}      # tile -> area_id
areas = {}         # area_id -> set(tiles)
next_area_id = 1

W = H = 0
map_changed = False

# --------------------------- HELPERS -----------------------------
def neighbors(p):
    x, y = p
    return [(x-1,y), (x+1,y), (x,y-1), (x,y+1)]

def bfs_from(bot, walkable):
    queue = deque([bot])
    seen = {bot}
    prev = {}
    while queue:
        cur = queue.popleft()
        for n in neighbors(cur):
            if n in walkable and n not in seen:
                seen.add(n)
                prev[n] = cur
                queue.append(n)
    return seen, prev

def reconstruct_path(prev, start, target):
    if target == start:
        return start
    if target not in prev:
        return None
    cur = target
    while prev.get(cur, start) != start:
        cur = prev[cur]
    return cur

def move_from_to(a, b):
    ax, ay = a; bx, by = b
    if bx == ax+1: return "E"
    if bx == ax-1: return "W"
    if by == ay+1: return "S"
    if by == ay-1: return "N"
    return "WAIT"

# --------------------------- AREA RECONSTRUCTION -----------------------------
def rebuild_areas():
    global next_area_id, areas, area_map
    areas = {}
    area_map = {}
    next_area_id = 1
    remaining = set(known_floor)
    while remaining:
        start = remaining.pop()
        aid = next_area_id
        next_area_id += 1
        queue = deque([start])
        areas[aid] = {start}
        area_map[start] = aid
        while queue:
            cur = queue.popleft()
            for n in neighbors(cur):
                if n in remaining:
                    remaining.remove(n)
                    queue.append(n)
                    areas[aid].add(n)
                    area_map[n] = aid

# --------------------------- FRONTIER WEIGHT -----------------------------
def frontier_weight(tile):
    """Tiles mit mehr unbesuchten Nachbarn haben höhere Priorität"""
    weight = 0
    for n in neighbors(tile):
        if n not in known_floor and n not in known_walls:
            weight += 1
    # Berücksichtige letzten Besuch (älter = besser)
    weight -= last_visit_tile.get(tile, 0) / 1000.0
    return -weight  # min() wird verwendet, also invertieren

# --------------------------- TARGET SELECTION -----------------------------
def choose_target(bot, reachable):
    # Diamanten auf Bot-Tile entfernen
    if bot in known_gems:
        del known_gems[bot]

    # Direkt benachbarte Diamanten priorisieren
    for g in known_gems:
        if abs(bot[0]-g[0]) + abs(bot[1]-g[1]) == 1:
            return g

    # Erreichbare Diamanten
    gems_in_reach = [g for g in known_gems if g in reachable]
    if gems_in_reach:
        return min(gems_in_reach, key=lambda g: abs(bot[0]-g[0]) + abs(bot[1]-g[1]))
    if known_gems:
        return min(known_gems.keys(), key=lambda g: abs(bot[0]-g[0]) + abs(bot[1]-g[1]))

    # Frontier-basiertes Erkunden
    area_frontier = {}
    for aid, tiles in areas.items():
        fr = []
        for t in tiles:
            for n in neighbors(t):
                if n not in known_floor and n not in known_walls and 0 <= n[0] < W and 0 <= n[1] < H:
                    fr.append(t)
                    break
        area_frontier[aid] = fr

    bot_area = area_map.get(bot, None)
    if bot_area and area_frontier[bot_area]:
        candidates = [f for f in area_frontier[bot_area] if f in reachable]
        if candidates:
            return min(candidates, key=frontier_weight)

    # Andere offene Bereiche
    open_areas = [aid for aid in areas if area_frontier[aid]]
    if open_areas:
        target_area = min(open_areas, key=lambda aid: last_visit_area.get(aid, -1))
        candidates = [t for t in areas[target_area] if t in reachable]
        if candidates:
            return min(candidates, key=frontier_weight)

    # Fallback: nächstgelegener erreichbarer Tile
    if reachable:
        return min(reachable, key=lambda t: last_visit_tile.get(t, -1))

    return bot

# --------------------------- MAIN LOOP -----------------------------
for line in sys.stdin:
    data = json.loads(line)
    tick_counter += 1

    if first_tick:
        cfg = data["config"]
        W, H = cfg["width"], cfg["height"]
        first_tick = False

    bot = tuple(data["bot"])

    # Map Update
    floor_now = set(map(tuple, data["floor"]))
    wall_now = set(map(tuple, data["wall"]))
    gems_now = data["visible_gems"]

    if floor_now - known_floor or wall_now - known_walls:
        map_changed = True

    known_floor.update(floor_now)
    known_walls.update(wall_now)

    # Persistent Gem Memory
    for gpos in list(known_gems.keys()):
        known_gems[gpos] -= 1
        if known_gems[gpos] <= 0:
            del known_gems[gpos]

    for g in gems_now:
        known_gems[tuple(g["position"])] = g["ttl"]

    # Visits
    last_visit_tile[bot] = tick_counter

    if map_changed:
        rebuild_areas()
        map_changed = False

    bot_area = area_map.get(bot, None)
    if bot_area:
        last_visit_area[bot_area] = tick_counter

    # BFS für Reachability
    walkable = known_floor - known_walls
    reachable, prev = bfs_from(bot, walkable)

    # Ziel wählen
    target = choose_target(bot, reachable)

    # Nächster Schritt
    nxt = reconstruct_path(prev, bot, target)
    if nxt is None or nxt == bot:
        print("WAIT", flush=True)
        continue

    move = move_from_to(bot, nxt)
    print(move, flush=True)
#das funktioniert nicht
