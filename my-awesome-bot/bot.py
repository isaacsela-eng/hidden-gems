#!/usr/bin/env python3
import sys
import json
import math
from collections import deque
from typing import Tuple, Optional, Set, Dict, List

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


class GemTracker:
    def __init__(self, pos: Tuple[int, int], ttl: int = None, confidence: float = 1.0):
        self.pos = pos
        self.ttl = ttl
        self.confidence = confidence
        self.last_seen = 0
        self.estimated = ttl is None


class HiddenGemsBot:
    def __init__(self):
        self.width = 19
        self.height = 19
        self.signal_radius = 10.0
        self.vis_radius = 5
        self.max_ticks = 1200

        self.map = []
        self.x = 0
        self.y = 0
        self.tick = 0

        self.gems: Dict[Tuple[int, int], GemTracker] = {}
        self.collected_gems: Set[Tuple[int, int]] = set()

        self.signal_history: List[Tuple[int, int, float]] = []

        self.current_path: List[str] = []
        self.current_target: Optional[Tuple[int, int]] = None

        self.frontier: Set[Tuple[int, int]] = set()
        self.position_history: List[Tuple[int, int]] = []

        # 🔥 NEW: signal hunting mode
        self.last_real_gem_tick = 0
        self.signal_gradient_memory: List[Tuple[int, int, float]] = []

    # ---------------- MAP ----------------

    def initialize_map(self):
        self.map = [[MapCell.UNKNOWN for _ in range(self.height)]
                    for _ in range(self.width)]

    def update_map(self, walls, floors):
        for w in walls:
            self.map[w[0]][w[1]] = MapCell.WALL
        for f in floors:
            self.map[f[0]][f[1]] = MapCell.FLOOR
        self._update_frontier()

    def _update_frontier(self):
        self.frontier = set()
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

    # ---------------- SIGNAL ----------------

    def signal_to_distance(self, signal: float) -> float:
        if signal <= 0:
            return float('inf')
        signal = min(max(signal, 1e-6), 0.999999)
        value = 1.0 / signal - 1.0
        if value < 0:
            value = 0.0
        return self.signal_radius * math.sqrt(value)

    # ---------------- GEM TRACKING ----------------

    def update_gems(self, visible_gems):
        visible_positions = set()

        for g in visible_gems:
            pos = tuple(g["position"])
            ttl = g["ttl"]
            visible_positions.add(pos)

            # 🔥 real gem found → reset timer
            self.last_real_gem_tick = self.tick

            if pos in self.gems:
                gem = self.gems[pos]
                gem.ttl = ttl
                gem.last_seen = self.tick
                gem.confidence = 1.0
                gem.estimated = False
            else:
                self.gems[pos] = GemTracker(pos, ttl, 1.0)
                self.gems[pos].last_seen = self.tick

        for pos in list(self.gems.keys()):
            gem = self.gems[pos]
            if not gem.estimated and pos not in visible_positions and gem.last_seen < self.tick - 1:
                self.collected_gems.add(pos)
                del self.gems[pos]

    # ---------------- PATHFINDING ----------------

    def bfs(self, start, targets):
        if not targets:
            return []
        queue = deque([(start, [])])
        visited = {start}

        while queue:
            (x, y), path = queue.popleft()
            if (x, y) in targets:
                return path

            for d, (dx, dy) in DIRECTIONS.items():
                nx, ny = x + dx, y + dy
                if (nx, ny) not in visited and self.is_walkable(nx, ny):
                    visited.add((nx, ny))
                    queue.append(((nx, ny), path + [d]))
        return []

    def find_path_to_frontier(self):
        return self.bfs((self.x, self.y), self.frontier)

    # ---------------- SIGNAL HUNT MODE ----------------

    def in_signal_hunt_mode(self):
        return (self.tick - self.last_real_gem_tick) >= 150

    def score_move_signal_only(self, direction, signal_level):
        dx, dy = DIRECTIONS[direction]
        nx, ny = self.x + dx, self.y + dy

        score = 0.0

        # prefer unexplored
        if self.map[nx][ny] == MapCell.UNKNOWN:
            score += 1.5

        # avoid going back
        if self.position_history and (nx, ny) == self.position_history[-1]:
            score -= 2.0

        # 🔥 signal gradient memory
        for px, py, psig in self.signal_gradient_memory:
            if (px, py) == (nx, ny):
                score += (signal_level - psig) * 20

        return score

    # ---------------- MOVE SCORING ----------------

    def score_move(self, direction, signal_level):
        dx, dy = DIRECTIONS[direction]
        nx, ny = self.x + dx, self.y + dy
        score = 0.0

        for pos, gem in self.gems.items():
            if not gem.estimated or gem.confidence > 0.5:
                old_dist = abs(pos[0] - self.x) + abs(pos[1] - self.y)
                new_dist = abs(pos[0] - nx) + abs(pos[1] - ny)
                if new_dist < old_dist:
                    score += 12 if not gem.estimated else gem.confidence * 6

        if self.map[nx][ny] == MapCell.UNKNOWN:
            score += 3
        if (nx, ny) in self.frontier:
            score += 1.5

        if self.position_history and (nx, ny) == self.position_history[-1]:
            score -= 2

        return score

    # ---------------- DECISION LOGIC ----------------

    def decide_move(self, signal_level):
        self.position_history.append((self.x, self.y))
        if len(self.position_history) > 30:
            self.position_history.pop(0)

        # store signal memory
        self.signal_gradient_memory.append((self.x, self.y, signal_level))
        if len(self.signal_gradient_memory) > 20:
            self.signal_gradient_memory.pop(0)

        # immediate visible gem
        for pos, gem in self.gems.items():
            if not gem.estimated:
                if abs(pos[0] - self.x) + abs(pos[1] - self.y) == 1:
                    dx = pos[0] - self.x
                    dy = pos[1] - self.y
                    for d, (mx, my) in DIRECTIONS.items():
                        if (mx, my) == (dx, dy):
                            return d

        # 🔥 SIGNAL HUNT MODE ACTIVATED
        if self.in_signal_hunt_mode():
            moves = [d for d in DIRECTIONS if self.is_walkable(self.x + DIRECTIONS[d][0],
                                                               self.y + DIRECTIONS[d][1])]
            if moves:
                best = max(moves, key=lambda m: self.score_move_signal_only(m, signal_level))
                return best

        # normal gem targeting
        for gem_pos in sorted(self.gems.keys()):
            if gem_pos in self.gems and not self.gems[gem_pos].estimated:
                path = self.bfs((self.x, self.y), {gem_pos})
                if path:
                    return path[0]

        # exploration
        path = self.find_path_to_frontier()
        if path:
            return path[0]

        # fallback scoring
        moves = [d for d in DIRECTIONS if self.is_walkable(self.x + DIRECTIONS[d][0],
                                                           self.y + DIRECTIONS[d][1])]
        if not moves:
            return "WAIT"

        return max(moves, key=lambda m: self.score_move(m, signal_level))

    # ---------------- MAIN LOOP ----------------

    def process_tick(self, data):
        self.tick = data["tick"]
        self.x, self.y = data["bot"]

        self.update_map(data.get("wall", []), data.get("floor", []))
        self.update_gems(data.get("visible_gems", []))

        signal_level = data.get("signal_level", 0.0)

        move = self.decide_move(signal_level)

        print(
            f"T{self.tick} ({self.x},{self.y}) sig={signal_level:.4f} "
            f"mode={'SIG' if self.in_signal_hunt_mode() else 'NORMAL'} move={move}",
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
                config = data.get("config", {})
                bot.width = config.get("width", 19)
                bot.height = config.get("height", 19)
                bot.signal_radius = config.get("signal_radius", 10.0)
                bot.vis_radius = config.get("vis_radius", 5)
                bot.max_ticks = config.get("max_ticks", 1200)
                bot.initialize_map()
                first_tick = False

            move = bot.process_tick(data)
            print(move, flush=True)

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr, flush=True)
            print("WAIT", flush=True)


if __name__ == "__main__":
    main()
