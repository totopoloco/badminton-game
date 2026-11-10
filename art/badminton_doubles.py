#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.6", "pillow>=10"]
# ///
"""A mixed-doubles point in Aseprite, drawn through aseprite-mcp.

Game point at 14-13 under 3x15 scoring: red (man + woman) against blue
(man + woman). The red woman serves short, the blue man lifts, the red man
jump-smashes, the blue woman blocks, the red woman plays a tight net shot,
the blue woman lifts again, the red man smashes again, the blue man's drive
sits up and the red woman kills it at the net: 15-13, game. Red celebrate
with a high five.

Red attack front-and-back (woman at the net, man at the back); blue defend
side by side. Every player has their own layer.

Uses badminton_rally.py and badminton_point.py (renderer, court, physics,
backends): keep the three files in the same folder.

  uv run badminton_doubles.py mcp --mcp-dir ~/aseprite-mcp --out ~/badminton
  uv run badminton_doubles.py preview --out ./preview
  uv run badminton_doubles.py plan --out ./plan.json
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
from badminton_rally import Call, Raster  # noqa: E402

W, H = base.W, base.H
GROUND, SKEW, NET_X, NET_H = base.GROUND, base.SKEW, base.NET_X, base.NET_H
STEM = "badminton_doubles"
P = base.POSES
add_pose, like = pt.add_pose, pt.like

# --------------------------------------------------------------------------
# Doubles poses (right-handed player facing +x; y up-negative)
# --------------------------------------------------------------------------

add_pose("bh_serve_hold", head=(1, -27), sh=(0, -21), hip=(-1, -12),            # backhand short serve
         fk=(3, -7), fa=(5, -2), bk=(-3, -7), ba=(-5, -2),
         re=(3, -16), rh=(5, -15), ang=70, fe=(4, -17), fh=(9, -15))
add_pose("bh_serve_back", **like("bh_serve_hold", ang=95))
add_pose("bh_serve_contact", **like("bh_serve_hold", ang=10, fh=(6, -19)))
add_pose("bh_serve_follow", **like("bh_serve_hold", re=(4, -17), rh=(7, -17), ang=-15, fh=(5, -19)))
add_pose("net_ready", head=(2, -25), sh=(1, -19), hip=(-1, -11),                 # front player
         fk=(3, -6), fa=(6, -2), bk=(-4, -6), ba=(-6, -2),
         re=(5, -20), rh=(7, -24), ang=-80, fe=(3, -15), fh=(5, -17))
add_pose("net_ready_b", **like("net_ready", head=(2, -24), sh=(1, -18), hip=(-1, -10),
                               fk=(3, -5), bk=(-4, -5), re=(5, -19), rh=(7, -23),
                               fe=(3, -14), fh=(5, -16)))
add_pose("receive", head=(3, -26), sh=(2, -20), hip=(-1, -12),                   # receiving the serve
         fk=(4, -7), fa=(7, -2), bk=(-4, -7), ba=(-7, -2), back_heel=True,
         re=(5, -24), rh=(6, -29), ang=-80, fe=(5, -19), fh=(9, -20))
add_pose("receive_b", **like("receive", head=(3, -25), sh=(2, -19), hip=(-1, -11),
                             re=(5, -23), rh=(6, -28), fe=(5, -18), fh=(9, -19)))
add_pose("drive_prep", head=(1, -26), sh=(0, -20), hip=(-1, -11),                # flat drive
         fk=(3, -6), fa=(6, -2), bk=(-4, -6), ba=(-6, -2),
         re=(-3, -18), rh=(-6, -21), ang=-150, fe=(4, -17), fh=(7, -18))
add_pose("drive_contact", head=(2, -26), sh=(1, -20), hip=(-1, -11),
         fk=(3, -6), fa=(6, -2), bk=(-4, -6), ba=(-6, -2),
         re=(4, -21), rh=(8, -23), ang=-25, fe=(-2, -17), fh=(-4, -14))
add_pose("drive_follow", **like("drive_contact", re=(4, -19), rh=(7, -17), ang=40))
add_pose("high_five", head=(1, -27), sh=(0, -21), hip=(-1, -12),
         fk=(3, -7), fa=(5, -2), bk=(-4, -7), ba=(-6, -2),
         re=(-2, -17), rh=(-3, -13), ang=100, fe=(4, -25), fh=(7, -29))
add_pose("high_five_low", **like("high_five", fe=(4, -24), fh=(8, -27)))
add_pose("hands_hips", head=(1, -27), sh=(0, -21), hip=(-1, -12),
         fk=(3, -7), fa=(4, -2), bk=(-3, -7), ba=(-4, -2),
         re=(4, -17), rh=(1, -13), ang=95, fe=(-4, -17), fh=(-2, -13))
add_pose("hands_hips_b", **like("hands_hips", head=(1, -26)))

CONTACT_POSES = {"bh_serve_contact", "lunge_lift", "jump_contact", "block_contact",
                 "lunge_net", "drive_contact", "kill_contact"}

# --------------------------------------------------------------------------
# The four players. Women are drawn 8% shorter, with a ponytail and a skirt.
# Layers go back to front: each team's man stays further from the viewer.
# --------------------------------------------------------------------------

PEOPLE = {
    "red_man": dict(face=1, scale=1.0, colors=base.PLAYERS["red"]),
    "red_woman": dict(face=1, scale=0.92, ponytail=True, skirt=("#f1f2f6", "#c4c8d3"),
                      colors=dict(shirt=("#d94a4a", "#a23434"), shorts=("#d9a27a", "#ad7552"),
                                  skin=("#d9a27a", "#ad7552"), hair=("#2b2734", "#1b1823"),
                                  sock="#f4f4f4", shoe="#f4f4f4", sole="#d94a4a")),
    "blue_man": dict(face=-1, scale=1.0, colors=base.PLAYERS["blue"]),
    "blue_woman": dict(face=-1, scale=0.92, ponytail=True, skirt=("#25315c", "#18203f"),
                       colors=dict(shirt=("#3f84dc", "#2b5ea6"), shorts=("#f3c7a2", "#d09c77"),
                                   skin=("#f3c7a2", "#d09c77"), hair=("#d8ab52", "#a57f2f"),
                                   sock="#f4f4f4", shoe="#f4f4f4", sole="#3f84dc")),
}
LAYERS = ["red_man", "red_woman", "blue_man", "blue_woman"]
TEAMS = (("red_man", "red_woman"), ("blue_man", "blue_woman"))

JOINTS = ("head", "sh", "hip", "fk", "fa", "bk", "ba", "re", "rh", "fe", "fh")
FLOWING = ("run", "lunge", "jump", "smash_air", "kill_reach", "kill_contact", "celebrate_b", "split")


def scaled_pose(pose_name, s):
    """Pose joints scaled about the feet, with the jump lift applied."""
    p = dict(P[pose_name])
    for k in JOINTS:
        p[k] = (p[k][0] * s, p[k][1] * s - p["lift"])
    return p


def draw_skirt(r: Raster, p, colors):
    hx, hy = p["hip"]
    top, bot = hy - 2.2, hy + 2.6
    y1 = math.ceil(bot)
    for y in range(math.floor(top), y1 + 1):
        t = min(1.0, max(0.0, (y - top) / (bot - top)))
        hw = 2.4 + 1.4 * t
        for x in range(math.floor(hx - hw), math.ceil(hx + hw) + 1):
            if abs(x - hx) <= hw:
                r.px[(x, y)] = colors[1] if y == y1 else colors[0]


def draw_ponytail(r: Raster, head, hair, flowing):
    cx, cy = head
    pts = ([(-3.8, -1.6), (-4.8, -1.8), (-5.8, -1.4), (-6.6, -0.8)] if flowing
           else [(-3.8, -1.2), (-4.5, -0.3), (-4.9, 0.8), (-5.0, 1.9)])
    for i, (dx, dy) in enumerate(pts):
        r.put(cx + dx, cy + dy, hair[1] if i == 0 else hair[0])


def render_person(who, pose_name) -> Raster:
    """Like badminton_rally.render_player, plus scale, skirt and ponytail."""
    spec = PEOPLE[who]
    col, s = spec["colors"], spec["scale"]
    p = scaled_pose(pose_name, s)
    r = Raster()
    if p["racket_behind"]:
        base.draw_racket(r, p)
    base.draw_arm(r, p["sh"], p["fe"], p["fh"], col, shade=True)               # far arm
    base.draw_leg(r, p, p["bk"], p["ba"], col, shade=True)                      # far leg
    r.capsule(p["sh"], base.lerp(p["sh"], p["hip"], 0.8), 2.5 if s == 1 else 2.3, col["shirt"][0])
    back = (p["sh"][0] - 1.6, p["sh"][1] + 1)
    r.capsule(back, (p["hip"][0] - 1.6, p["hip"][1] - 2), 0.9, col["shirt"][1])
    r.capsule((p["hip"][0], p["hip"][1] - 1.5), p["hip"], 2.6, col["shorts"][0])
    base.draw_leg(r, p, p["fk"], p["fa"], col, shade=False)                     # near leg
    if spec.get("skirt"):
        draw_skirt(r, p, spec["skirt"])
    neck_top = (p["head"][0] - 0.5, p["head"][1] + 2.5)
    r.capsule(neck_top, p["sh"], 0.8, col["skin"][1])
    base.draw_head(r, p["head"], col)
    if spec.get("ponytail"):
        draw_ponytail(r, p["head"], col["hair"], pose_name.startswith(FLOWING))
    arm = Raster()                                                              # racket arm on top,
    if not p["racket_behind"]:                                                  # with a contour
        base.draw_racket(arm, p)
    base.draw_arm(arm, p["sh"], p["re"], p["rh"], col, shade=False)
    for (x, y), c in list(r.px.items()):
        if (x, y) not in arm.px and any(n in arm.px for n in
                                        ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))):
            r.px[(x, y)] = base.darken(c, 0.62)
    for k, c in arm.px.items():
        r.set(k, c)
    r.outline(base.OUT, skip=(base.RACKET_STRINGS,))
    if p["smear"]:
        sm = p["smear"]
        pivot = (sm["pivot"][0] * s, sm["pivot"][1] * s - p["lift"])
        for k in range(60, -1, -1):
            t = k / 60
            a = sm["a0"] + (sm["a1"] - sm["a0"]) * t
            alpha = (0x22, 0x3a, 0x5c)[min(2, int(t * 3))]
            for rr in (sm["r"] - 3.0, sm["r"] - 2.0, sm["r"] - 1.0, sm["r"], sm["r"] + 0.8):
                x, y = base.polar(pivot, a, rr)
                r.put(x, y, f"#ffffff{alpha:02x}", only_empty=True)
    return r


# --------------------------------------------------------------------------
# Choreography. X runs along the court, D is the depth row (larger = nearer
# the viewer). Red's right service court is the near half, blue's the far.
# At 14 (even) red serves from its right court, diagonally to blue's right.
# --------------------------------------------------------------------------

RUN = ("run_a", "run_b")
BACK = ("back_a", "back_b")
LOOP = lambda a, b, n: [a, a, b, b] * n                                    # noqa: E731


class Track:
    def __init__(self, who, x, d):
        self.face = PEOPLE[who]["face"]
        self.x, self.d = float(x), float(d)
        self.frames: list[tuple[float, float, str, int]] = []

    def seq(self, *poses, face=None):
        for p in poses:
            self.frames.append((self.x, self.d, p, face or self.face))

    def move(self, x, d, n, gait, face=None):
        x0, d0 = self.x, self.d
        for i in range(1, n + 1):
            e = 0.5 - 0.5 * math.cos(math.pi * i / n)
            self.frames.append((x0 + (x - x0) * e, d0 + (d - d0) * e,
                                gait[(i - 1) % len(gait)], face or self.face))
        self.x, self.d = float(x), float(d)


def choreography():
    rw = Track("red_woman", 66, 91)                     # serves, then holds the net
    rw.seq(*["bh_serve_hold"] * 7, "bh_serve_back")                                # 0-7
    rw.seq("bh_serve_contact")                                                     # 8  SERVE
    rw.seq("bh_serve_follow")                                                      # 9
    rw.move(68, 89, 3, ("net_ready_b", "net_ready", "net_ready_b"))                # 10-12
    rw.seq(*LOOP("net_ready", "net_ready_b", 4), "net_ready", "net_ready")         # 13-30
    rw.seq("net_ready", "net_ready_b", "net_ready_b", "net_ready")                 # 31-34
    rw.seq("net_ready", "net_ready", "net_ready_b", "net_ready_b")                 # 35-38
    rw.move(70, 90, 4, ("lunge_reach", "lunge_reach", "lunge", "lunge"))           # 39-42
    rw.seq("lunge_net")                                                            # 43 NET SHOT
    rw.seq("lunge_net", "lunge", "lunge_reach")                                    # 44-46
    rw.move(72, 89, 4, ("net_ready_b", "net_ready", "net_ready_b", "net_ready"))   # 47-50
    rw.seq("net_ready")                                                            # 51
    rw.move(76, 88, 4, ("net_ready_b", "net_ready", "net_ready_b", "net_ready"))   # 52-55
    rw.seq(*LOOP("net_ready", "net_ready_b", 2))                                   # 56-63
    rw.seq("net_ready", "net_ready_b", "net_ready", "split", "split_land")          # 64-68
    rw.move(78, 88, 1, ("run_a",))                                                 # 69
    rw.move(80, 88, 2, ("kill_reach", "kill_reach2"))                              # 70-71
    rw.seq("kill_contact")                                                         # 72 NET KILL
    rw.seq("kill_follow", "kill_land", "ready_b")                                  # 73-75
    rw.seq("ready_a", face=-1)                                                     # 76 turns round
    rw.move(71, 88, 4, RUN, face=-1)                                               # 77-80
    rw.seq(*["high_five"] * 4, face=-1)                                            # 81-84
    rw.seq(*LOOP("celebrate_b", "celebrate_a", 3), "celebrate_b", "celebrate_b", "celebrate_a")  # 85-99

    rm = Track("red_man", 46, 88)                       # behind the server, then the back court
    rm.seq(*LOOP("ready_b", "ready_a", 2))                                         # 0-7
    rm.seq("ready_b", *LOOP("ready_b", "ready_a", 2), "ready_b")                   # 8-17
    rm.seq("split")                                                                # 18
    rm.move(38, 84, 6, BACK)                                                       # 19-24
    rm.seq("prep", "prep", "crouch", "jump_windup", "jump_windup2", "jump_swing")  # 25-30
    rm.seq("jump_contact")                                                         # 31 JUMP SMASH
    rm.seq("smash_air", "smash_land")                                              # 32-33
    rm.move(42, 85, 4, RUN)                                                        # 34-37
    rm.seq(*LOOP("ready_a", "ready_b", 3), "ready_b", "split")                     # 38-51
    rm.move(34, 82, 6, BACK)                                                       # 52-57
    rm.seq("prep", "prep", "crouch", "jump_windup", "jump_windup2", "jump_swing")  # 58-63
    rm.seq("jump_contact")                                                         # 64 JUMP SMASH
    rm.seq("smash_air", "smash_land")                                              # 65-66
    rm.move(42, 85, 4, RUN)                                                        # 67-70
    rm.seq("ready_b", "ready_b", "ready_a", "ready_a", "ready_a")                  # 71-75
    rm.move(58, 88, 5, RUN)                                                        # 76-80
    rm.seq(*["high_five_low"] * 4)                                                 # 81-84
    rm.seq(*LOOP("celebrate_a", "celebrate_b", 3), "celebrate_a", "celebrate_a", "celebrate_b")  # 85-99

    bm = Track("blue_man", 134, 80)                     # receives in blue's right (far) court
    bm.seq(*LOOP("receive", "receive_b", 2), "receive")                            # 0-8
    bm.seq("receive", "receive_b", "receive_b", "receive")                         # 9-12
    bm.move(132, 80, 2, RUN)                                                       # 13-14
    bm.move(129, 80, 3, ("lunge_reach", "lunge", "lunge"))                         # 15-17
    bm.seq("lunge_lift")                                                           # 18 LIFT
    bm.seq("lift_follow", "lift_follow")                                           # 19-20
    bm.move(135, 82, 5, BACK)                                                      # 21-25
    bm.seq("defend", "defend", "defend", "defend", "split", "defend")              # 26-31
    bm.seq(*LOOP("defend", "split_land", 4), "defend", "defend", "defend")         # 32-50
    bm.seq(*["defend"] * 12, "split", "defend")                                    # 51-64
    bm.move(134, 82, 3, ("drive_prep",) * 3)                                       # 65-67
    bm.seq("drive_contact")                                                        # 68 DRIVE
    bm.seq("drive_follow", "defend", "defend", "defend")                           # 69-72
    bm.move(131, 84, 3, ("lunge_reach", "lunge_reach", "lunge"))                   # 73-75 too late
    bm.seq(*LOOP("dejected_a", "dejected_b", 6))                                   # 76-99

    bw = Track("blue_woman", 152, 90)                   # partner, then the near side in defence
    bw.seq(*LOOP("ready_a", "ready_b", 4), "ready_a", "ready_a", "ready_a")        # 0-18
    bw.move(152, 92, 4, BACK)                                                      # 19-22
    bw.seq(*["defend"] * 7, "split", "defend")                                     # 23-31
    bw.seq("block_prep", "block_prep", "block_prep")                               # 32-34
    bw.seq("block_contact")                                                        # 35 BLOCK
    bw.seq("block_follow", "block_follow", "ready_b", "ready_b", "ready_a", "ready_a",
           "split", "split_land")                                                  # 36-43
    bw.move(138, 90, 3, RUN)                                                       # 44-46
    bw.move(128, 90, 4, ("lunge_reach", "lunge_reach", "lunge", "lunge"))          # 47-50
    bw.seq("lunge_lift")                                                           # 51 LIFT
    bw.seq("lift_follow", "lift_follow")                                           # 52-53
    bw.move(152, 91, 5, BACK)                                                      # 54-58
    bw.seq("defend", "defend", "defend", "defend", "split", *["defend"] * 9)       # 59-72
    bw.move(149, 89, 3, ("lunge_reach", "lunge_reach", "lunge"))                   # 73-75
    bw.seq(*LOOP("hands_hips", "hands_hips_b", 6))                                 # 76-99
    return {"red_woman": rw.frames, "red_man": rm.frames,
            "blue_man": bm.frames, "blue_woman": bw.frames}


# (name, hitter, contact frame, impact: 0 soft / 1 normal / 2 hard)
SHOTS = [
    ("serve", "red_woman", 8, 0), ("lift", "blue_man", 18, 1), ("jump_smash", "red_man", 31, 2),
    ("block", "blue_woman", 35, 0), ("net_shot", "red_woman", 43, 0), ("lift_2", "blue_woman", 51, 1),
    ("jump_smash_2", "red_man", 64, 2), ("drive", "blue_man", 68, 1), ("net_kill", "red_woman", 72, 2),
]
LAND_FRAME = 75
LANDING = (124.0, 86.0)            # the kill lands between the two blue defenders
FRAMES = 100


def local_point(who, pose_name, key="racket"):
    p = scaled_pose(pose_name, PEOPLE[who]["scale"])
    return base.racket_head_centre(p) if key == "racket" else p[key]


def world_point(tracks, who, f, key="racket"):
    x, d, pname, face = tracks[who][f]
    lx, ly = local_point(who, pname, key)
    return x + face * lx, d, -ly


def flights(tracks):
    out = []
    for k, (name, who, f0, impact) in enumerate(SHOTS):
        X0, D0, Z0 = world_point(tracks, who, f0)
        if k + 1 < len(SHOTS):
            nxt = SHOTS[k + 1]
            X1, D1, Z1 = world_point(tracks, nxt[1], nxt[2])
            f1 = nxt[2]
        else:
            (X1, D1), Z1, f1 = LANDING, 0.0, LAND_FRAME
        T = f1 - f0
        vx, vy = pt.solve((X0, -Z0), (X1, -Z1), T)
        pts = [(x, D0 + (D1 - D0) * i / pt.SUB / T, -y, svx, -svy)
               for i, (x, y, svx, svy) in enumerate(pt.fly(X0, -Z0, vx, vy, T))]
        net_z = None
        for a, b in zip(pts, pts[1:]):
            if (a[0] - NET_X) * (b[0] - NET_X) <= 0 and a[0] != b[0]:
                net_z = a[2] + (b[2] - a[2]) * (NET_X - a[0]) / (b[0] - a[0])
                break
        out.append(dict(name=name, hitter=who, f0=f0, f1=f1, T=T, impact=impact, pts=pts,
                        net_z=net_z, apex=max(p[2] for p in pts), speed0=math.hypot(vx, vy)))
    return out


def check(tracks, fl):
    problems = []
    for name, who, f, _ in SHOTS:
        if tracks[who][f][2] not in CONTACT_POSES:
            problems.append(f"{name}: {who} is in pose {tracks[who][f][2]} at frame {f}")
    for man, woman in TEAMS:                     # layer order: the man is drawn first
        for f in range(FRAMES):
            if tracks[woman][f][1] < tracks[man][f][1]:
                problems.append(f"frame {f}: {woman} is behind {man} (layer order)")
                break
    for who, frames in tracks.items():
        if len(frames) != FRAMES:
            problems.append(f"{who}: {len(frames)} frames")
        for x, d, _, _ in frames:
            sx, _ = pt.screen(x, d)
            if not 12 <= sx <= W - 12:
                problems.append(f"{who} leaves the canvas at x={sx:.0f}")
                break
    for s in fl:
        if s["net_z"] is None or s["net_z"] < NET_H + 1.5:
            problems.append(f"{s['name']}: crosses the net at Z={s['net_z']}")
        for x, d, z, *_ in s["pts"]:
            sx, sy = pt.screen(x, d, z)
            if sy < 3 or not (2 <= sx <= W - 3):
                problems.append(f"{s['name']}: leaves the canvas at ({sx:.0f},{sy:.0f})")
                break
    return problems


# --------------------------------------------------------------------------
# Shuttle per frame
# --------------------------------------------------------------------------

def shuttle_states(tracks, fl):
    st: list[dict] = [None] * FRAMES                                # type: ignore[list-item]
    server, serve_f = SHOTS[0][1], SHOTS[0][2]
    face = PEOPLE[server]["face"]
    held_dir = (-0.6 * face, 0.8)                                   # cork towards the racket face
    for f in range(serve_f):
        X, D, Z = world_point(tracks, server, f, "fh")
        st[f] = dict(X=X + 0.5 * face, D=D, Z=Z - 2.0, dir=held_dir, t=None)
    for k, s in enumerate(fl):
        vd = (s["pts"][-1][1] - s["pts"][0][1]) / s["T"]
        for t in range(s["T"]):
            X, D, Z, vX, vZ = s["pts"][t * pt.SUB]
            if t == 0:
                if k == 0:
                    d = held_dir
                else:
                    pv = fl[k - 1]
                    pvd = (pv["pts"][-1][1] - pv["pts"][0][1]) / pv["T"]
                    d = pt.screen_dir(pv["pts"][-1][3], pvd, pv["pts"][-1][4])
            else:
                d = pt.screen_dir(vX, vd, vZ)
                if s["name"] == "net_shot" and t <= 5:              # spinning net shot tumbles
                    d = pt.rotate(d, 80 * t)
            st[s["f0"] + t] = dict(X=X, D=D, Z=Z, dir=d, t=t)
    X, D, _, vX, vZ = fl[-1]["pts"][-1]
    side = 1.0 if vX > 0 else -1.0
    st[LAND_FRAME] = dict(X=X, D=D, Z=0.0, dir=pt.screen_dir(vX, 0, vZ), t=None, landed=0)
    st[LAND_FRAME + 1] = dict(X=X + 2.5 * side, D=D, Z=2.5, dir=(side, 0.2), t=None, landed=1)
    for f in range(LAND_FRAME + 2, FRAMES):
        st[f] = dict(X=X + 4 * side, D=D, Z=0.6, dir=(side, 0.35), t=None, landed=2)
    return st


# --------------------------------------------------------------------------
# Score
# --------------------------------------------------------------------------

DIGITS = {**base.DIGITS,
          "3": ["###", "..#", "###", "..#", "###"],
          "4": ["#.#", "#.#", "###", "..#", "..#"],
          "5": ["###", "#..", "###", "..#", "###"]}


def score_raster(red_pts: str, blue_pts: str, red_colour: str) -> Raster:
    r, sbx = Raster(), pt.SBX
    for ch, dx, colour in ((red_pts[0], 5, red_colour), (red_pts[1], 9, red_colour),
                           (blue_pts[0], 24, base.C["blue_digit"]), (blue_pts[1], 28, base.C["blue_digit"])):
        for yy, row in enumerate(DIGITS[ch]):
            for xx, c in enumerate(row):
                if c == "#":
                    r.put(sbx + dx + xx, 16 + yy, colour)
    r.put(sbx + 17, 17, base.C["colon"])
    r.put(sbx + 17, 20, base.C["colon"])
    return r


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------

HIGH_FIVE = 83                                                      # hands meet


def frame_durations():
    d = [80] * FRAMES
    for f in range(SHOTS[0][2] - 1):
        d[f] = 110
    for _, _, f, impact in SHOTS:
        d[f] = (100, 120, 180)[impact]
    d[LAND_FRAME] = 220
    d[LAND_FRAME + 1] = 120
    for f in range(LAND_FRAME + 2, FRAMES):
        d[f] = 110
    d[HIGH_FIVE] = 180
    d[FRAMES - 1] = 700
    return d


def build_plan(sprite: str, out_dir: str) -> list[Call]:
    calls: list[Call] = []

    def add(tool, **args):
        calls.append(Call(tool, {"filename": sprite, **args}))

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

    tracks = choreography()
    fl = flights(tracks)
    problems = check(tracks, fl)
    if problems:
        raise SystemExit("choreography problems:\n  " + "\n  ".join(problems))
    shuttle = shuttle_states(tracks, fl)
    contacts = {f: impact for _, _, f, impact in SHOTS}

    # sprite, layers (players back to front), frames
    calls.append(Call("create_canvas", {"width": W, "height": H, "filename": sprite}))
    add("rename_layer", layer_name="Layer 1", new_name="background")
    for name in ("score", "net", "shadows", *[f"player_{w}" for w in LAYERS], "shuttle"):
        add("add_layer", layer_name=name)
    add("add_frames", count=FRAMES - 1, duration_ms=80)
    add("set_frame_duration_all", duration_ms=80)

    # static layers
    pt.draw_background(rect, line, rows)
    net, near_post = base.net_raster()
    rows("net", 1, net)
    add("propagate_cels", layer_names=["background", "net"], source_frame=1,
        start_frame=1, end_frame=FRAMES)

    # score: 14-13 (game point) until the shuttle is down, then 15-13 blinking
    won = LAND_FRAME + 2
    rows("score", 1, score_raster("14", "13", base.C["red_digit"]))
    add("propagate_cels", layer_names=["score"], source_frame=1, start_frame=1, end_frame=won)
    rows("score", won + 1, score_raster("15", "13", base.C["red_digit"]))
    add("propagate_cels", layer_names=["score"], source_frame=won + 1,
        start_frame=won + 1, end_frame=FRAMES)
    for f in range(won, FRAMES):
        if (f - won) // 2 % 2 == 1:
            rows("score", f + 1, score_raster("15", "13", pt.RED_DIM))

    prev = None
    for f in range(FRAMES):
        fi = f + 1
        sh = Raster()
        placed = {}
        for who in LAYERS:
            X, D, pname, face = tracks[who][f]
            sx, sy = pt.screen(X, D)
            rx, ry = math.floor(sx + 0.5), math.floor(sy + 0.5)
            placed[who] = (rx, ry, pname, face)
            hw = (5.5 - 0.3 * P[pname]["lift"]) * PEOPLE[who]["scale"]
            for x in range(math.floor(rx - hw), math.ceil(rx + hw) + 1):
                for y in (ry - 1, ry, ry + 1):
                    if ((x - rx) / hw) ** 2 + ((y - ry) / 1.4) ** 2 <= 1.0:
                        sh.put(x, y, base.SHADOW)
        s = shuttle[f]
        fx, fy = pt.screen(s["X"], s["D"], 0)
        if s["Z"] > 1:
            w = 2 if s["Z"] < 25 else 1
            for x in range(round(fx) - w, round(fx) + w + 1):
                sh.put(x, round(fy) + 1, base.SHADOW)
        for k in near_post & set(sh.px):
            del sh.px[k]
        rows("shadows", fi, sh)

        for who in LAYERS:
            rx, ry, pname, face = placed[who]
            r = render_person(who, pname)
            if face < 0:
                r = r.mirrored()
            x, y, rws, legend = r.to_rows(rx, ry)
            rows(f"player_{who}", fi, rws, x=x, y=y, legend=legend)

        sr, prev = pt.shuttle_raster(s, prev if s.get("t") else None, contacts.get(f))
        if f == HIGH_FIVE:                                           # a small spark on the high five
            hx, hd, hz = world_point(tracks, "red_man", f, "fh")
            cx, cy = (round(v) for v in pt.screen(hx, hd, hz))
            for dx, dy in ((0, -3), (-3, 0), (3, 0), (-2, -2), (2, -2)):
                sr.put(cx + dx, cy + dy, pt.FLASH_SOFT, only_empty=True)
        rows("shuttle", fi, sr)

    # timing and tags
    for f, ms in enumerate(frame_durations()):
        if ms != 80:
            add("set_frame_duration", frame_index=f + 1, duration_ms=ms)
    bounds = [f for _, _, f, _ in SHOTS] + [LAND_FRAME]
    starts = [0] + bounds[1:]
    for (name, *_), a, b in zip(SHOTS, starts, bounds[1:]):
        add("set_tag", name=name, from_frame=a + 1, to_frame=b, direction="forward")
    add("set_tag", name="game", from_frame=LAND_FRAME + 1, to_frame=FRAMES, direction="forward")

    # exports
    stem = os.path.join(out_dir, STEM)
    add("export_animation", output_filename=stem + ".gif", scale=4)
    add("export_spritesheet", output_filename=stem + "_sheet.png", sheet_type="rows",
        data_filename=stem + "_sheet.json", scale=1, list_tags=True)
    kill = next(f for n, _, f, _ in SHOTS if n == "net_kill")
    add("export_frame", frame_index=kill + 1, output_filename=stem + "_kill.png", scale=4)
    return calls


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mcp", help="draw through a running aseprite-mcp server")
    m.add_argument("--mcp-dir", required=True, help="path to the aseprite-mcp checkout")
    m.add_argument("--aseprite", help="Aseprite binary (else ASEPRITE_PATH / the repo's .env)")
    m.add_argument("--out", required=True, help="output directory")
    m.add_argument("--uv", default="uv", help="uv executable (default: uv on PATH)")
    m.add_argument("--quiet", action="store_true")
    p = sub.add_parser("preview", help="apply the same calls locally with Pillow")
    p.add_argument("--out", required=True)
    j = sub.add_parser("plan", help="write the tool calls as JSON")
    j.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "plan":
        calls = build_plan(f"/ABS/PATH/{STEM}.aseprite", "/ABS/PATH")
        with open(a.out, "w") as fh:
            json.dump([{"tool": c.tool, "arguments": c.args} for c in calls], fh, indent=1)
        print(f"{len(calls)} tool calls -> {a.out}")
        return
    out = os.path.abspath(os.path.expanduser(a.out))
    os.makedirs(out, exist_ok=True)
    calls = build_plan(os.path.join(out, f"{STEM}.aseprite"), out)
    counts: dict[str, int] = {}
    for c in calls:
        counts[c.tool] = counts.get(c.tool, 0) + 1
    if a.cmd == "preview":
        pv = base.Preview()
        for c in calls:
            pv.call(c)
    else:
        mcp_dir = os.path.abspath(os.path.expanduser(a.mcp_dir))
        aseprite = os.path.abspath(os.path.expanduser(a.aseprite)) if a.aseprite else None
        asyncio.run(base.run_mcp(calls, mcp_dir, aseprite, a.uv, a.quiet))
    print(f"{len(calls)} tool calls: " + ", ".join(f"{k} x{v}" for k, v in counts.items()))
    print("Wrote:", *sorted(n for n in os.listdir(out) if n.startswith(STEM)), sep="\n  ")


if __name__ == "__main__":
    main()
