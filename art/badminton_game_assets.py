#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.6", "pillow>=10"]
# ///
"""Sprite sheets for the Godot badminton game, drawn in Aseprite through aseprite-mcp.

Uses the same renderer, poses and court as the three animations, so the game
looks like them. Writes into the Godot project:

  assets/sprites/<who>.png + .json   one sheet per player (red_man, red_woman,
                                     blue_man, blue_woman), one Aseprite tag per
                                     animation (idle, run, overhead, lift, ...)
  assets/sprites/shuttle.png + .json the shuttle in 32 flight directions
  assets/sprites/crowd.png + .json   the crowd in the stands: "idle" and "cheer" tags
  assets/court/background.png        hall, stands, sponsor boards, floor, court lines,
                                     scoreboard panel
  assets/court/net_back.png          far half of the net (behind the players)
  assets/court/net_front.png         near half of the net and the near post
  assets/rig.json                    contact points of every stroke, hand points
                                     for serving, cell anchor (game data)
  assets/source/*.aseprite           the Aseprite files (mcp mode only)
  icon.png                           project icon

Keep it next to badminton_rally.py, badminton_point.py and badminton_doubles.py.

  # Through the real aseprite-mcp server (full Aseprite build):
  uv run badminton_game_assets.py mcp --mcp-dir ~/aseprite-mcp --game ~/badminton/game

  # Same tool calls rendered locally with Pillow (no Aseprite needed):
  uv run badminton_game_assets.py preview --game ./game

  # Only the planned tool calls, as JSON:
  uv run badminton_game_assets.py plan --out ./plan_game.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import badminton_rally as base  # noqa: E402
import badminton_point as pt  # noqa: E402  (registers the point's poses)
import badminton_doubles as db  # noqa: E402  (registers the doubles' poses, people)
from badminton_rally import Call, Raster  # noqa: E402

W, H = base.W, base.H
CHARACTERS = ("red_man", "red_woman", "blue_man", "blue_woman")
PLAY_D = 86                      # depth row the game is played on (players and shuttle)
NET_SPLIT_X = 97                 # screen column of the net at PLAY_D: <= in front of the players

# --------------------------------------------------------------------------
# Animations: name -> (frames [(pose, ms)], loop, contact frame index or None)
# --------------------------------------------------------------------------

ANIMS = {
    "idle":        ([("ready_a", 260), ("ready_b", 260)], True, None),
    "receive":     ([("receive", 300), ("receive_b", 300)], True, None),
    "run":         ([("run_a", 110), ("run_b", 110)], True, None),
    "back":        ([("back_a", 120), ("back_b", 120)], True, None),
    "split":       ([("split", 90), ("split_land", 120)], False, None),
    "jump":        ([("crouch", 60), ("jump_windup", 90), ("jump_windup2", 200)], False, None),
    "land":        ([("split_land", 120)], False, None),
    "overhead":    ([("prep", 70), ("windup", 70), ("swing", 50), ("contact", 80),
                     ("follow", 130), ("recover", 120)], False, 3),
    "jump_smash":  ([("jump_windup2", 60), ("jump_swing", 50), ("jump_contact", 80),
                     ("smash_air", 160)], False, 2),
    "smash_land":  ([("smash_land", 150)], False, None),
    "kill":        ([("kill_reach", 60), ("kill_reach2", 50), ("kill_contact", 80),
                     ("kill_follow", 120), ("kill_land", 120)], False, 2),
    "drive":       ([("drive_prep", 80), ("drive_contact", 80), ("drive_follow", 140)], False, 1),
    "block":       ([("block_prep", 70), ("block_contact", 80), ("block_follow", 140)], False, 1),
    "net":         ([("lunge_reach", 70), ("lunge", 70), ("lunge_net", 90), ("lunge", 160)], False, 2),
    "lift":        ([("lunge_reach", 70), ("lunge", 70), ("lunge_lift", 80), ("lift_follow", 160)], False, 2),
    "serve":       ([("serve_hold", 400), ("serve_swing", 110), ("serve_contact", 80),
                     ("serve_follow", 200)], False, 2),
    "serve_short": ([("bh_serve_hold", 300), ("bh_serve_back", 110), ("bh_serve_contact", 80),
                     ("bh_serve_follow", 200)], False, 2),
    "celebrate":   ([("celebrate_a", 160), ("celebrate_b", 160)], True, None),
    "dejected":    ([("dejected_a", 400), ("dejected_b", 400)], True, None),
}
SERVES = ("serve", "serve_short")
SHUTTLE_DIRS = 32
SHUTTLE_CELL = 13

# --------------------------------------------------------------------------
# The hall for the game: stands with a crowd, sponsor boards, a game panel
# --------------------------------------------------------------------------

CROWD_Y, CROWD_H = 8, 28            # the crowd sheet covers screen rows 8-35
# (head top row, first seat x, last seat x) per tier, back to front; the two back
# tiers stop short of the scoreboard (left) and the game panel (right)
TIERS = ((12, 49, 151), (20, 52, 151), (28, 3, 183))
SEAT_PITCH = 6
GAME_PANEL = (159, 9, 31, 11)       # x, y, w, h of the board behind "GAME n"
BOARD_X = (4, 52, 104, 152)         # the four sponsor boards of draw_background
# Invented sponsors (text, colour) for those boards, left to right. 3x5 capitals,
# digits and "x"; up to 8 characters fit a board.
SPONSORS = (("AIRVANE", "#eef0e6"), ("3x15 CUP", "#fff2a0"),
            ("CORKSTAR", "#1d2a45"), ("FIZZBIRD", "#eef0e6"))
CROWD_ANIMS = (("idle", 2, 700), ("cheer", 4, 110))     # tag, frames, ms per frame
CROWD_DIM = 0.74                    # the stands are darker than the lit court
SKINS = ("#e6b38c", "#c9936a", "#a36b46", "#704732")
HAIRS = ("#2a1d16", "#4b3222", "#141414", "#8c6a3c", "#9b9b9b", "#5c2b1b")
FAN_RED, FAN_BLUE = "#c44a4a", "#4677c4"
SHIRTS = ("#4f8a52", "#7a5aa8", "#c99a3a", "#5f6b7d", "#2f4f7a", "#a85f35", "#3d8a8a", "#8a3d6a")
SCARF_STRIPE = "#d9d2c3"
SEAT, TIER_EDGE, STAND_FRONT = "#2a3a5f", "#2f4169", "#151d32"

FONT = {                            # the game's 3x5 font (scripts/pixel_font.gd)
    "0": ('###', '#.#', '#.#', '#.#', '###'), "1": ('.#.', '##.', '.#.', '.#.', '###'),
    "2": ('###', '..#', '###', '#..', '###'), "3": ('###', '..#', '.##', '..#', '###'),
    "4": ('#.#', '#.#', '###', '..#', '..#'), "5": ('###', '#..', '###', '..#', '###'),
    "6": ('###', '#..', '###', '#.#', '###'), "7": ('###', '..#', '..#', '.#.', '.#.'),
    "8": ('###', '#.#', '###', '#.#', '###'), "9": ('###', '#.#', '###', '..#', '###'),
    "A": ('.#.', '#.#', '###', '#.#', '#.#'), "B": ('##.', '#.#', '##.', '#.#', '##.'),
    "C": ('.##', '#..', '#..', '#..', '.##'), "D": ('##.', '#.#', '#.#', '#.#', '##.'),
    "E": ('###', '#..', '##.', '#..', '###'), "F": ('###', '#..', '##.', '#..', '#..'),
    "G": ('.##', '#..', '#.#', '#.#', '.##'), "H": ('#.#', '#.#', '###', '#.#', '#.#'),
    "I": ('###', '.#.', '.#.', '.#.', '###'), "J": ('..#', '..#', '..#', '#.#', '.#.'),
    "K": ('#.#', '#.#', '##.', '#.#', '#.#'), "L": ('#..', '#..', '#..', '#..', '###'),
    "M": ('#.#', '###', '###', '#.#', '#.#'), "N": ('##.', '#.#', '#.#', '#.#', '#.#'),
    "O": ('.#.', '#.#', '#.#', '#.#', '.#.'), "P": ('##.', '#.#', '##.', '#..', '#..'),
    "Q": ('.#.', '#.#', '#.#', '##.', '.##'), "R": ('##.', '#.#', '##.', '#.#', '#.#'),
    "S": ('.##', '#..', '.#.', '..#', '##.'), "T": ('###', '.#.', '.#.', '.#.', '.#.'),
    "U": ('#.#', '#.#', '#.#', '#.#', '###'), "V": ('#.#', '#.#', '#.#', '#.#', '.#.'),
    "W": ('#.#', '#.#', '###', '###', '#.#'), "X": ('#.#', '#.#', '.#.', '#.#', '#.#'),
    "Y": ('#.#', '#.#', '.#.', '.#.', '.#.'), "Z": ('###', '..#', '.#.', '#..', '###'),
    "x": ('...', '#.#', '.#.', '#.#', '...'), " ": ('...', '...', '...', '...', '...'),
}


def text_raster(r: Raster, x, y, text, colour):
    for ch in text:
        glyph = FONT.get(ch) or FONT.get(ch.upper())
        if glyph:
            for yy, row in enumerate(glyph):
                for xx, c in enumerate(row):
                    if c == "#":
                        r.put(x + xx, y + yy, colour)
        x += 4


def crowd_people():
    """Everyone in the stands, back tier first; the same seats in every frame."""
    import random
    rng = random.Random(15)
    people = []
    for hy, x0, x1 in TIERS:
        for sx in range(x0, x1 + 1, SEAT_PITCH):
            if rng.random() < 0.07:
                continue                                        # an empty seat
            pick = rng.random()
            shirt = FAN_RED if pick < 0.22 else FAN_BLUE if pick < 0.44 else rng.choice(SHIRTS)
            style = rng.choices(("arms", "clap", "wave", "scarf"), (40, 30, 15, 15))[0]
            x = sx + rng.choice((-1, 0, 0, 1))
            if style == "scarf" and (shirt not in (FAN_RED, FAN_BLUE) or (hy == TIERS[2][0] and x < 48)):
                style = "arms"                  # scarves for fans; none over the scoreboard
            people.append(dict(x=x, y=hy, skin=rng.choice(SKINS), hair=rng.choice(HAIRS),
                               long=rng.random() < 0.3, shirt=shirt, style=style,
                               side=rng.choice((-1, 1)), phase=rng.randrange(4),
                               fidget=rng.random() < 0.3))
    return people


def crowd_frame(people, tag, f) -> Raster:
    """Frame f of the crowd's idle or cheer animation, in sheet coordinates.

    A spectator is a 3x3 head (hair on top, longer hair at the sides) over a 5x4
    shirt; cheering raises the arms, claps, waves or holds a scarf up, with
    small jumps, each person at their own phase.
    """
    r = Raster()

    def put(x, y, c):
        if 0 <= x < W and 0 <= y - CROWD_Y < CROWD_H:
            r.put(x, y - CROWD_Y, c)

    for p in people:
        x, y = p["x"], p["y"]
        skin, hair = base.darken(p["skin"], CROWD_DIM), base.darken(p["hair"], CROWD_DIM)
        shirt = base.darken(p["shirt"], CROWD_DIM)
        sleeve = base.darken(p["shirt"], CROWD_DIM * 0.82)
        hx, dy = x, 0
        limbs = []                                   # (x, y, colour), drawn last
        k = (f + p["phase"]) % 4
        st = p["style"]
        if tag == "idle":
            if p["fidget"] and f == 1:
                hx = x + p["side"]                   # turns to a neighbour
        elif st in ("arms", "scarf"):
            dy = -1 if k in (0, 2) else 0
            if st == "arms":
                if k in (0, 2):                      # straight up
                    hands = ((x - 1, y - 1), (x + 3, y - 1))
                elif k == 1:                         # a V
                    hands = ((x - 2, y - 1), (x + 4, y - 1))
                else:                                # fists at the shoulders
                    hands = ((x - 2, y + 1), (x + 4, y + 1))
                for ax, hy in hands:
                    col = x - 1 if ax < x else x + 3
                    for yy in range(hy + 1, y + 3):
                        limbs.append((col, yy + dy, skin))
                    limbs.append((ax, hy + dy, skin))
            else:                                    # a scarf held up in both hands
                top = y - 2 if k in (0, 2) else y - 1
                for i, sxx in enumerate(range(x - 2, x + 5)):
                    limbs.append((sxx, top + dy, shirt if i % 2 == 0 else base.darken(SCARF_STRIPE, CROWD_DIM)))
                for ax in (x - 2, x + 4):
                    col = x - 1 if ax < x else x + 3
                    limbs.append((ax, top + 1 + dy, skin))
                    for yy in range(top + 2, y + 3):
                        limbs.append((col, yy + dy, skin))
        elif st == "clap":
            if k in (0, 2):                          # hands apart
                limbs += [(x, y + 4, skin), (x + 2, y + 4, skin)]
            else:                                    # hands together
                limbs.append((x + 1, y + 3, skin))
        else:                                        # waving one arm
            col = x - 1 if p["side"] < 0 else x + 3
            ax = col + p["side"] if k in (0, 1) else col
            limbs.append((ax, y - 1, skin))
            for yy in range(y, y + 3):
                limbs.append((col, yy, skin))
        for yy in range(y + 3, y + 7):               # shirt, sleeves at the sides
            for xx in range(x - 1, x + 4):
                put(xx, yy + dy, sleeve if xx in (x - 1, x + 3) else shirt)
        for xx in range(hx, hx + 3):                 # head
            put(xx, y + dy, hair)
            put(xx, y + 1 + dy, hair if p["long"] and xx != hx + 1 else skin)
            put(xx, y + 2 + dy, hair if p["long"] and xx != hx + 1 else skin)
        for lx, ly, c in limbs:
            put(lx, ly, c)
    return r


def draw_hall(rect, rows):
    """The game's additions to the animations' hall: tiers of seats behind the
    crowd sheet, the front of the stand, a panel for the game number, and the
    sponsors' names on the boards."""
    C, bg = base.C, "background"
    stands = Raster()
    for i, (hy, x0, x1) in enumerate(TIERS):
        front = i == len(TIERS) - 1
        for x in range(W) if front else range(x0 - 3, x1 + 6):
            stands.put(x, hy + 7, TIER_EDGE)         # the step the row sits on
        for sx in range(x0, x1 + 1, SEAT_PITCH):     # seat backs (seen when empty)
            for yy in (hy + 4, hy + 5):
                for xx in range(sx, sx + 3):
                    stands.put(xx, yy, SEAT)
    for x in range(W):
        stands.put(x, 36, TIER_EDGE)
        for yy in range(37, 42):
            stands.put(x, yy, STAND_FRONT)
    rows(bg, 1, stands)
    gx, gy, gw, gh = GAME_PANEL
    rect(bg, gx, gy, gw, gh, C["panel_rim"])
    rect(bg, gx + 1, gy + 1, gw - 2, gh - 2, C["panel"])
    names = Raster()
    for i, bx in enumerate(BOARD_X):
        rect(bg, bx, 57, 36, 11, C["boards"][i])     # clear the placeholder stripes
        text, colour = SPONSORS[i]
        text_raster(names, bx + (36 - (len(text) * 4 - 1)) // 2, 60, text, colour)
    rows(bg, 1, names)


def face(who):
    return db.PEOPLE[who]["face"]


def render(who, pose_name) -> Raster:
    """A player as drawn in the doubles animation; blue faces left (mirrored)."""
    r = db.render_person(who, pose_name)
    return r.mirrored() if face(who) < 0 else r


def frame_list():
    """Every sheet frame in order: (anim, pose, ms)."""
    return [(name, pose, ms) for name, (frames, _, _) in ANIMS.items() for pose, ms in frames]


def cell_geometry():
    """One cell size for every player sheet, root at a shared anchor (ax, ay)."""
    xs, ys = [], []
    for who in CHARACTERS:
        for _, pose, _ in frame_list():
            for x, y in render(who, pose).px:
                xs.append(x)
                ys.append(y)
    ax = max(-min(xs), max(xs)) + 1           # symmetric, so red and blue share the anchor
    ay = -min(ys) + 1
    return 2 * ax + 1, ay + max(ys) + 2, ax, ay


def local(who, pose_name, key):
    """(dx, z) of a point for the player facing right: 'racket' head centre or a joint.

    z is the height above the feet; the pose's own jump lift is included.
    """
    p = db.scaled_pose(pose_name, db.PEOPLE[who]["scale"])
    x, y = base.racket_head_centre(p) if key == "racket" else p[key]
    return [round(x, 2), round(-y, 2)]


def rig(cell):
    cw, ch, ax, ay = cell
    out = {
        "comment": "Generated by badminton_game_assets.py. Points are (dx, z) for a player "
                   "facing right: dx along the court from the feet, z height above the floor.",
        "cell": {"w": cw, "h": ch, "ax": ax, "ay": ay},
        "play_depth": PLAY_D,
        "anims": {},
        "characters": {},
        "crowd": {"sheet": "res://assets/sprites/crowd.png", "data": "res://assets/sprites/crowd.json",
                  "x": 0, "y": CROWD_Y},
    }
    for name, (frames, loop, contact) in ANIMS.items():
        out["anims"][name] = {"loop": loop, "contact": -1 if contact is None else contact,
                              "frames": len(frames),
                              "lift": [base.POSES[p]["lift"] for p, _ in frames]}
    for who in CHARACTERS:
        spec = db.PEOPLE[who]
        c = {"face": spec["face"], "sheet": f"res://assets/sprites/{who}.png",
             "data": f"res://assets/sprites/{who}.json", "contact": {}, "hold": {}}
        for name, (frames, _, contact) in ANIMS.items():
            if contact is not None:
                c["contact"][name] = local(who, frames[contact][0], "racket")
            if name in SERVES:   # where the free hand holds the shuttle, per frame
                c["hold"][name] = [local(who, p, "fh") for p, _ in frames]
        out["characters"][who] = c
    return out


# --------------------------------------------------------------------------
# The plan: MCP tool calls for every Aseprite file
# --------------------------------------------------------------------------

def build_plan(game_dir: str) -> list[Call]:
    calls: list[Call] = []
    src = os.path.join(game_dir, "assets", "source")
    sprites = os.path.join(game_dir, "assets", "sprites")
    court_dir = os.path.join(game_dir, "assets", "court")
    cw, ch, ax, ay = cell = cell_geometry()

    def adder(sprite):
        def add(tool, **args):
            calls.append(Call(tool, {"filename": sprite, **args}))
        return add

    # -- players: one sheet each, one tag per animation -------------------------
    frames = frame_list()
    for who in CHARACTERS:
        spr = os.path.join(src, f"{who}.aseprite")
        add = adder(spr)
        calls.append(Call("create_canvas", {"width": cw, "height": ch, "filename": spr}))
        add("rename_layer", layer_name="Layer 1", new_name="player")
        add("add_frames", count=len(frames) - 1, duration_ms=100)
        add("set_frame_duration_all", duration_ms=100)
        for i, (_, pose, ms) in enumerate(frames):
            x, y, rows, legend = render(who, pose).to_rows(ax, ay)
            add("draw_rows", layer_name="player", frame_index=i + 1, x=x, y=y, rows=rows, legend=legend)
            if ms != 100:
                add("set_frame_duration", frame_index=i + 1, duration_ms=ms)
        start = 1
        for name, (fr, _, _) in ANIMS.items():
            add("set_tag", name=name, from_frame=start, to_frame=start + len(fr) - 1, direction="forward")
            start += len(fr)
        add("export_spritesheet", output_filename=os.path.join(sprites, f"{who}.png"),
            sheet_type="horizontal", data_filename=os.path.join(sprites, f"{who}.json"),
            data_format="json-array", list_tags=True)

    # -- shuttle: cork pointing in 32 directions (screen space, y down) ------------
    spr = os.path.join(src, "shuttle.aseprite")
    add = adder(spr)
    c = SHUTTLE_CELL // 2
    calls.append(Call("create_canvas", {"width": SHUTTLE_CELL, "height": SHUTTLE_CELL, "filename": spr}))
    add("rename_layer", layer_name="Layer 1", new_name="shuttle")
    add("add_frames", count=SHUTTLE_DIRS - 1, duration_ms=100)
    for i in range(SHUTTLE_DIRS):
        a = math.radians(i * 360 / SHUTTLE_DIRS)
        x, y, rows, legend = base.shuttle_raster((c, c), (math.cos(a), math.sin(a))).to_rows(0, 0)
        add("draw_rows", layer_name="shuttle", frame_index=i + 1, x=x, y=y, rows=rows, legend=legend)
    add("set_tag", name="directions", from_frame=1, to_frame=SHUTTLE_DIRS, direction="forward")
    add("export_spritesheet", output_filename=os.path.join(sprites, "shuttle.png"),
        sheet_type="horizontal", data_filename=os.path.join(sprites, "shuttle.json"),
        data_format="json-array", list_tags=True)

    # -- crowd: the stands behind the court, idle and cheering --------------------
    spr = os.path.join(src, "crowd.aseprite")
    add = adder(spr)
    calls.append(Call("create_canvas", {"width": W, "height": CROWD_H, "filename": spr}))
    add("rename_layer", layer_name="Layer 1", new_name="crowd")
    add("add_frames", count=sum(n for _, n, _ in CROWD_ANIMS) - 1, duration_ms=100)
    people = crowd_people()
    i = 1
    for tag, n, ms in CROWD_ANIMS:
        add("set_tag", name=tag, from_frame=i, to_frame=i + n - 1, direction="forward")
        for f in range(n):
            x, y, rws, legend = crowd_frame(people, tag, f).to_rows(0, 0)
            add("draw_rows", layer_name="crowd", frame_index=i, x=x, y=y, rows=rws, legend=legend)
            add("set_frame_duration", frame_index=i, duration_ms=ms)
            i += 1
    add("export_spritesheet", output_filename=os.path.join(sprites, "crowd.png"),
        sheet_type="horizontal", data_filename=os.path.join(sprites, "crowd.json"),
        data_format="json-array", list_tags=True)

    # -- court: background, and the net split at the players' depth ---------------
    spr = os.path.join(src, "court.aseprite")
    add = adder(spr)
    calls.append(Call("create_canvas", {"width": W, "height": H, "filename": spr}))
    add("rename_layer", layer_name="Layer 1", new_name="background")
    add("add_layer", layer_name="net_back")
    add("add_layer", layer_name="net_front")

    def rect(layer, x, y, w, h, color):
        add("draw_rectangle_at", layer_name=layer, frame_index=1, x=x, y=y,
            width=w, height=h, color=color, fill=True)

    def line(layer, x1, y1, x2, y2, color):
        add("draw_line_at", layer_name=layer, frame_index=1, x1=x1, y1=y1,
            x2=x2, y2=y2, color=color, thickness=1)

    def rows(layer, frame, raster_or_rows, x=None, y=None, legend=None):
        if isinstance(raster_or_rows, Raster):
            x, y, rws, legend = raster_or_rows.to_rows(0, 0)
        else:
            rws = raster_or_rows
        add("draw_rows", layer_name=layer, frame_index=frame, x=x, y=y, rows=rws, legend=legend)

    pt.draw_background(rect, line, rows)
    draw_hall(rect, rows)
    net, _ = base.net_raster()
    back, front = Raster(), Raster()
    for (x, y), col in net.px.items():
        (front if x <= NET_SPLIT_X else back).px[(x, y)] = col
    rows("net_back", 1, back)
    rows("net_front", 1, front)
    add("export_layers", output_directory=court_dir)
    return calls


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------

class GamePreview(base.Preview):
    """The Pillow stand-in, plus export_layers (one full-canvas PNG per layer)."""

    def t_export_layers(self, filename, output_directory, include_hidden=False):
        os.makedirs(output_directory, exist_ok=True)
        spr = self.s[filename]
        for layer in spr["layers"]:
            self._cel(filename, layer, 1).save(os.path.join(output_directory, f"{layer}.png"))

    def t_export_spritesheet(self, filename, output_filename, **kw):
        super().t_export_spritesheet(filename, output_filename, **kw)
        data_filename = kw.get("data_filename")
        if data_filename:                     # name frames like Aseprite does
            with open(data_filename) as fh:
                data = json.load(fh)
            stem = os.path.splitext(os.path.basename(filename))[0]
            for i, fr in enumerate(data["frames"]):
                fr["filename"] = f"{stem} {i}.aseprite"
            with open(data_filename, "w") as fh:
                json.dump(data, fh, indent=1)


def make_icon(game_dir: str, cell):
    """128 px project icon from the exported red_man sheet (Pillow)."""
    from PIL import Image
    cw, ch, ax, ay = cell
    sheet = Image.open(os.path.join(game_dir, "assets", "sprites", "red_man.png")).convert("RGBA")
    idx = [i for i, (anim, _, _) in enumerate(frame_list()) if anim == "celebrate"][1]
    player = sheet.crop((idx * cw, 0, (idx + 1) * cw, ch))
    icon = Image.new("RGBA", (64, 64), base.rgba(base.C["wall_lo"]))
    for y in range(44, 64):
        for x in range(64):
            icon.putpixel((x, y), base.rgba(base.C["court"]))
    for x in range(64):
        icon.putpixel((x, 52), base.rgba(base.C["line"]))
    icon.alpha_composite(player, (32 - ax, 54 - ay))
    shuttle = Image.open(os.path.join(game_dir, "assets", "sprites", "shuttle.png")).convert("RGBA")
    k = SHUTTLE_DIRS * 3 // 4                           # cork up
    icon.alpha_composite(shuttle.crop((k * SHUTTLE_CELL, 0, (k + 1) * SHUTTLE_CELL, SHUTTLE_CELL)), (44, 2))
    icon.resize((128, 128), Image.NEAREST).save(os.path.join(game_dir, "icon.png"))


def write_rig(game_dir: str, cell):
    path = os.path.join(game_dir, "assets", "rig.json")
    with open(path, "w") as fh:
        json.dump(rig(cell), fh, indent=1)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mcp", help="draw through a running aseprite-mcp server")
    m.add_argument("--mcp-dir", required=True, help="path to the aseprite-mcp checkout")
    m.add_argument("--aseprite", help="Aseprite binary (else ASEPRITE_PATH / the repo's .env)")
    m.add_argument("--game", required=True, help="the Godot project folder")
    m.add_argument("--uv", default="uv", help="uv executable (default: uv on PATH)")
    m.add_argument("--quiet", action="store_true")
    p = sub.add_parser("preview", help="apply the same calls locally with Pillow")
    p.add_argument("--game", required=True)
    j = sub.add_parser("plan", help="write the tool calls as JSON")
    j.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    cell = cell_geometry()
    if a.cmd == "plan":
        calls = build_plan("/ABS/GAME")
        with open(a.out, "w") as fh:
            json.dump([{"tool": c.tool, "arguments": c.args} for c in calls], fh, indent=1)
        print(f"{len(calls)} tool calls -> {a.out}")
        return

    game = os.path.abspath(os.path.expanduser(a.game))
    for sub_dir in ("assets/source", "assets/sprites", "assets/court"):
        os.makedirs(os.path.join(game, sub_dir), exist_ok=True)
    calls = build_plan(game)
    if a.cmd == "mcp":
        asyncio.run(base.run_mcp(calls, os.path.expanduser(a.mcp_dir), a.aseprite, a.uv, a.quiet))
    else:
        pv = GamePreview()
        for c in calls:
            pv.call(c)
        os.rmdir(os.path.join(game, "assets", "source")) if not os.listdir(
            os.path.join(game, "assets", "source")) else None
    print(f"{len(calls)} tool calls")
    print("Wrote:", write_rig(game, cell))
    make_icon(game, cell)
    print("Wrote:", os.path.join(game, "icon.png"))
    print(f"Player cell {cell[0]}x{cell[1]}, anchor ({cell[2]}, {cell[3]})")


if __name__ == "__main__":
    main()
