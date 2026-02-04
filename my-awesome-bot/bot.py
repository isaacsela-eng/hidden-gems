gpt v.2.1

#!/usr/bin/env python3
import sys, json, math, heapq, random
from collections import deque

UNKNOWN_CELL = 0
WALL_CELL = 1
FLOOR_CELL = 2

DIRECTION_OFFSETS = {
    "N": (0, -1),
    "S": (0, 1),
    "W": (-1, 0),
    "E": (1, 0),
}

def manhattan_distance(from_position, to_position):
    return abs(from_position[0] - to_position[0]) + abs(from_position[1] - to_position[1])

class CaveExplorationBot:
    def __init__(self):
        self.known_map = {}
        self.recent_positions = deque(maxlen=20)

    def remember_world(self, game_state):
        bot_position = tuple(game_state["bot"])

        for wall_x, wall_y in game_state.get("wall", []):
            self.known_map[(wall_x, wall_y)] = WALL_CELL

        for floor_x, floor_y in game_state.get("floor", []):
            self.known_map.setdefault((floor_x, floor_y), FLOOR_CELL)

        self.known_map[bot_position] = FLOOR_CELL
        self.recent_positions.append(bot_position)

        return bot_position

    def get_walkable_positions_around(self, position):
        for move_x, move_y in DIRECTION_OFFSETS.values():
            next_position = (position[0] + move_x, position[1] + move_y)
            if self.known_map.get(next_position, UNKNOWN_CELL) != WALL_CELL:
                yield next_position

    def find_path_using_a_star(self, start_position, target_position):
        if start_position == target_position:
            return []

        priority_queue = [(0, start_position)]
        previous_position = {start_position: None}
        travel_cost = {start_position: 0}

        while priority_queue:
            _, current_position = heapq.heappop(priority_queue)

            if current_position == target_position:
                break

            for neighbor_position in self.get_walkable_positions_around(current_position):
                new_cost = travel_cost[current_position] + 1

                if neighbor_position not in travel_cost or new_cost < travel_cost[neighbor_position]:
                    travel_cost[neighbor_position] = new_cost
                    estimated_total_cost = new_cost + manhattan_distance(neighbor_position, target_position)
                    heapq.heappush(priority_queue, (estimated_total_cost, neighbor_position))
                    previous_position[neighbor_position] = current_position

        if target_position not in previous_position:
            return None

        path = []
        current_position = target_position
        while current_position != start_position:
            path.append(current_position)
            current_position = previous_position[current_position]
        path.reverse()

        return path

    def find_positions_next_to_unknown_area(self):
        frontier_positions = []

        for (x, y), cell_type in self.known_map.items():
            if cell_type == FLOOR_CELL:
                for move_x, move_y in DIRECTION_OFFSETS.values():
                    if self.known_map.get((x + move_x, y + move_y), UNKNOWN_CELL) == UNKNOWN_CELL:
                        frontier_positions.append((x, y))
                        break

        return frontier_positions

    def gaussian_gem_signal(self, position, visible_gems, sigma=3.0):
        signal_strength = 0.0

        for gem in visible_gems:
            gem_x, gem_y = gem["position"]
            distance = manhattan_distance(position, (gem_x, gem_y))
            signal_strength += math.exp(-(distance ** 2) / (2 * sigma ** 2))

        return signal_strength

    def choose_random_known_floor(self, current_position):
        possible_positions = [
            pos for pos, cell_type in self.known_map.items()
            if cell_type == FLOOR_CELL and pos not in self.recent_positions
        ]
        return random.choice(possible_positions) if possible_positions else current_position

    def choose_target_position(self, bot_position, visible_gems):
        if visible_gems:
            best_gem = max(visible_gems, key=lambda gem: gem["ttl"])
            return tuple(best_gem["position"])

        frontier_positions = self.find_positions_next_to_unknown_area()
        if frontier_positions:
            return min(frontier_positions, key=lambda pos: manhattan_distance(bot_position, pos))

        return self.choose_random_known_floor(bot_position)

    def decide_direction(self, bot_position, target_position, visible_gems):
        path_to_target = self.find_path_using_a_star(bot_position, target_position)

        if path_to_target:
            next_position = path_to_target[0]
        else:
            best_direction = None
            strongest_signal = -1e9

            for direction_name, (move_x, move_y) in DIRECTION_OFFSETS.items():
                candidate_position = (bot_position[0] + move_x, bot_position[1] + move_y)

                if self.known_map.get(candidate_position, UNKNOWN_CELL) != WALL_CELL:
                    signal = self.gaussian_gem_signal(candidate_position, visible_gems)

                    if signal > strongest_signal:
                        strongest_signal = signal
                        best_direction = direction_name

            return best_direction or "N"

        move_x = next_position[0] - bot_position[0]
        move_y = next_position[1] - bot_position[1]

        for direction_name, (dx, dy) in DIRECTION_OFFSETS.items():
            if (move_x, move_y) == (dx, dy):
                return direction_name

        return "N"

bot = CaveExplorationBot()
first_tick = True

for line in sys.stdin:
    game_state = json.loads(line)

    if first_tick:
        config = game_state["config"]
        print(f"Cave bot started on {config['width']}x{config['height']} map", file=sys.stderr)
        first_tick = False

    bot_position = bot.remember_world(game_state)
    visible_gems = game_state.get("visible_gems", [])

    target_position = bot.choose_target_position(bot_position, visible_gems)
    chosen_direction = bot.decide_direction(bot_position, target_position, visible_gems)

    print(chosen_direction)
    sys.stdout.flush()
