"""CISC 121 Lab - Part A: Multi-agent grid world with shared memory  (STARTER - complete the 5 TODOs)

Minecraft-inspired: agents with LIMITED VISION explore a grid, gather WOOD / STONE / IRON,
avoid LAVA, craft a sword once the TEAM has enough materials, then one agent must reach
the BOSS cell. We compare agents with PRIVATE memory against agents that share a MEMORY
blackboard (what one agent sees, all agents know).
"""
import random
from collections import deque

SIZE = 16
VISION = 1                                     # sees cells within Chebyshev distance 1
NEEDS = {"WOOD": 3, "STONE": 3, "IRON": 2}     # team requirement for the sword
MOVES = [(0, 1), (0, -1), (1, 0), (-1, 0)]
RESPAWN_PENALTY = 5                            # steps an agent loses after dying in lava
BASE, BOSS = (0, 0), (SIZE - 1, SIZE - 1)


def make_world(seed):
    """Return grid: dict (x,y) -> '.', 'WOOD', 'STONE', 'IRON', 'LAVA', 'BOSS'."""
    rng = random.Random(seed)
    free = [(x, y) for x in range(SIZE) for y in range(SIZE)
            if (x, y) not in (BASE, BOSS) and max(x, y) > 1 and min(SIZE - 1 - x, SIZE - 1 - y) > 0]
    rng.shuffle(free)
    grid = {(x, y): "." for x in range(SIZE) for y in range(SIZE)}
    grid[BOSS] = "BOSS"
    for kind, n in (("WOOD", 5), ("STONE", 5), ("IRON", 4), ("LAVA", 30)):
        for _ in range(n):
            grid[free.pop()] = kind
    return grid


class SharedMemory:
    """A blackboard: anything written here can be read by every agent holding a reference."""
    def __init__(self):
        self.seen = {}                         # (x,y) -> terrain label

    def write(self, cell, label):
        # TODO 1: store the label for this cell in self.seen
        pass

    def read(self):
        # TODO 2: return the dictionary of everything remembered so far
        pass


class Agent:
    def __init__(self, aid, memory):
        self.id, self.pos, self.memory = aid, BASE, memory
        self.wait, self.deaths = 0, 0

    def observe(self, grid):
        """Write every cell inside the vision window to memory."""
        # TODO 3: loop over every cell within VISION of self.pos (a square window).
        #         For each cell that exists in grid, call self.memory.write(cell, grid[cell]).
        pass

    def bfs(self, goal_test):
        """Breadth-first search over KNOWN, non-lava cells.
        Returns (first_step, target_cell) for the nearest cell passing goal_test, else None."""
        known, start = self.memory.read(), self.pos
        q, prev = deque([start]), {start: None}
        while q:
            cur = q.popleft()
            if cur != start and goal_test(cur, known):
                target = cur
                while prev[cur] != start:
                    cur = prev[cur]
                return (cur[0] - start[0], cur[1] - start[1]), target
            for dx, dy in MOVES:
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt in prev or nxt not in known or known[nxt] == "LAVA":
                    continue
                prev[nxt] = cur
                q.append(nxt)
        return None

    def choose_move(self, needed, claimed, sword, rng):
        """Priority: boss (if sword) > nearest unclaimed needed resource > frontier > random."""
        if sword:
            r = self.bfs(lambda c, k: k[c] == "BOSS")
            if r:
                return r[0]
        r = self.bfs(lambda c, k: k[c] in needed and c not in claimed)
        if r:
            claimed.add(r[1])                  # tell teammates (this turn) not to go there too
            return r[0]
        def is_frontier(c, k):
            # TODO 4: return True if cell c is KNOWN but has at least one in-bounds neighbor
            #         (use MOVES) that is NOT in k yet. That is where new information lives.
            return False
        r = self.bfs(is_frontier)
        if r:
            return r[0]
        return rng.choice(MOVES)


def run_episode(seed, n_agents, shared, max_steps=800):
    grid = make_world(seed)
    rng = random.Random(seed + 999)
    common = SharedMemory()
    # TODO 5: if shared is True every agent must receive the SAME memory object (common);
    #         otherwise each agent gets its own SharedMemory().
    agents = [Agent(i, SharedMemory()) for i in range(n_agents)]
    inventory = {k: 0 for k in NEEDS}          # team inventory is pooled
    sword, deaths, moves = False, 0, 0
    for step in range(1, max_steps + 1):
        claimed = set()
        for a in agents:
            if a.wait > 0:
                a.wait -= 1
                continue
            a.observe(grid)
            needed = {k for k, v in NEEDS.items() if inventory[k] < v}
            dx, dy = a.choose_move(needed, claimed, sword, rng)
            nx, ny = a.pos[0] + dx, a.pos[1] + dy
            if not (0 <= nx < SIZE and 0 <= ny < SIZE):
                continue
            a.pos = (nx, ny)
            moves += 1                         # total effort across the whole team
            cell = grid[a.pos]
            if cell == "LAVA":
                a.memory.write(a.pos, "LAVA")  # the death is remembered (and shared if shared)
                a.deaths += 1
                deaths += 1
                a.pos, a.wait = BASE, RESPAWN_PENALTY
            elif cell in NEEDS:
                if inventory[cell] < NEEDS[cell]:
                    inventory[cell] += 1
                grid[a.pos] = "."
                a.memory.write(a.pos, ".")
                sword = all(inventory[k] >= v for k, v in NEEDS.items())
            elif cell == "BOSS" and sword:
                return {"success": True, "steps": step, "deaths": deaths, "moves": moves}
    return {"success": False, "steps": max_steps, "deaths": deaths, "moves": moves}


def experiment(n_agents_list=(1, 2, 4, 8), trials=60):
    rows = []
    for n in n_agents_list:
        for shared in (False, True):
            res = [run_episode(s, n, shared) for s in range(trials)]
            rows.append({"agents": n, "shared": shared,
                         "success_rate": sum(r["success"] for r in res) / trials,
                         "mean_steps": sum(r["steps"] for r in res) / trials,
                         "mean_moves": sum(r["moves"] for r in res) / trials})
    return rows


if __name__ == "__main__":
    print(f"{'agents':>6} {'memory':>8} {'success':>8} {'steps':>8} {'moves':>8}")
    for r in experiment():
        print(f"{r['agents']:>6} {'shared' if r['shared'] else 'private':>8} "
              f"{r['success_rate']:>8.0%} {r['mean_steps']:>8.1f} {r['mean_moves']:>8.1f}")
