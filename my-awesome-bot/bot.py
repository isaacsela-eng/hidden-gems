#!/usr/bin/env python3
import sys
import json
import math
import heapq
from collections import deque
from typing import Tuple, Dict, Set, List, Optional

DIRECTIONS = {
    'N': (0, -1),
    'S': (0, 1),
    'E': (1, 0),
    'W': (-1, 0)
}


class MapCell:
    UNKNOWN = 0
    WALL = 1
    FLOOR = 2


class GemEstimate:
    def __init__(self, pos: Tuple[int, int], confidence: float):
        self.pos = pos
        self.confidence = confidence
        self.last_update = 0


class HiddenGemsBot:
    def __init__(self):
        self.width = 19
        self.height = 19
        self.signal_radius = 10.0

        self.map = []
        self.last_visit = []

        self.x = 0
        self.y = 0
        self.tick = 0

        self.signal_samples: List[Tuple[int, int, float]] = []

        self.predicted_gems: Dict[Tuple[int, int], GemEstimate] = {}
        self.visible_gems: Set[Tuple[int, int]] = set()

        self.frontier: Set[Tuple[int, int]] = set()
        self.current_target: Optional[Tuple[int, int]] = None
        self.current_path: List[str] = []
        self.target_lock_ticks = 0  # prevents oscillation

    # ---------------- MAP ----------------

    def initialize_map(self):
        self.map = [[MapCell.UNKNOWN for _ in range(self.height)]
                    for _ in range(self.width)]
        self.last_visit = [[-1 for _ in range(self.height)]
                           for _ in range(self.width)]

    def update_map(self, walls, floors):
        for w in walls:
            self.map[w[0]][w[1]] = MapCell.WALL
        for f in floors:
            self.map[f[0]][f[1]] = MapCell.FLOOR
        self.update_frontier()

    def update_frontier(self):
        self.frontier.clear()
        for x in range(self.width):
            for y in range(self.height):
                if self.map[x][y] == MapCell.FLOOR:
                    for dx, dy in DIRECTIONS.values():
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < self.width and 0 <= ny < self.height and self.map[nx][ny] == MapCell.UNKNOWN:
                            self.frontier.add((x, y))
                            break

    def is_walkable(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height and self.map[x][y] != MapCell.WALL

    def explored_ratio(self):
        known = sum(1 for x in range(self.width) for y in range(self.height)
                    if self.map[x][y] != MapCell.UNKNOWN)
        return known / (self.width * self.height)

    # ---------------- SIGNAL ----------------

    def signal_to_distance(self, signal: float) -> float:
        if signal <= 0:
            return float("inf")
        signal = min(max(signal, 1e-6), 0.999999)
        val = 1.0 / signal - 1.0
        if val < 0:
            val = 0
        return self.signal_radius * math.sqrt(val)

    def update_signal_samples(self, signal):
        self.signal_samples.append((self.x, self.y, signal))
        if len(self.signal_samples) > 40:
            self.signal_samples.pop(0)

    def predict_gems(self):
        if len(self.signal_samples) < 6:
            return

        samples = sorted(self.signal_samples, key=lambda s: s[2], reverse=True)[:12]

        for sx, sy, sig in samples:
            dist = self.signal_to_distance(sig)
            if dist == float("inf"):
                continue

            tol = 2.0
            r = int(dist) + 3

            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    x = sx + dx
                    y = sy + dy
                    if not self.is_walkable(x, y):
                        continue

                    d = math.sqrt(dx * dx + dy * dy)
                    if abs(d - dist) <= tol:
                        pos = (x, y)
                        conf = 1.0 - abs(d - dist) / tol

                        if pos not in self.predicted_gems:
                            self.predicted_gems[pos] = GemEstimate(pos, conf)
                        else:
                            self.predicted_gems[pos].confidence = min(
                                1.0, self.predicted_gems[pos].confidence + conf * 0.15
                            )
                        self.predicted_gems[pos].last_update = self.tick

        # decay predictions
        to_del = []
        for pos, g in self.predicted_gems.items():
            g.confidence *= 0.975
            if self.tick - g.last_update > 100 or g.confidence < 0.2:
                to_del.append(pos)
        for pos in to_del:
            del self.predicted_gems[pos]

    # ---------------- PATHFINDING (A*) ----------------

    def heuristic(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def cell_cost(self, x, y):
        # prefer unexplored or long-unvisited cells
        t = self.last_visit[x][y]
        if t == -1:
            return 0.1
        return 1.0 + min(5.0, (self.tick - t) / 50)

    def astar(self, start, goal):
        if start == goal:
            return []

        open_set = [(0, start)]
        came_from = {}
        g_score = {start: 0}

        while open_set:
            _, current = heapq.heappop(open_set)

            if current == goal:
                path = []
                while current != start:
                    prev = came_from[current]
                    dx = current[0] - prev[0]
                    dy = current[1] - prev[1]
                    for d, (mx, my) in DIRECTIONS.items():
                        if (mx, my) == (dx, dy):
                            path.append(d)
                    current = prev
                return path[::-1]

            for d, (dx, dy) in DIRECTIONS.items():
                nx, ny = current[0] + dx, current[1] + dy
                if not self.is_walkable(nx, ny):
                    continue

                cost = g_score[current] + self.cell_cost(nx, ny)
                if (nx, ny) not in g_score or cost < g_score[(nx, ny)]:
                    g_score[(nx, ny)] = cost
                    f = cost + self.heuristic((nx, ny), goal)
                    heapq.heappush(open_set, (f, (nx, ny)))
                    came_from[(nx, ny)] = current

        return []

    # ---------------- TARGET SELECTION ----------------

    def score_frontier(self, p):
        # exploration value
        x, y = p
        unknown_neighbors = 0
        for dx, dy in DIRECTIONS.values():
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height and self.map[nx][ny] == MapCell.UNKNOWN:
                unknown_neighbors += 1
        dist = abs(x - self.x) + abs(y - self.y)
        return unknown_neighbors * 3 - dist * 0.2

    def find_least_recent_cell(self):
        best = None
        best_time = float("inf")

        for x in range(self.width):
            for y in range(self.height):
                if not self.is_walkable(x, y):
                    continue
                t = self.last_visit[x][y]
                if t == -1:
                    return (x, y)
                if t < best_time:
                    best_time = t
                    best = (x, y)

        return best

    def choose_target(self, use_signal: bool):
        if self.visible_gems:
            return min(self.visible_gems, key=lambda p: self.heuristic(p, (self.x, self.y)))

        if use_signal and self.predicted_gems:
            best = max(self.predicted_gems.values(), key=lambda g: g.confidence)
            return best.pos

        if self.frontier:
            return max(self.frontier, key=self.score_frontier)

        return self.find_least_recent_cell()

    # ---------------- MOVE LOGIC ----------------

    def decide_move(self):
        use_signal = self.explored_ratio() > 0.55 or self.tick > 180

        # keep target for a while to avoid oscillation
        if self.current_target is None or self.target_lock_ticks <= 0:
            self.current_target = self.choose_target(use_signal)
            self.current_path = []
            self.target_lock_ticks = 15  # commit to target

        self.target_lock_ticks -= 1

        # recompute path only when needed
        if self.current_target and not self.current_path:
            self.current_path = self.astar((self.x, self.y), self.current_target)

        # unreachable → reset target
        if self.current_target and not self.current_path:
            self.current_target = None
            return self.decide_move()

        # local greedy smoothing (more efficient movement)
        if self.current_path:
            return self.current_path.pop(0)

        return "WAIT"

    # ---------------- TICK ----------------

    def process_tick(self, data):
        self.tick = data["tick"]
        self.x, self.y = data["bot"]

        self.last_visit[self.x][self.y] = self.tick

        self.update_map(data.get("wall", []), data.get("floor", []))
        self.visible_gems = {tuple(g["position"]) for g in data.get("visible_gems", [])}

        signal = data.get("signal_level", 0.0)
        self.update_signal_samples(signal)

        if self.explored_ratio() > 0.55 or self.tick > 180:
            self.predict_gems()

        move = self.decide_move()

        print(
            f"T{self.tick} ({self.x},{self.y}) explored={self.explored_ratio():.2f} "
            f"target={self.current_target}",
            file=sys.stderr,
            flush=True,
        )

        return move


def main():
    bot = HiddenGemsBot()
    first_tick = True

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            data = json.loads(line)

            if first_tick:
                cfg = data.get("config", {})
                bot.width = cfg.get("width", 19)
                bot.height = cfg.get("height", 19)
                bot.signal_radius = cfg.get("signal_radius", 10.0)
                bot.initialize_map()
                first_tick = False

            move = bot.process_tick(data)
            print(move, flush=True)

        except Exception as e:
            print("Error:", e, file=sys.stderr, flush=True)
            print("WAIT", flush=True)


if __name__ == "__main__":
    main()
