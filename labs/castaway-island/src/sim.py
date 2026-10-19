"""
Castaway Island — 730-day survival simulation.

Twelve survivors of a ditched airliner live on a 1,200-acre tropical island
for two years. Each day the simulation:
  1. rolls the weather (wet / dry season, squalls, two cyclones),
  2. assigns every castaway a job (fishing, foraging, gardening, building,
     woodcutting, scouting, cooking, nursing, signal watch),
  3. resolves food, wood and building progress,
  4. updates health and morale, injuries and illness,
  5. writes a headline and journal line for the day.

The output (data/days.json) drives the video renderer. Deterministic: the same
seed always produces the same two years.
"""
from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SEED = 1200
START = date(2026, 11, 1)          # day 1: the ditching
DAYS = 730
LAT = -14.8                        # south Pacific
NEED_KCAL = 2300
REST_KCAL = 1900
ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- castaways
PEOPLE = [
    # id, name, age, role, color, skills
    ("ray",   "Ray Delgado",   54, "Captain (pilot)",       (214, 69, 65),  dict(fish=1.0, forage=0.8, build=0.9, wood=0.9, scout=1.0, lead=1.0)),
    ("nia",   "Nia Okafor",    31, "ER nurse",              (242, 242, 242), dict(fish=0.6, forage=0.9, build=0.7, wood=0.6, medic=1.0)),
    ("tomas", "Tomas Reyes",   42, "Carpenter",             (230, 145, 56), dict(fish=0.6, forage=0.7, build=1.5, wood=1.4)),
    ("hana",  "Hana Sato",     27, "Marine biologist",      (64, 180, 200), dict(fish=1.6, forage=0.9, build=0.7, wood=0.6, scout=0.8)),
    ("walt",  "Walt Brennan",  67, "Retired farmer",        (120, 160, 70), dict(fish=0.7, forage=1.1, garden=1.6, build=0.9, wood=0.8)),
    ("priya", "Priya Nair",    35, "Civil engineer",        (150, 90, 200), dict(fish=0.6, forage=0.8, build=1.3, wood=0.9, craft=1.3)),
    ("marcus","Marcus Hale",   29, "Flight attendant",      (40, 90, 170),  dict(fish=1.1, forage=1.0, build=1.0, wood=1.1, medic=0.6)),
    ("elena", "Elena Varga",   46, "Chef",                  (235, 200, 60), dict(fish=0.8, forage=1.1, build=0.7, wood=0.6, cook=1.6)),
    ("sam",   "Sam Whitaker",  16, "High-school student",   (90, 200, 120), dict(fish=0.9, forage=1.2, build=0.8, wood=0.8, scout=1.5)),
    ("june",  "June Whitaker", 44, "Teacher (Sam's mom)",   (220, 120, 170), dict(fish=0.6, forage=1.0, garden=1.1, build=0.8, wood=0.6, lead=0.8)),
    ("kofi",  "Kofi Mensah",   38, "Fisherman / boatwright", (30, 140, 110), dict(fish=1.5, forage=0.8, build=1.2, wood=1.3, boat=1.6)),
    ("lucy",  "Lucy Chen",     23, "Wilderness guide",      (200, 80, 40),  dict(fish=0.9, forage=1.5, build=0.9, wood=1.0, scout=1.4, fire=1.4)),
]
PRONOUN = {k: "her" for k in ("nia", "hana", "priya", "elena", "june", "lucy")} | {k: "his" for k in ("ray", "tomas", "walt", "marcus", "sam", "kofi")}
BIRTHDAYS = {  # month, day
    "ray": (2, 14), "nia": (6, 3), "tomas": (9, 21), "hana": (12, 9), "walt": (4, 30),
    "priya": (8, 12), "marcus": (1, 27), "elena": (7, 7), "sam": (3, 22),
    "june": (10, 2), "kofi": (5, 18), "lucy": (11, 25),
}

# ---------------------------------------------------------------- projects
@dataclass
class Project:
    key: str
    name: str
    hours: float
    logs: int
    unlock: int
    prereq: tuple = ()
    skill: str = "build"
    done_hours: float = 0.0
    logs_used: float = 0.0
    finished: int | None = None
    condition: float = 1.0           # storm damage lowers this
    repair_hours: float = 0.0

    @property
    def progress(self) -> float:
        return min(1.0, self.done_hours / self.hours)


def make_projects() -> list[Project]:
    P = Project
    return [
        P("signal_beach", "Beach signal fire", 8, 0, 1),
        P("leanto", "Palm-frond lean-to", 36, 4, 1),
        P("fish_kit", "Fishing lines, spears and a net", 20, 0, 3, skill="craft"),
        P("latrine", "Latrine and wash area", 20, 1, 4),
        P("elt", "Salvaged emergency beacon", 60, 0, 5, skill="craft"),
        P("peak_beacon", "Summit signal beacon", 60, 6, 6, ("summit",)),
        P("weir", "Lagoon fish weir", 140, 10, 12, ("fish_kit",)),
        P("hut1", "Sleeping hut 1", 170, 24, 14),
        P("aqueduct", "Bamboo aqueduct and cistern", 180, 6, 20, ("river",), skill="craft"),
        P("smokehouse", "Smokehouse", 110, 12, 24),
        P("hut2", "Sleeping hut 2", 170, 24, 30),
        P("sos", "Giant SOS on the beach", 60, 10, 35),
        P("garden1", "Garden terrace 1", 80, 2, 35, ("taro",), skill="garden"),
        P("salt", "Salt evaporation pans", 70, 2, 40, skill="craft"),
        P("hut3", "Sleeping hut 3", 170, 24, 45),
        P("garden2", "Garden terrace 2", 80, 2, 50, ("taro",), skill="garden"),
        P("hut4", "Sleeping hut 4", 170, 24, 60),
        P("lookout", "Summit lookout platform", 150, 18, 70, ("peak_beacon",)),
        P("canoe", "Dugout canoe", 420, 3, 80, ("fish_kit",), skill="boat"),
        P("garden3", "Garden terrace 3", 80, 2, 90, ("taro",), skill="garden"),
        P("infirmary", "Infirmary hut", 180, 20, 95),
        P("school", "Shade house and classroom", 90, 8, 120),
        P("kiln", "Clay kiln and pottery", 200, 4, 130, ("clay",), skill="craft"),
        P("garden4", "Garden terrace 4", 80, 2, 150, ("taro",), skill="garden"),
        P("bridge", "River footbridge", 140, 12, 160, skill="craft"),
        P("longhouse", "Longhouse (storm-proof hall)", 700, 90, 175),
        P("nursery", "Tree nursery and replanting", 90, 2, 200, skill="garden"),
        P("garden5", "Garden terrace 5", 80, 2, 200, ("taro",), skill="garden"),
        P("dock", "Lagoon dock", 260, 36, 260),
        P("garden6", "Garden terrace 6", 80, 2, 260, ("taro",), skill="garden"),
        P("outrigger", "Outrigger sailing canoe", 950, 6, 330, ("canoe", "dock"), skill="boat"),
        P("chapel", "Memorial garden and bell", 60, 4, 380),
    ]


# Discoveries happen as scouting hours accumulate.
DISCOVERIES = [
    (0,   "river",      "Found fresh water: a clear river tumbling off the mountain into the lagoon."),
    (10,  "summit",     "Sam and Lucy reached the 412 m summit. The island is about 3 km long. No other land in sight."),
    (26,  "taro",       "Wild taro and yams found in a wet hollow behind the beach."),
    (40,  "breadfruit", "A grove of breadfruit trees on the eastern slope."),
    (58,  "bananas",    "Wild bananas near the waterfall. Elena is thrilled."),
    (80,  "coast",      "First full walk around the coast: 9 km of shoreline, two good reefs, one sea cave."),
    (110, "cave",       "A dry cave above the river. Good storm shelter."),
    (150, "clay",       "Workable clay in the riverbank. Priya wants a kiln."),
    (190, "springs",    "A second spring on the north side keeps flowing in the dry season."),
]

# Scripted story beats (day -> (headline, morale delta, flags))
SCRIPT = {
    1:   ("Flight 1207 ditched on the reef at dawn. All 12 made it to shore.", -10, {"crash": True}),
    2:   ("Salvaged the galley, life rafts, a crash axe and the first-aid kits from the wreck.", 4, {}),
    7:   ("One week. Lean-to finished; the signal fire burns every night.", 3, {}),
    33:  ("The salvaged emergency beacon gave out. No reply was ever heard.", -6, {}),
    41:  ("Ship lights on the horizon after dark. The summit beacon was unlit that night; it never saw us.", -18, {"ship": "missed"}),
    42:  ("New rule: a night watch on the summit, every night, no exceptions.", 6, {}),
    100: ("Day 100. June carved the hundredth notch in the calendar post.", 5, {}),
    139: ("Cyclone. The camp is flattened; the weir is gone; the wreck slid off the reef.", -14, {"cyclone": True}),
    140: ("Everyone survived the cyclone in the cave. Rebuilding starts tomorrow.", 6, {}),
    183: ("Six months on the island.", 2, {}),
    226: ("Sam finished a full school year with June. Graduation by firelight.", 8, {}),
    303: ("A jet contrail, very high, heading south. Nobody saw it turn.", -6, {}),
    365: ("One year. A feast of smoked fish, breadfruit and roast taro.", 10, {}),
    388: ("A fishing boat on the horizon at dusk. Beacon lit, smoke rising. It turned away.", -16, {"ship": "missed"}),
    412: ("Marcus and Lucy were married on the beach. Captain Ray officiated.", 14, {"wedding": True}),
    466: ("Second cyclone. The longhouse held. Everyone rode it out inside.", -6, {"cyclone": True}),
    500: ("Day 500.", 3, {}),
    548: ("Eighteen months.", 1, {}),
    700: ("Thirty days to the two-year mark. The outrigger sails well.", 3, {}),
    728: ("A survey plane flew low over the island at midday and circled the SOS twice.", 25, {"plane": True}),
    729: ("The plane came back and dropped a radio. A ship is on its way.", 30, {"radio": True}),
    730: ("Day 730. Ship lights in the lagoon at dusk. Rescue.", 60, {"rescue": True}),
}
SCRIPTED_INJURIES = {  # day: (person, kind, days, text)
    16:  ("tomas", "injured", 9,  "Tomas gashed his hand splitting logs. Nia stitched it with the first-aid kit."),
    61:  ("ray",   "sick",    6,  "Captain Ray is down with a high fever. Nia keeps watch."),
    118: ("sam",   "injured", 32, "Sam fell from the lookout scaffold and broke his arm. Splinted by Nia."),
    255: ("walt",  "sick",    5,  "Walt collapsed from heat exhaustion in the garden. Ordered to rest."),
    431: ("kofi",  "injured", 12, "Kofi was stung by a stonefish. Hot-water treatment through the night."),
    602: ("elena", "sick",    7,  "Elena caught a stomach bug. Hana is cooking (badly)."),
}
CYCLONE_DAYS = {139: 1.0, 466: 0.55}   # severity


# ---------------------------------------------------------------- helpers
def sunset_hour(d: date) -> float:
    """Approximate local solar sunset time (hours) at LAT."""
    n = d.timetuple().tm_yday
    decl = math.radians(23.44) * math.sin(math.radians(360 / 365 * (n - 81)))
    lat = math.radians(LAT)
    h0 = math.radians(-0.833)
    cos_h = (math.sin(h0) - math.sin(lat) * math.sin(decl)) / (math.cos(lat) * math.cos(decl))
    H = math.degrees(math.acos(max(-1, min(1, cos_h))))
    b = math.radians(360 / 365 * (n - 81))
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)   # minutes
    return 12 + H / 15 - eot / 60


def moon_phase(d: date) -> float:
    """0 = new, 0.5 = full."""
    ref = date(2000, 1, 6)
    return ((d - ref).days + 0.76) / 29.530588 % 1.0


def season(d: date) -> str:
    return "wet" if d.month in (11, 12, 1, 2, 3, 4) else "dry"


@dataclass
class Person:
    id: str
    name: str
    age: int
    role: str
    color: tuple
    skills: dict
    health: float = 88.0
    morale: float = 55.0
    status: str = "ok"          # ok / sick / injured
    status_days: int = 0
    task: str = "rest"

    def skill(self, k: str) -> float:
        return self.skills.get(k, 0.7 if k in ("build", "wood", "fish", "forage", "garden", "craft", "boat") else 0.0)


# ---------------------------------------------------------------- simulation
def run() -> list[dict]:
    rng = random.Random(SEED)
    people = [Person(*p) for p in PEOPLE]
    by_id = {p.id: p for p in people}
    projects = make_projects()
    pj = {p.key: p for p in projects}
    found: set[str] = set()
    scout_hours = 0.0

    store = dict(preserved=0.0, coconuts=40.0, roots=0.0)   # kcal / count / kcal
    logs = 0.0
    trees_felled = 0
    trees_planted = 0
    wreck_on_reef = True
    weather_prev = "clear"
    plots_planted: dict[str, int] = {}
    totals = dict(fish=0.0, coconuts=0, fruit=0.0, roots=0.0, garden=0.0)
    days: list[dict] = []
    night_watch = False
    last_ratio = 0.7

    for day in range(1, DAYS + 1):
        d = START + timedelta(days=day - 1)
        seas = season(d)
        events: list[tuple[int, str]] = []     # (priority, text)
        flags: dict = {}

        # ---------------- weather
        p_rain, p_storm = (0.34, 0.05) if seas == "wet" else (0.17, 0.015)
        if weather_prev in ("rain", "storm"):
            p_rain += 0.12
        r = rng.random()
        if day in CYCLONE_DAYS:
            weather = "cyclone"
        elif day - 1 in CYCLONE_DAYS:
            weather = "rain"
        elif day in (1, 728, 729, 730):
            weather = "clear" if day != 1 else "cloudy"
        elif r < p_storm:
            weather = "storm"
        elif r < p_storm + p_rain:
            weather = "rain"
        elif r < p_storm + p_rain + 0.25:
            weather = "cloudy"
        else:
            weather = "clear"
        weather_prev = weather
        wind = {"clear": rng.uniform(2, 12), "cloudy": rng.uniform(6, 18), "rain": rng.uniform(10, 25),
                "storm": rng.uniform(25, 45), "cyclone": 150 * CYCLONE_DAYS.get(day, 1)}[weather]
        work_factor = {"clear": 1.0, "cloudy": 1.0, "rain": 0.7, "storm": 0.25, "cyclone": 0.0}[weather]

        # ---------------- status (illness / injury)
        for p in people:
            if p.status != "ok":
                p.status_days -= 1 + (1 if p.id != "nia" and by_id["nia"].status == "ok" and rng.random() < 0.25 else 0)
                if p.status_days <= 0:
                    p.status = "ok"
                    events.append((2, f"{p.name.split()[0]} is back on {PRONOUN[p.id]} feet."))
        if day in SCRIPTED_INJURIES:
            pid, kind, n, text = SCRIPTED_INJURIES[day]
            q = by_id[pid]
            q.status, q.status_days = kind, n
            q.health -= 12
            events.append((8, text))
        else:
            p_sick = 0.012 if day < 30 else 0.003
            for p in people:
                if p.status == "ok" and rng.random() < p_sick:
                    p.status, p.status_days = "sick", rng.randint(2, 5)
                    p.health -= 6
                    what = rng.choice(["a stomach bug", "a fever", "an infected coral cut", "sunstroke"])
                    events.append((5, f"{p.name.split()[0]} is laid up with {what}."))

        able = [p for p in people if p.status == "ok"]
        rest_day = day > 30 and d.weekday() == 6 and weather not in ("storm", "cyclone")

        # ---------------- discoveries (scouting)
        pending_disc = [x for x in DISCOVERIES if x[1] not in found]

        # ---------------- job assignment
        for p in people:
            p.task = "rest" if p.status == "ok" else ("sick" if p.status == "sick" else "injured")
        free = list(able)

        def take(task: str, skill: str, n: int = 1, prefer: list[str] | None = None):
            nonlocal free
            chosen = []
            for _ in range(n):
                if not free:
                    break
                pool = free
                if prefer:
                    pref = [q for q in free if q.id in prefer]
                    pool = pref or free
                best = max(pool, key=lambda q: q.skill(skill) + rng.random() * 0.15)
                best.task = task
                free.remove(best)
                chosen.append(best)
            return chosen

        if weather == "cyclone":
            for p in free:
                p.task = "shelter"
            free = []
        if weather == "storm":
            for p in free:
                p.task = "shelter"
            take_fire = [p for p in able if p.task == "shelter"][:1]
            for p in take_fire:
                p.task = "fire"
            free = []

        # essentials
        if any(p.status != "ok" for p in people):
            take("nurse", "medic", 1, prefer=["nia", "marcus"])
        take("cook", "cook", 1, prefer=["elena"])
        take("fire", "fire", 1, prefer=["lucy", "june", "ray", "sam"] if day % 3 else ["june", "walt", "marcus"])
        if not pj["aqueduct"].finished:
            take("water", "forage", 1)

        # food workers
        target_store_days = 3 if day < 30 else (8 if day < 120 else (14 if day < 365 else 18))
        store_kcal = store["preserved"] + store["coconuts"] * 650 + store["roots"]
        store_days = store_kcal / (12 * NEED_KCAL)
        n_food = 5 if day < 14 else 4
        if last_ratio < 0.97:
            n_food += 1 if last_ratio > 0.85 else 2
        if store_days > target_store_days * 1.3:
            n_food -= 1
        if store_days > target_store_days * 2.5:
            n_food -= 1
        n_food = max(2, min(7, n_food))
        if day < 3:
            n_food = 4
        gardens_live = [k for k in plots_planted if day - plots_planted[k] >= 0]
        if gardens_live and free:
            take("garden", "garden", 1 + (len(gardens_live) >= 3), prefer=["walt", "june"])
        n_fish = max(1, math.ceil(n_food * 0.55))
        fishers = take("fish", "fish", n_fish)
        foragers = take("forage", "forage", max(0, n_food - n_fish))

        # scouting
        scouts = []
        if pending_disc and day >= 2 and free:
            scouts = take("scout", "scout", 2 if day < 20 else 1, prefer=["sam", "lucy", "hana", "ray"])

        # projects
        active = [p for p in projects if p.finished is None and day >= p.unlock and all(r in found or (r in pj and pj[r].finished) for r in p.prereq)]
        repairs = [p for p in projects if p.repair_hours > 0]
        work_list = repairs + active
        logs_wanted = sum(max(0, p.logs * (1 - p.progress)) for p in active[:2]) + sum(p.logs * 0.3 for p in repairs)
        n_wood = 0
        if logs < logs_wanted:
            n_wood = 1 if logs_wanted - logs < 12 else (2 if logs_wanted - logs < 40 else 3)
        cutters = take("wood", "wood", n_wood) if work_list else []
        builders = []
        if rest_day:   # Sundays: no building, food and fires only
            for p in free:
                p.task = "rest"
            free = []
        for p in list(free):
            p.task = "build"
            builders.append(p)
        free = []
        if not work_list:
            for b in builders:
                b.task = "forage" if b.skill("forage") > b.skill("fish") else "fish"
                (foragers if b.task == "forage" else fishers).append(b)
            builders = []

        hours = 7.0 * work_factor
        # ---------------- scouting results
        for s in scouts:
            scout_hours += hours * s.skill("scout") * 0.5
        if day == 2 and "river" not in found:
            found.add("river")
            events.append((7, DISCOVERIES[0][2]))
        for need, key, text in DISCOVERIES:
            if key not in found and scout_hours >= need and day >= 3:
                found.add(key)
                events.append((6, text))
                break

        # ---------------- food production
        gear = 0.45 if not pj["fish_kit"].finished else 1.0
        wf_fish = {"clear": 1.0, "cloudy": 0.95, "rain": 0.65, "storm": 0.0, "cyclone": 0.0}[weather]
        fish_kg = 0.0
        canoe_out = None
        for i, f in enumerate(fishers):
            mult = gear
            if i == 0 and pj["outrigger"].finished:
                mult *= 2.3; canoe_out = "outrigger"
            elif i == 0 and pj["canoe"].finished:
                mult *= 1.6; canoe_out = "canoe"
            fish_kg += 1.6 * f.skill("fish") * mult * wf_fish * rng.lognormvariate(0, 0.45)
        weir = pj["weir"]
        if weir.finished and fishers and weather != "cyclone":
            fish_kg += rng.uniform(4, 11) * weir.condition * (0.6 if weather == "storm" else 1.0)
        fish_kg = round(fish_kg, 1)

        fruit_season = 1.0
        if d.month in (11, 12, 1, 2) or d.month in (6, 7, 8):
            fruit_season = 1.35
        coconuts = fruit_kg = roots_kg = 0.0
        for f in foragers:
            s = f.skill("forage") * work_factor
            coconuts += rng.randint(12, 22) * s
            fruit_kg += rng.uniform(2.0, 5.0) * s * fruit_season * (1 + 0.35 * ("breadfruit" in found) + 0.3 * ("bananas" in found))
            if "taro" in found:
                roots_kg += rng.uniform(1.0, 3.5) * s
        coconuts = int(coconuts)

        # gardens: mature 110 days after the terrace is finished
        gardeners = [p for p in people if p.task == "garden"]
        garden_kg = 0.0
        for k, planted in plots_planted.items():
            age = day - planted
            if age > 110:
                tend = 1.0 if gardeners else 0.6
                garden_kg += rng.uniform(1.8, 3.6) * tend * pj[k].condition * (0.8 if weather == "rain" else 1.0)
        garden_kg = round(garden_kg, 1)

        # ---------------- eating
        need = sum(NEED_KCAL if p.status == "ok" else REST_KCAL for p in people)
        fresh = fish_kg * 950 + fruit_kg * 750 + roots_kg * 1100 + garden_kg * 900
        eaten = min(fresh, need)
        leftover_fresh_fish = max(0, fish_kg * 950 - eaten) if fresh > need else 0
        remaining = need - eaten
        coco_cap = 22
        store["coconuts"] += coconuts
        use_coco = min(store["coconuts"], coco_cap, remaining / 650)
        store["coconuts"] -= use_coco
        eaten += use_coco * 650
        remaining = need - eaten
        for k in ("roots", "preserved"):
            take_k = min(store[k], max(0, remaining))
            store[k] -= take_k
            eaten += take_k
            remaining = need - eaten
        # surplus handling
        surplus = max(0, fresh - need)
        if surplus > 0:
            root_part = min(surplus, (roots_kg * 1100 + garden_kg * 900) * 0.6)
            store["roots"] += root_part
            surplus -= root_part
            if pj["smokehouse"].finished and any(p.task == "cook" for p in people):
                smoked = min(surplus, 15 * 950) * pj["smokehouse"].condition
                store["preserved"] += smoked
            elif day > 4:   # sun-dried and salted, poorly
                store["preserved"] += surplus * (0.35 if pj["salt"].finished else 0.15)
        store["preserved"] *= 0.99
        store["roots"] *= 0.965
        store["coconuts"] *= 0.985
        ratio = eaten / need
        last_ratio = ratio

        totals["fish"] += fish_kg; totals["coconuts"] += coconuts; totals["fruit"] += fruit_kg
        totals["roots"] += roots_kg; totals["garden"] += garden_kg

        # ---------------- wood
        axe_rate = 1.0 if day < 40 else 1.6
        felled = 0
        for c in cutters:
            felled += int(axe_rate * c.skill("wood") * work_factor * rng.uniform(0.7, 1.4) + rng.random())
        trees_felled += felled
        logs += felled * 3
        if pj["nursery"].finished and weather in ("clear", "cloudy", "rain"):
            planted_today = rng.choice([0, 1, 1, 2, 3]) if gardeners else rng.choice([0, 0, 1])
            trees_planted += planted_today

        # ---------------- building
        completed = []
        bh = {}
        for b in builders:
            bh[b.id] = hours
        build_pool = [(b, hours) for b in builders]
        # distribute builders: repairs first, then top two active projects
        targets = (repairs + active)[:3] or []
        for i, (b, h) in enumerate(build_pool):
            if not targets:
                break
            t = targets[i % len(targets)] if len(targets) > 1 and i >= len(build_pool) // 2 else targets[0]
            skill = b.skill(t.skill if t.skill != "build" else "build")
            if t.repair_hours > 0:
                t.repair_hours -= h * skill
                if t.repair_hours <= 0:
                    t.repair_hours = 0; t.condition = 1.0
                    events.append((4, f"Repairs finished on the {t.name.lower()}."))
                else:
                    t.condition = min(1.0, t.condition + 0.02)
                continue
            frac_needed = (h * skill) / t.hours
            logs_needed = t.logs * frac_needed
            if logs_needed > logs + 1e-6 and t.logs > 0:
                frac_needed *= max(0.0, logs / logs_needed) if logs_needed else 1
                logs_needed = logs
            logs -= logs_needed
            t.logs_used += logs_needed
            t.done_hours += frac_needed * t.hours
            if t.done_hours >= t.hours and t.finished is None:
                t.finished = day
                completed.append(t)
            if t.finished is not None and targets and t in targets:
                targets = [x for x in targets if x.finished is None or x.repair_hours > 0] or targets
        for t in completed:
            events.append((7, f"Finished: {t.name}."))
            for p in people:
                p.morale += 3
            if t.key.startswith("garden"):
                plots_planted[t.key] = day
        logs = max(0.0, logs)

        # ---------------- storms damage
        if weather in ("cyclone", "storm"):
            sev = CYCLONE_DAYS.get(day, 0.12 if weather == "storm" else 0)
            for t in projects:
                if t.finished and t.key not in ("fish_kit", "elt", "signal_beach"):
                    toughness = 0.3 if t.key in ("longhouse",) else (0.6 if t.key in ("kiln", "bridge", "lookout") else 1.0)
                    dmg = min(0.95, sev * toughness * rng.uniform(0.5, 1.0))
                    if t.key == "weir" and day == 139:
                        dmg = 0.95
                    if dmg > 0.08:
                        t.condition = max(0.05, t.condition - dmg)
                        t.repair_hours += dmg * t.hours * 0.45
            if day == 139:
                wreck_on_reef = False
            if weather == "storm" and any(t.repair_hours > 0 for t in projects):
                events.append((3, "A squall tore through camp overnight. Repairs needed."))

        # ---------------- night watch / beacon
        if day >= 42:
            night_watch = True
        beacon_lit = pj["peak_beacon"].finished is not None and (night_watch or day % 2 == 0)

        # ---------------- health and morale
        shelter_cap = (12 if pj["leanto"].finished else 0) * 0.6 + sum(3 for k in ("hut1", "hut2", "hut3", "hut4") if pj[k].finished and pj[k].condition > 0.5) + (12 if pj["longhouse"].finished and pj["longhouse"].condition > 0.4 else 0)
        sheltered = min(1.0, shelter_cap / 12)
        for p in people:
            dh = (ratio - 0.88) * 7 if ratio < 0.88 else 0.0
            if ratio >= 0.88:
                dh += (100 - p.health) * 0.04
            if weather in ("rain", "storm", "cyclone"):
                dh -= (1 - sheltered) * 2.5
            if p.status == "sick":
                dh -= 2.0
            if p.status == "injured":
                dh -= 0.6
            if p.task == "rest":
                dh += 0.6
            p.health = max(30, min(100, p.health + dh))
            target = 48 + 18 * sheltered + 8 * min(1, store_days / 10) + (6 if rest_day else 0) + 6 * min(1, day / 200)
            p.morale += (target - p.morale) * 0.06 + rng.uniform(-1.2, 1.2)
            if p.status != "ok":
                p.morale -= 0.8

        # birthdays
        for pid, (m, dd) in BIRTHDAYS.items():
            if d.month == m and d.day == dd:
                q = by_id[pid]
                q.age += 1
                events.append((5, f"{q.name.split()[0]} turned {q.age}. Elena baked coconut cake on a hot stone."))
                for p in people:
                    p.morale += 4
                flags["birthday"] = pid

        # scripted beats
        headline = None
        if day in SCRIPT:
            text, dm, fl = SCRIPT[day]
            events.append((10, text))
            flags.update(fl)
            for p in people:
                p.morale += dm
        for p in people:
            p.morale = max(10, min(100, p.morale))

        # notable catches
        if fish_kg >= 22 and day > 20:
            events.append((3, f"Big day on the water: {fish_kg:.0f} kg of fish{' from the ' + canoe_out if canoe_out else ''}."))
        if weather == "rain" and day % 11 == 0:
            events.append((1, "Rain all day. The cistern is full." if pj["aqueduct"].finished else "Rain all day. Every shell and hull-panel set out to catch it."))

        events.sort(key=lambda e: -e[0])
        if events:
            headline = events[0][1]
        else:
            in_prog = [t for t in active if t.done_hours > 0]
            if in_prog:
                t = in_prog[0]
                headline = f"{t.name}: {int(t.progress * 100)}% built. {fish_kg:.0f} kg fish, {coconuts} coconuts."
            else:
                headline = f"A quiet day. {fish_kg:.0f} kg fish, {coconuts} coconuts gathered."
        if rest_day and (not events or events[0][0] < 3):
            headline = rng.choice([
                "Sunday. No building today: fishing, swimming and a long supper.",
                "Sunday rest. June held class on the beach; Kofi taught knots.",
                "Sunday. Walt's garden tour, then a nap in the shade.",
                "Day of rest. Cards made from palm bark; Marcus is unbeatable.",
            ])

        store_kcal = store["preserved"] + store["coconuts"] * 650 + store["roots"]
        days.append({
            "day": day,
            "date": d.isoformat(),
            "weekday": d.strftime("%a"),
            "season": seas,
            "weather": weather,
            "wind_kmh": round(wind),
            "sunset": round(sunset_hour(d), 3),
            "moon": round(moon_phase(d), 3),
            "headline": headline,
            "events": [e[1] for e in events[:4]],
            "flags": flags,
            "rest_day": rest_day,
            "food": {
                "fish_kg": fish_kg, "coconuts": coconuts, "fruit_kg": round(fruit_kg, 1),
                "roots_kg": round(roots_kg, 1), "garden_kg": garden_kg,
                "eaten_pct": round(ratio * 100), "store_days": round(store_kcal / (12 * NEED_KCAL), 1),
            },
            "wood": {"logs": round(logs), "felled_total": trees_felled, "planted_total": trees_planted},
            "projects": {t.key: {"p": round(t.progress, 3), "c": round(t.condition, 2), "done": t.finished}
                         for t in projects if t.done_hours > 0},
            "found": sorted(found),
            "wreck_on_reef": wreck_on_reef,
            "beacon_lit": beacon_lit,
            "canoe_out": canoe_out,
            "people": [{"id": p.id, "task": p.task, "status": p.status,
                        "health": round(p.health), "morale": round(p.morale), "age": p.age} for p in people],
        })

    meta = {
        "start": START.isoformat(), "days": DAYS, "seed": SEED,
        "people": [{"id": p[0], "name": p[1], "age": p[2], "role": p[3], "color": p[4]} for p in PEOPLE],
        "projects": {t.key: {"name": t.name, "finished": t.finished, "hours": t.hours, "logs": t.logs} for t in projects},
        "totals": {k: round(v, 1) for k, v in totals.items()} | {"trees_felled": trees_felled, "trees_planted": trees_planted},
    }
    return days, meta


def write_outputs(days, meta):
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    (data / "days.json").write_text(json.dumps({"meta": meta, "days": days}, separators=(",", ":")))
    with open(data / "daily_stats.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["day", "date", "weather", "fish_kg", "coconuts", "fruit_kg", "roots_kg", "garden_kg",
                    "eaten_pct", "store_days", "logs", "trees_felled", "trees_planted",
                    "avg_health", "avg_morale", "sick_or_injured", "headline"])
        for d in days:
            ppl = d["people"]
            w.writerow([d["day"], d["date"], d["weather"], d["food"]["fish_kg"], d["food"]["coconuts"],
                        d["food"]["fruit_kg"], d["food"]["roots_kg"], d["food"]["garden_kg"],
                        d["food"]["eaten_pct"], d["food"]["store_days"], d["wood"]["logs"],
                        d["wood"]["felled_total"], d["wood"]["planted_total"],
                        round(sum(p["health"] for p in ppl) / 12), round(sum(p["morale"] for p in ppl) / 12),
                        sum(p["status"] != "ok" for p in ppl), d["headline"]])
    # journal
    lines = ["# Castaway Island — the journal", "",
             "One line per day, kept by June Whitaker on the calendar post (generated by `src/sim.py`).", ""]
    month = None
    for d in days:
        dt = date.fromisoformat(d["date"])
        if dt.strftime("%B %Y") != month:
            month = dt.strftime("%B %Y")
            lines += ["", f"## {month}", ""]
        extra = [e for e in d["events"] if e != d["headline"]][:2]
        tail = (" " + " ".join(extra)) if extra else ""
        lines.append(f"- **Day {d['day']}** ({d['weekday']} {dt.day}, {d['weather']}) — {d['headline']}{tail}")
    (ROOT / "docs" / "journal.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    days, meta = run()
    write_outputs(days, meta)
    fin = {k: v["finished"] for k, v in meta["projects"].items()}
    print("finished:", fin)
    print("totals:", meta["totals"])
    print("store days end:", days[-1]["food"]["store_days"], "eaten% avg:",
          sum(d["food"]["eaten_pct"] for d in days) / len(days))
