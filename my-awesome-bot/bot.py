#!/usr/bin/env python3
import sys, json, math, random, heapq

sys.stdout.flush()

# ------------------------------
# Constants & Directions
# ------------------------------
UNKNOWN = 0
WALL = 1
FLOOR = 2

DIRS = {
    "N": (0, -1),
    "S": (0, 1),
    "W": (-1, 0),
    "E": (1, 0),
}

# ------------------------------
# Global Variables
# ------------------------------
grid = None
signal_map = None
visit_count = {}
known_gems = {}  # (x,y) -> ttl
width = height = None
first_tick = True
last_pos = None
last_signal = None

# ------------------------------
# Helper Functions
# ------------------------------
def heuristic(a, b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1])

def astar(start, goals):
    open_set = []
    heapq.heappush(open_set, (0, start))
    came_from = {start: None}
    g_score = {start: 0}
    goals_set = set(goals)
    while open_set:
        _, current = heapq.heappop(open_set)
        if current in goals_set:
            path = []
            while current != start:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path
        x, y = current
        for dx, dy in DIRS.values():
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                if grid[ny][nx] == WALL:
                    continue
                neighbor = (nx, ny)
                tentative_g = g_score[current] + 1 + visit_count.get(neighbor, 0)*0.1
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + min(heuristic(neighbor, g) for g in goals)
                    heapq.heappush(open_set,(f_score, neighbor))
                    came_from[neighbor] = current
    return []

def neighbors(x, y):
    for d, (dx, dy) in DIRS.items():
        nx, ny = x+dx, y+dy
        if 0 <= nx < width and 0 <= ny < height:
            yield d, nx, ny

def get_signal_vector(bx, by):
    vx, vy = 0.0, 0.0
    for d, nx, ny in neighbors(bx, by):
        if grid[ny][nx] != WALL:
            diff = signal_map[ny][nx] - signal_map[by][bx]
            dx, dy = nx-bx, ny-by
            vx += dx*diff
            vy += dy*diff
    if last_pos is not None and last_signal is not None:
        lx, ly = last_pos
        ds = last_signal
        vx += (bx-lx)*(signal_map[by][bx]-ds)
        vy += (by-ly)*(signal_map[by][bx]-ds)
    length = math.hypot(vx, vy)
    if length>0:
        return vx/length, vy/length
    return 0, 0

# ------------------------------
# Main Loop
# ------------------------------
for line in sys.stdin:
    data = json.loads(line)

    if first_tick:
        cfg = data["config"]
        width = cfg["width"]
        height = cfg["height"]
        grid = [[UNKNOWN for _ in range(width)] for _ in range(height)]
        signal_map = [[0.0 for _ in range(width)] for _ in range(height)]
        first_tick=False

    bx, by = data["bot"]
    signal = data.get("signal",0.0)

    # ------------------------------
    # Update map
    # ------------------------------
    for x, y in data.get("wall", []):
        grid[y][x] = WALL
    for x, y in data.get("floor", []):
        grid[y][x] = FLOOR

    # ------------------------------
    # Update gem memory
    # ------------------------------
    visible = data.get("visible_gems", [])
    for g in visible:
        gx, gy = g["position"]
        ttl = g.get("ttl",100)
        known_gems[(gx, gy)] = ttl

    # Decay gem TTL
    for pos in list(known_gems.keys()):
        known_gems[pos] -= 1
        if known_gems[pos] <= 0:
            del known_gems[pos]

    # ------------------------------
    # Update signal heatmap
    # ------------------------------
    signal_map[by][bx] = max(signal_map[by][bx], signal)

    best_move = None

    # ------------------------------
    # 1️⃣ IMMEDIATE GEM COLLECTION
    # ------------------------------
    if visible:
        # prioritize closest visible gem
        target = min([tuple(g["position"]) for g in visible], key=lambda p: heuristic(p,(bx,by)))
        path = astar((bx,by), [target])
        if path:
            nx, ny = path[0]
            for d, (dx, dy) in DIRS.items():
                if bx+dx==nx and by+dy==ny:
                    best_move = d

    # ------------------------------
    # 2️⃣ KNOWN GEM MEMORY
    # ------------------------------
    if best_move is None and known_gems:
        target = min(known_gems.keys(), key=lambda p: heuristic(p,(bx,by)))
        path = astar((bx,by), [target])
        if path:
            nx, ny = path[0]
            for d, (dx, dy) in DIRS.items():
                if bx+dx==nx and by+dy==ny:
                    best_move = d

    # ------------------------------
    # 3️⃣ SIGNAL PREDICTION
    # ------------------------------
    if best_move is None:
        vx, vy = get_signal_vector(bx, by)
        best_score = -1e9
        for d, nx, ny in neighbors(bx, by):
            if grid[ny][nx]==WALL: continue
            dx, dy = nx-bx, ny-by
            align = dx*vx + dy*vy
            score = align*2.0 + signal_map[ny][nx]*1.5
            if grid[ny][nx]==UNKNOWN: score+=0.6
            score -= visit_count.get((nx,ny),0)*0.15
            score += random.random()*0.02
            if score>best_score:
                best_score = score
                best_move = d

    # ------------------------------
    # 4️⃣ EXPLORATION
    # ------------------------------
    if best_move is None or best_score<0.05:
        frontiers = set()
        for y in range(height):
            for x in range(width):
                if grid[y][x]==FLOOR:
                    for _, nx, ny in neighbors(x,y):
                        if grid[ny][nx]==UNKNOWN:
                            frontiers.add((x,y))
        if frontiers:
            path = astar((bx,by), frontiers)
            if path:
                nx, ny = path[0]
                for d,(dx,dy) in DIRS.items():
                    if bx+dx==nx and by+dy==ny:
                        best_move = d

    # ------------------------------
    # 5️⃣ POST-EXPLORATION (historic signals)
    # ------------------------------
    if best_move is None:
        max_signal = -1
        best_tile = None
        for y in range(height):
            for x in range(width):
                if grid[y][x]!=WALL and signal_map[y][x]>max_signal:
                    max_signal = signal_map[y][x]
                    best_tile = (x,y)
        if best_tile:
            path = astar((bx,by), [best_tile])
            if path:
                nx, ny = path[0]
                for d,(dx,dy) in DIRS.items():
                    if bx+dx==nx and by+dy==ny:
                        best_move = d

    # ------------------------------
    # fallback random move
    # ------------------------------
    if best_move is None:
        best_move = random.choice(list(DIRS.keys()))

    visit_count[(bx,by)] = visit_count.get((bx,by),0)+1
    last_pos = (bx,by)
    last_signal = signal

    print(best_move)
    sys.stdout.flush()
