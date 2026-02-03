#!/usr/bin/env python3
import sys
import json
import math
from collections import deque

sys.stdout.flush()

class CaveBot:
    def __init__(self, config):
        self.width = config.get("width", 19)
        self.height = config.get("height", 19)
        self.vis_radius = config.get("vis_radius", 5)
        self.max_ticks = config.get("max_ticks", 1200)
        
        # Map memory: 0 = unknown, 1 = floor, -1 = wall
        self.map = [[0 for _ in range(self.height)] for _ in range(self.width)]
        
        # Track visited cells for exploration
        self.visit_count = [[0 for _ in range(self.height)] for _ in range(self.width)]
        
        # Current position (will be updated each tick)
        self.x = None
        self.y = None
        
        # Current target we're pathfinding to
        self.current_target = None
        self.current_path = []
        
        # Directions: N, S, E, W
        self.directions = {
            "N": (0, -1),
            "S": (0, 1),
            "E": (1, 0),
            "W": (-1, 0)
        }
        
        self.tick = 0
        
    def update_map(self, bot_pos, walls, floors):
        """Update internal map with visible cells"""
        self.x, self.y = bot_pos
        
        # Mark current position as floor (we're standing here)
        self.map[self.x][self.y] = 1
        
        # Mark visible walls
        for wx, wy in walls:
            self.map[wx][wy] = -1
            
        # Mark visible floors
        for fx, fy in floors:
            self.map[fx][fy] = 1
            
        # Increment visit count for current position
        self.visit_count[self.x][self.y] += 1
    
    def get_neighbors(self, x, y):
        """Get valid neighboring cells (not walls, within bounds)"""
        neighbors = []
        for direction, (dx, dy) in self.directions.items():
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                if self.map[nx][ny] != -1:  # Not a wall
                    neighbors.append((nx, ny, direction))
        return neighbors
    
    def bfs_path(self, target):
        """Find shortest path to target using BFS"""
        if (self.x, self.y) == target:
            return []
            
        queue = deque([(self.x, self.y, [])])
        visited = {(self.x, self.y)}
        
        while queue:
            cx, cy, path = queue.popleft()
            
            for nx, ny, direction in self.get_neighbors(cx, cy):
                if (nx, ny) in visited:
                    continue
                    
                new_path = path + [direction]
                
                if (nx, ny) == target:
                    return new_path
                    
                visited.add((nx, ny))
                queue.append((nx, ny, new_path))
        
        return None  # No path found
    
    def find_nearest_unexplored(self):
        """Find nearest unexplored or rarely visited cell using BFS"""
        queue = deque([(self.x, self.y)])
        visited = {(self.x, self.y)}
        
        # Priority: completely unknown (0) > rarely visited floor (1)
        candidates = []
        
        while queue:
            cx, cy = queue.popleft()
            
            # Check if this is a good exploration target
            if self.map[cx][cy] == 0:  # Unknown
                return (cx, cy)
            elif self.map[cx][cy] == 1 and self.visit_count[cx][cy] < 2:
                candidates.append((cx, cy, self.visit_count[cx][cy]))
            
            for nx, ny, _ in self.get_neighbors(cx, cy):
                if (nx, ny) not in visited:
                    visited.add((nx, ny))
                    queue.append((nx, ny))
        
        # Return least visited floor if no unknown cells reachable
        if candidates:
            candidates.sort(key=lambda x: x[2])  # Sort by visit count
            return (candidates[0][0], candidates[0][1])
        
        return None
    
    def score_gem(self, gem):
        """Score a gem based on distance and TTL (Gaussian-inspired weighting)"""
        gx, gy = gem["position"]
        ttl = gem["ttl"]
        
        # Manhattan distance
        dist = abs(gx - self.x) + abs(gy - self.y)
        
        # Score: higher is better
        # Exponential decay based on distance (Gaussian-like)
        # Plus urgency factor from TTL
        distance_score = math.exp(-dist / self.vis_radius)  # 1.0 when close, decays when far
        urgency_score = ttl / 300  # Normalize TTL (assuming max 300)
        
        return distance_score * 0.6 + urgency_score * 0.4
    
    def choose_direction(self, visible_gems):
        """Main decision logic"""
        # Phase 1: If we can see gems, prioritize the best one
        if visible_gems:
            # Score and sort gems
            scored_gems = [(gem, self.score_gem(gem)) for gem in visible_gems]
            scored_gems.sort(key=lambda x: x[1], reverse=True)
            
            best_gem = scored_gems[0][0]
            target_pos = tuple(best_gem["position"])
            
            # If we're already targeting this gem, continue
            if self.current_target == target_pos and self.current_path:
                return self.current_path.pop(0)
            
            # Calculate new path to gem
            path = self.bfs_path(target_pos)
            if path:
                self.current_target = target_pos
                self.current_path = path[1:] if len(path) > 1 else []
                return path[0]
        
        # Phase 2: Exploration - find nearest unexplored/underexplored cell
        if not self.current_path or self.tick % 10 == 0:  # Re-evaluate periodically
            explore_target = self.find_nearest_unexplored()
            if explore_target:
                path = self.bfs_path(explore_target)
                if path:
                    self.current_target = explore_target
                    self.current_path = path[1:] if len(path) > 1 else []
                    return path[0]
        
        # Phase 3: If we have a cached path, follow it
        if self.current_path:
            return self.current_path.pop(0)
        
        # Phase 4: Desperate - move to least visited neighbor
        best_dir = None
        best_score = float('inf')
        
        for direction, (dx, dy) in self.directions.items():
            nx, ny = self.x + dx, self.y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                if self.map[nx][ny] != -1:  # Not a wall
                    score = self.visit_count[nx][ny]
                    if score < best_score:
                        best_score = score
                        best_dir = direction
        
        return best_dir if best_dir else "N"  # Default to North if stuck
    
    def tick_update(self, data):
        """Process one tick of game data"""
        self.tick = data.get("tick", 0)
        bot_pos = data.get("bot", [0, 0])
        walls = data.get("wall", [])
        floors = data.get("floor", [])
        visible_gems = data.get("visible_gems", [])
        
        # Update our map knowledge
        self.update_map(bot_pos, walls, floors)
        
        # Decide and return direction
        return self.choose_direction(visible_gems)


# Main loop
bot = None
first_tick = True

for line in sys.stdin:
    try:
        data = json.loads(line)
        
        if first_tick:
            config = data.get("config", {})
            bot = CaveBot(config)
            print(f"CaveExplorer bot launching on {config.get('width')}x{config.get('height')} map", 
                  file=sys.stderr)
            first_tick = False
        
        direction = bot.tick_update(data)
        print(direction)
        sys.stdout.flush()
        
    except json.JSONDecodeError:
        print("Error parsing JSON", file=sys.stderr)
        print("N")  # Safe fallback
        sys.stdout.flush()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("N")  # Safe fallback
        sys.stdout.flush()