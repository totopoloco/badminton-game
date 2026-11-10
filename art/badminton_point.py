#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.6", "pillow>=10"]
# ///
"""A full badminton point in Aseprite, drawn through aseprite-mcp.

Blue serves high, red clears, blue drops, red plays a net shot, blue lifts,
red jump-smashes, blue blocks and red kills at the net: 21-19, game.
The players split-step, chassé back, run, lunge, jump and celebrate; every
shot flies with air drag (fast off the racket, steep fall), the net shot
tumbles over the tape and the winner hits the floor.

Uses badminton_rally.py (renderer, court, backends): keep both files in the
same folder.

  uv run badminton_point.py mcp --mcp-dir ~/aseprite-mcp --out ~/badminton
  uv run badminton_point.py preview --out ./preview
  uv run badminton_point.py plan --out ./plan.json
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
from badminton_rally import Call, Raster, pose  # noqa: E402

W, H = base.W, base.H
GROUND, SKEW, NET_X, NET_H = base.GROUND, base.SKEW, base.NET_X, base.NET_H
STEM = "badminton_point"

# --------------------------------------------------------------------------
# Poses (right-handed player facing +x, root = ground under the body,
# y up-negative). Added to the shared pose table used by the renderer.
# --------------------------------------------------------------------------

P = base.POSES


def add_pose(name, **kw):
    P[name] = pose(**kw)


def like(name, **kw):
    """A pose derived from an existing one."""
    return {**P[name], **kw}


UP = dict(re=(2, -25), rh=(2, -30), ang=-95)                  # racket raised, moving back
add_pose("run_a", head=(2, -27), sh=(1, -21), hip=(0, -12),
         fk=(4, -7), fa=(7, -2), bk=(-3, -8), ba=(-6, -3), back_heel=True,
         re=(4, -17), rh=(7, -21), ang=-70, fe=(-2, -17), fh=(-4, -13))
add_pose("run_b", head=(2, -28), sh=(1, -22), hip=(0, -13),
         fk=(2, -8), fa=(1, -2), bk=(3, -10), ba=(0, -6),
         re=(4, -18), rh=(7, -22), ang=-70, fe=(2, -18), fh=(5, -16))
add_pose("back_a", head=(0, -27), sh=(0, -21), hip=(-1, -12),
         fk=(3, -7), fa=(4, -2), bk=(-5, -8), ba=(-8, -2),
         fe=(3, -24), fh=(6, -27), **UP)
add_pose("back_b", head=(0, -27), sh=(0, -21), hip=(-1, -12), lift=1,
         fk=(1, -7), fa=(1, -2), bk=(-3, -7), ba=(-3, -2),
         fe=(3, -24), fh=(6, -27), **UP)
add_pose("split", head=(1, -26), sh=(0, -20), hip=(-1, -11), lift=2,
         fk=(3, -6), fa=(6, -2), bk=(-5, -6), ba=(-7, -2),
         re=(3, -16), rh=(6, -19), ang=-70, fe=(-1, -15), fh=(3, -14))
add_pose("split_land", head=(1, -25), sh=(0, -19), hip=(-1, -10),
         fk=(3, -5), fa=(6, -2), bk=(-5, -5), ba=(-7, -2),
         re=(3, -15), rh=(6, -18), ang=-70, fe=(-1, -14), fh=(3, -13))
add_pose("crouch", head=(0, -25), sh=(-1, -19), hip=(-1, -10),
         fk=(3, -5), fa=(5, -2), bk=(-4, -5), ba=(-6, -2),
         fe=(2, -23), fh=(5, -27), re=(-4, -21), rh=(-6, -26), ang=-95)

TUCK = dict(fk=(3, -8), fa=(2, -3), bk=(-3, -8), ba=(-6, -4))
add_pose("jump_windup", **like("windup", lift=4, **TUCK))
add_pose("jump_windup2", **like("windup", lift=6, head=(-2, -27), **TUCK))
add_pose("jump_swing", **like("swing", lift=7, back_heel=False,
                              fk=(2, -8), fa=(0, -3), bk=(-2, -8), ba=(-4, -3)))
add_pose("jump_contact", head=(0, -28), sh=(0, -22), hip=(0, -12), lift=7,
         re=(2, -27), rh=(4, -32), ang=-60, fe=(2, -18), fh=(4, -15),
         fk=(1, -8), fa=(-2, -4), bk=(3, -9), ba=(5, -5))
add_pose("smash_air", **like("follow", lift=3, fk=(3, -8), fa=(4, -4), bk=(-2, -8), ba=(-4, -4)))
add_pose("smash_land", **like("follow", head=(3, -25), sh=(2, -19), hip=(0, -11),
                              fk=(4, -6), fa=(6, -2), bk=(-3, -6), ba=(-5, -2)))

AIR = dict(fk=(3, -8), fa=(4, -3), bk=(-3, -8), ba=(-5, -3))
add_pose("kill_reach", head=(1, -27), sh=(0, -21), hip=(0, -12), lift=2,
         re=(2, -26), rh=(4, -31), ang=-70, fe=(3, -24), fh=(6, -26), **AIR)
add_pose("kill_reach2", **like("kill_reach", lift=3))
add_pose("kill_contact", head=(1, -27), sh=(0, -21), hip=(0, -12), lift=3,
         re=(3, -25), rh=(6, -29), ang=-40, fe=(2, -17), fh=(4, -15), **AIR)
add_pose("kill_follow", head=(2, -26), sh=(1, -20), hip=(0, -12), lift=1,
         re=(4, -17), rh=(7, -14), ang=25, fe=(-2, -17), fh=(-4, -14),
         fk=(3, -7), fa=(5, -2), bk=(-3, -7), ba=(-5, -2))
add_pose("kill_land", **like("kill_follow", lift=0))

STANCE = dict(fk=(3, -7), fa=(5, -2), bk=(-4, -7), ba=(-6, -2))
add_pose("serve_hold", head=(1, -27), sh=(0, -21), hip=(-1, -12), **STANCE,
         fe=(4, -18), fh=(8, -17), re=(-3, -17), rh=(-6, -14), ang=160)
add_pose("serve_swing", head=(1, -27), sh=(0, -21), hip=(-1, -12), **STANCE,
         fe=(3, -18), fh=(6, -21), re=(-1, -16), rh=(0, -12), ang=125)
add_pose("serve_contact", head=(2, -27), sh=(1, -21), hip=(0, -12), **STANCE, back_heel=True,
         fe=(3, -18), fh=(4, -22), re=(3, -16), rh=(4, -12), ang=30)
add_pose("serve_follow", head=(2, -27), sh=(1, -21), hip=(0, -12), back_heel=True,
         fk=(3, -7), fa=(5, -2), bk=(-3, -7), ba=(-5, -3),
         fe=(0, -17), fh=(-3, -15), re=(4, -21), rh=(6, -26), ang=-80)

LUNGE = dict(head=(6, -21), sh=(5, -16), hip=(1, -9),
             fk=(6, -5), fa=(9, -2), bk=(-4, -5), ba=(-9, -2),
             fe=(2, -14), fh=(-2, -12))
add_pose("lunge_reach", head=(4, -24), sh=(3, -19), hip=(0, -11),
         fk=(4, -6), fa=(7, -2), bk=(-3, -7), ba=(-6, -3), back_heel=True,
         re=(6, -16), rh=(10, -17), ang=-30, fe=(1, -15), fh=(-2, -13))
add_pose("lunge", **LUNGE, re=(9, -14), rh=(13, -15), ang=-15)
add_pose("lunge_net", **LUNGE, re=(9, -15), rh=(12, -18), ang=-35)
add_pose("lunge_lift", **LUNGE, re=(9, -14), rh=(12, -13), ang=-10)
add_pose("lift_follow", **LUNGE, re=(8, -19), rh=(9, -24), ang=-80)

DEFEND = dict(head=(2, -24), sh=(1, -18), hip=(-1, -10),
              fk=(3, -6), fa=(6, -2), bk=(-5, -6), ba=(-7, -2),
              fe=(-2, -14), fh=(0, -11))
add_pose("defend", **DEFEND, re=(5, -15), rh=(8, -17), ang=-55)
add_pose("block_prep", **DEFEND, re=(5, -15), rh=(9, -16), ang=-50)
add_pose("block_contact", **DEFEND, re=(5, -15), rh=(9, -15), ang=-45)
add_pose("block_follow", **DEFEND, re=(5, -16), rh=(10, -17), ang=-40)

add_pose("celebrate_a", head=(1, -27), sh=(0, -21), hip=(-1, -12), **STANCE,
         re=(1, -26), rh=(2, -31), ang=-85, fe=(3, -18), fh=(4, -23))
add_pose("celebrate_b", head=(1, -28), sh=(0, -22), hip=(-1, -13), lift=3,
         fk=(3, -9), fa=(3, -4), bk=(-3, -9), ba=(-4, -4),
         re=(2, -27), rh=(3, -32), ang=-80, fe=(-2, -26), fh=(-4, -30))
add_pose("dejected_a", head=(5, -21), sh=(3, -17), hip=(-1, -12),
         fk=(3, -7), fa=(4, -2), bk=(-3, -7), ba=(-4, -2),
         re=(5, -12), rh=(5, -8), ang=60, fe=(3, -13), fh=(4, -9))
add_pose("dejected_b", **like("dejected_a", head=(5, -20)))

CONTACT_POSES = {"serve_contact", "contact", "lunge_net", "lunge_lift",
                 "jump_contact", "block_contact", "kill_contact"}


# --------------------------------------------------------------------------
# Choreography: per-frame (X, D, pose) for each player. X runs along the
# court (screen x at the players' reference depth), D is the depth row on the
# floor (larger = nearer the viewer). Red faces +x, blue faces -x.
# --------------------------------------------------------------------------

RUN = ("run_a", "run_b")
BACK = ("back_a", "back_b")


class Track:
    def __init__(self, x, d):
        self.x, self.d = float(x), float(d)
        self.frames: list[tuple[float, float, str]] = []

    def seq(self, *poses):
        for p in poses:
            self.frames.append((self.x, self.d, p))

    def move(self, x, d, n, gait):
        """Travel to (x, d) over n frames, cycling through the gait poses."""
        x0, d0 = self.x, self.d
        for i in range(1, n + 1):
            e = 0.5 - 0.5 * math.cos(math.pi * i / n)          # ease in and out
            self.frames.append((x0 + (x - x0) * e, d0 + (d - d0) * e, gait[(i - 1) % len(gait)]))
        self.x, self.d = float(x), float(d)


def choreography():
    red = Track(60, 86)
    red.seq(*["ready_a", "ready_a", "ready_b", "ready_b"] * 2)                 # 0-7
    red.seq("split")                                                          # 8   blue serves
    red.move(30, 85, 7, BACK)                                                 # 9-15
    red.seq("prep", "prep", "prep", "prep", "prep", "windup", "swing")        # 16-22
    red.seq("contact")                                                        # 23  CLEAR
    red.seq("follow", "follow", "recover")                                    # 24-26
    red.move(56, 87, 6, RUN)                                                  # 27-32
    red.seq("ready_a", "ready_b", "split", "split_land")                      # 33-36
    red.move(64, 86, 4, RUN)                                                  # 37-40
    red.move(70, 84, 4, ("lunge_reach", "lunge_reach", "lunge", "lunge"))     # 41-44
    red.seq("lunge_net")                                                      # 45  NET SHOT
    red.seq("lunge_net", "lunge")                                             # 46-47
    red.move(56, 87, 5, BACK)                                                 # 48-52
    red.seq("split", "split_land")                                            # 53-54
    red.move(34, 86, 7, BACK)                                                 # 55-61
    red.seq("prep", "prep", "crouch", "jump_windup", "jump_windup2", "jump_swing")  # 62-67
    red.seq("jump_contact")                                                   # 68  JUMP SMASH
    red.seq("smash_air", "smash_land")                                        # 69-70
    red.move(76, 87, 8, RUN)                                                  # 71-78
    red.move(78, 87, 2, ("kill_reach", "kill_reach2"))                        # 79-80
    red.seq("kill_contact")                                                   # 81  NET KILL
    red.seq("kill_follow", "kill_land", "ready_b", "ready_b")                 # 82-85
    red.seq(*["celebrate_a", "celebrate_a", "celebrate_b", "celebrate_b"] * 3,
            "celebrate_a", "celebrate_a")                                     # 86-99

    blue = Track(130, 90)
    blue.seq(*["serve_hold"] * 7, "serve_swing")                              # 0-7
    blue.seq("serve_contact")                                                 # 8   SERVE
    blue.seq("serve_follow", "serve_follow")                                  # 9-10
    blue.move(136, 88, 3, BACK)                                               # 11-13
    blue.seq(*["ready_a", "ready_a", "ready_b", "ready_b"] * 2)               # 14-21
    blue.seq("split", "split_land")                                           # 22-23
    blue.move(160, 88, 7, BACK)                                               # 24-30
    blue.seq("prep", "prep", "prep", "windup", "swing")                       # 31-35
    blue.seq("contact")                                                       # 36  DROP
    blue.seq("follow", "recover")                                             # 37-38
    blue.move(140, 88, 4, RUN)                                                # 39-42
    blue.seq("ready_b", "split", "split_land")                                # 43-45
    blue.move(134, 87, 4, RUN)                                                # 46-49
    blue.move(128, 86, 4, ("lunge_reach", "lunge_reach", "lunge", "lunge"))   # 50-53
    blue.seq("lunge_lift")                                                    # 54  LIFT
    blue.seq("lift_follow", "lift_follow")                                    # 55-56
    blue.move(138, 88, 5, BACK)                                               # 57-61
    blue.seq("defend", "defend", "defend", "defend", "defend", "split", "defend")  # 62-68
    blue.move(142, 90, 3, ("block_prep",) * 3)                                # 69-71
    blue.seq("block_contact")                                                 # 72  BLOCK
    blue.seq("block_follow", "block_follow")                                  # 73-74
    blue.seq("ready_b", "ready_b", "ready_a", "ready_a", "ready_b", "split")  # 75-80
    blue.move(136, 89, 3, ("lunge_reach", "lunge_reach", "lunge"))            # 81-83 too late
    blue.seq("lunge", "lunge")                                                # 84-85
    blue.seq(*["dejected_a", "dejected_a", "dejected_b", "dejected_b"] * 3,
             "dejected_a", "dejected_a")                                      # 86-99
    return {"red": red.frames, "blue": blue.frames}


# (name, hitter, contact frame, impact: 0 soft / 1 normal / 2 hard)
SHOTS = [
    ("serve", "blue", 8, 1), ("clear", "red", 23, 1), ("drop", "blue", 36, 0),
    ("net_shot", "red", 45, 0), ("lift", "blue", 54, 1), ("jump_smash", "red", 68, 2),
    ("block", "blue", 72, 0), ("net_kill", "red", 81, 2),
]
LAND_FRAME = 84
LANDING = (118.0, 91.0)            # where the kill hits the floor (X, D)
FRAMES = 100


def facing(name):
    return 1 if name == "red" else -1


def local_point(pose_name, key):
    """A joint (or 'racket' = racket head centre) in local coords, lift applied."""
    p = P[pose_name]
    x, y = base.racket_head_centre(p) if key == "racket" else p[key]
    return x, y - p["lift"]


def world_point(tracks, who, f, key="racket"):
    """3D (X, D, Z) of a player's racket head or joint at frame f."""
    x, d, pname = tracks[who][f]
    lx, ly = local_point(pname, key)
    return x + facing(who) * lx, d, -ly


def screen(x, d, z=0.0):
    """Project a court point (X along the court, depth row D, height Z)."""
    return x + (GROUND - d) * SKEW, d - z


# --------------------------------------------------------------------------
# Shuttle physics: gravity + quadratic drag in the vertical plane along the
# court, depth interpolated; solved per shot to meet the next racket.
# --------------------------------------------------------------------------

GRAVITY, DRAG, SUB = base.GRAVITY, base.DRAG, 40


def fly(x0, y0, vx, vy, frames, sub=SUB):
    """(x, y-down) samples every 1/sub frame for `frames` frames."""
    x, y, out = x0, y0, [(x0, y0, vx, vy)]
    dt = 1.0 / sub
    for _ in range(frames * sub):
        sp = math.hypot(vx, vy)
        vx += -DRAG * sp * vx * dt
        vy += (GRAVITY - DRAG * sp * vy) * dt
        x += vx * dt
        y += vy * dt
        out.append((x, y, vx, vy))
    return out


def solve(p0, p1, frames):
    """Launch velocity (vx, vy) reaching p1 from p0 in exactly `frames` frames."""
    (x0, y0), (x1, y1) = p0, p1
    v = [(x1 - x0) / frames * 2.0, (y1 - y0) / frames - 0.5 * GRAVITY * frames]
    for _ in range(200):
        x, y = fly(x0, y0, *v, frames)[-1][:2]
        ex, ey = x - x1, y - y1
        if abs(ex) < 1e-4 and abs(ey) < 1e-4:
            return v
        h = 1e-5
        xa, ya = fly(x0, y0, v[0] + h, v[1], frames)[-1][:2]
        xb, yb = fly(x0, y0, v[0], v[1] + h, frames)[-1][:2]
        j = [[(xa - x) / h, (xb - x) / h], [(ya - y) / h, (yb - y) / h]]
        det = j[0][0] * j[1][1] - j[0][1] * j[1][0]
        dx = (j[1][1] * ex - j[0][1] * ey) / det
        dy = (-j[1][0] * ex + j[0][0] * ey) / det
        step = 1.0
        while step > 1e-3:                                     # damped Newton
            cand = [v[0] - step * dx, v[1] - step * dy]
            cx, cy = fly(x0, y0, *cand, frames)[-1][:2]
            if math.hypot(cx - x1, cy - y1) < math.hypot(ex, ey):
                v = cand
                break
            step /= 2
        else:
            break
    raise RuntimeError(f"no trajectory from {p0} to {p1} in {frames} frames")


def flights(tracks):
    """Solve every shot; returns a list of dicts with per-frame 3D samples."""
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
        vx, vy = solve((X0, -Z0), (X1, -Z1), T)
        samples = fly(X0, -Z0, vx, vy, T)
        pts = []                                               # per sub-step: X, D, Z, vX, vZ
        for i, (x, y, svx, svy) in enumerate(samples):
            t = i / SUB
            pts.append((x, D0 + (D1 - D0) * t / T, -y, svx, -svy))
        net_z = None
        for a, b in zip(pts, pts[1:]):
            if (a[0] - NET_X) * (b[0] - NET_X) <= 0 and a[0] != b[0]:
                u = (NET_X - a[0]) / (b[0] - a[0])
                net_z = a[2] + (b[2] - a[2]) * u
                break
        out.append(dict(name=name, hitter=who, f0=f0, f1=f1, T=T, impact=impact,
                        pts=pts, net_z=net_z, apex=max(p[2] for p in pts),
                        speed0=math.hypot(vx, vy)))
    return out


def check(tracks, fl):
    """Contact poses at contact frames, net clearance, shuttle inside the canvas."""
    for name, who, f, _ in SHOTS:
        assert tracks[who][f][2] in CONTACT_POSES, (name, who, f, tracks[who][f][2])
    problems = []
    for s in fl:
        if s["net_z"] is None or s["net_z"] < NET_H + 1.5:
            problems.append(f"{s['name']}: crosses the net at Z={s['net_z']}")
        for x, d, z, *_ in s["pts"]:
            sx, sy = screen(x, d, z)
            if sy < 3 or not (2 <= sx <= W - 3):
                problems.append(f"{s['name']}: leaves the canvas at ({sx:.0f},{sy:.0f})")
                break
    return problems


# --------------------------------------------------------------------------
# Shuttle per frame: held, in flight (cork first), tumbling, landed
# --------------------------------------------------------------------------

def screen_dir(vx, vd, vz):
    """Screen-space direction of a court-space velocity."""
    return vx - vd * SKEW, vd - vz


def rotate(v, deg):
    a = math.radians(deg)
    return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a))


def shuttle_states(tracks, fl):
    st: list[dict] = [None] * FRAMES                               # type: ignore[list-item]
    serve_f = SHOTS[0][2]
    for f in range(serve_f):                                       # held by the feathers
        X, D, Z = world_point(tracks, "blue", f, "fh")
        drop = 4.0 if tracks["blue"][f][2] == "serve_swing" else 0.0
        st[f] = dict(X=X, D=D, Z=Z - 2.5 - drop, dir=(0.0, 1.0), shot=None, t=None)
    for k, s in enumerate(fl):
        vd = (s["pts"][-1][1] - s["pts"][0][1]) / s["T"]
        for t in range(s["T"]):
            X, D, Z, vX, vZ = s["pts"][t * SUB]
            if t == 0:                                             # still arriving: cork faces the racket
                if k == 0:
                    d = (0.0, 1.0)
                else:
                    pv = fl[k - 1]
                    pvd = (pv["pts"][-1][1] - pv["pts"][0][1]) / pv["T"]
                    d = screen_dir(pv["pts"][-1][3], pvd, pv["pts"][-1][4])
            else:
                d = screen_dir(vX, vd, vZ)
                if s["name"] == "net_shot" and t <= 5:             # spinning net shot tumbles
                    d = rotate(d, 80 * t)
            st[s["f0"] + t] = dict(X=X, D=D, Z=Z, dir=d, shot=s, t=t)
    last = fl[-1]
    X, D, _, vX, vZ = last["pts"][-1]
    side = 1.0 if vX > 0 else -1.0
    st[LAND_FRAME] = dict(X=X, D=D, Z=0.0, dir=screen_dir(vX, 0, vZ), shot=None, t=None, landed=0)
    if LAND_FRAME + 1 < FRAMES:
        st[LAND_FRAME + 1] = dict(X=X + 2.5 * side, D=D, Z=2.5, dir=(side, 0.2), shot=None, t=None, landed=1)
    for f in range(LAND_FRAME + 2, FRAMES):                        # at rest on its side
        st[f] = dict(X=X + 4 * side, D=D, Z=0.6, dir=(side, 0.35), shot=None, t=None, landed=2)
    assert all(s is not None for s in st)
    return st


DUST = "#e3d6c2a0"
FLASH_SOFT = "#fff6c890"


def shuttle_raster(stt, prev_screen, impact_now):
    sx, sy = screen(stt["X"], stt["D"], stt["Z"])
    r = base.shuttle_raster((sx, sy), stt["dir"])
    if prev_screen is not None:                                    # speed trail
        dist = math.dist(prev_screen, (sx, sy))
        if dist > 10:
            n = int(dist)
            for k in range(1, n):
                q = base.lerp(prev_screen, (sx, sy), k / n)
                if math.dist(q, (sx, sy)) > 3.2 and (k % 2 == 0 or dist > 25):
                    r.put(q[0], q[1], base.TRAIL, only_empty=True)
    if impact_now is not None:                                     # contact flash, by impact
        cx, cy = round(sx), round(sy)
        rays = {0: [(4, 0), (-4, 0), (0, 4), (0, -4)],
                1: [(5, 0), (6, 0), (-5, 0), (-6, 0), (0, 5), (0, 6), (0, -5), (0, -6),
                    (4, 4), (-4, 4), (4, -4), (-4, -4)],
                2: [(d * k, 0) for d in (5, 6, 7) for k in (1, -1)]
                   + [(0, d * k) for d in (5, 6, 7) for k in (1, -1)]
                   + [(d * a, d * b) for d in (4, 5) for a in (1, -1) for b in (1, -1)]}[impact_now]
        colour = FLASH_SOFT if impact_now == 0 else base.FLASH
        for dx, dy in rays:
            r.put(cx + dx, cy + dy, colour, only_empty=True)
    if stt.get("landed") in (0, 1):                                # dust where it hits the floor
        fx, fy = screen(stt["X"], stt["D"], 0)
        spread = 3 if stt["landed"] == 0 else 5
        for dx, dy in ((-spread, 0), (spread, 0), (-spread + 1, -1), (spread - 1, -1)):
            r.put(fx + dx, fy + dy, DUST, only_empty=True)
    return r, (sx, sy)


# --------------------------------------------------------------------------
# Background, score
# --------------------------------------------------------------------------

def draw_background(rect, line, rows):
    C, bg = base.C, "background"
    rect(bg, 0, 0, W, 42, C["wall_hi"])
    rect(bg, 0, 0, W, 6, C["ceiling"])
    for lx in (10, 58, 114, 162):
        rect(bg, lx, 1, 20, 2, C["light"])
        rect(bg, lx + 2, 3, 16, 1, C["glow"])
    rect(bg, 0, 42, W, 1, C["trim"])
    rect(bg, 0, 43, W, 27, C["wall_lo"])
    for i, bx in enumerate((4, 52, 104, 152)):                       # sponsor boards
        hi = base.tint(C["boards"][i], "#ffffff40")
        rect(bg, bx, 56, 36, 12, C["boards"][i])
        line(bg, bx, 56, bx + 35, 56, hi)
        rect(bg, bx + 4, 60, 28, 1, hi)
        rect(bg, bx + 8, 63, 20, 1, hi)
    rect(bg, 0, 70, W, 2, C["skirting"])
    rect(bg, 0, 72, W, H - 72, C["wood"])
    for sy in (75, 79, 84, 90, 97, 105):
        line(bg, 0, sy, W - 1, sy, C["wood_seam"])
    mx, my, mrows = base.court_mat_rows()
    rows(bg, 1, mrows, x=mx, y=my, legend={"g": C["court"]})
    for x1, y1, x2, y2 in base.court_lines():
        line(bg, x1, y1, x2, y2, C["line"])
    rect(bg, SBX, 11, 36, 15, C["panel_rim"])                        # scoreboard panel
    rect(bg, SBX + 1, 12, 34, 13, C["panel"])


SBX = 8
RED_DIM = "#7a3434"


def score_raster(red_pts: str, blue_pts: str, red_colour: str) -> Raster:
    r = Raster()
    for ch, dx, colour in ((red_pts[0], 5, red_colour), (red_pts[1], 9, red_colour),
                           (blue_pts[0], 24, base.C["blue_digit"]), (blue_pts[1], 28, base.C["blue_digit"])):
        for yy, row in enumerate(base.DIGITS[ch]):
            for xx, c in enumerate(row):
                if c == "#":
                    r.put(SBX + dx + xx, 16 + yy, colour)
    r.put(SBX + 17, 17, base.C["colon"])
    r.put(SBX + 17, 20, base.C["colon"])
    return r


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------

def frame_durations():
    d = [80] * FRAMES
    for f in range(SHOTS[0][2] - 1):
        d[f] = 110                                                   # players set before the serve
    for name, who, f, impact in SHOTS:
        d[f] = (100, 120, 180)[impact]                               # hit-stop by impact
    d[LAND_FRAME] = 220
    d[LAND_FRAME + 1] = 120
    for f in range(LAND_FRAME + 2, FRAMES):
        d[f] = 110
    d[FRAMES - 1] = 700                                              # pause before the loop
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

    # sprite, layers, frames
    calls.append(Call("create_canvas", {"width": W, "height": H, "filename": sprite}))
    add("rename_layer", layer_name="Layer 1", new_name="background")
    for name in ("score", "net", "shadows", "player_red", "player_blue", "shuttle"):
        add("add_layer", layer_name=name)
    add("add_frames", count=FRAMES - 1, duration_ms=80)
    add("set_frame_duration_all", duration_ms=80)

    # static layers on frame 1, copied to every frame
    draw_background(rect, line, rows)
    net, near_post = base.net_raster()
    rows("net", 1, net)
    add("propagate_cels", layer_names=["background", "net"], source_frame=1,
        start_frame=1, end_frame=FRAMES)

    # score: 20-19 until the point is over, then 21-19 with the red score blinking
    won = LAND_FRAME + 2
    rows("score", 1, score_raster("20", "19", base.C["red_digit"]))
    add("propagate_cels", layer_names=["score"], source_frame=1, start_frame=1, end_frame=won)
    rows("score", won + 1, score_raster("21", "19", base.C["red_digit"]))
    add("propagate_cels", layer_names=["score"], source_frame=won + 1,
        start_frame=won + 1, end_frame=FRAMES)
    for f in range(won, FRAMES):
        if (f - won) // 2 % 2 == 1:
            rows("score", f + 1, score_raster("21", "19", RED_DIM))

    # per frame: shadows, players, shuttle
    prev = None
    for f in range(FRAMES):
        fi = f + 1
        sh = Raster()
        placed = {}
        for who in ("red", "blue"):
            X, D, pname = tracks[who][f]
            sx, sy = screen(X, D)
            rx, ry = math.floor(sx + 0.5), math.floor(sy + 0.5)
            placed[who] = (rx, ry, pname)
            hw = 5.5 - 0.3 * P[pname]["lift"]
            for x in range(math.floor(rx - hw), math.ceil(rx + hw) + 1):
                for y in (ry - 1, ry, ry + 1):
                    if ((x - rx) / hw) ** 2 + ((y - ry) / 1.4) ** 2 <= 1.0:
                        sh.put(x, y, base.SHADOW)
        s = shuttle[f]
        fx, fy = screen(s["X"], s["D"], 0)
        if s["Z"] > 1:
            w = 2 if s["Z"] < 25 else 1
            for x in range(round(fx) - w, round(fx) + w + 1):
                sh.put(x, round(fy) + 1, base.SHADOW)
        for k in near_post & set(sh.px):
            del sh.px[k]
        rows("shadows", fi, sh)

        for who in ("red", "blue"):
            rx, ry, pname = placed[who]
            r = base.render_player(who, pname)
            if who == "blue":
                r = r.mirrored()
            x, y, rws, legend = r.to_rows(rx, ry)
            rows(f"player_{who}", fi, rws, x=x, y=y, legend=legend)

        sr, prev = shuttle_raster(s, prev if s.get("t") else None, contacts.get(f))
        rows("shuttle", fi, sr)

    # timing and tags
    for f, ms in enumerate(frame_durations()):
        if ms != 80:
            add("set_frame_duration", frame_index=f + 1, duration_ms=ms)
    bounds = [f for _, _, f, _ in SHOTS] + [LAND_FRAME]
    names = [n for n, *_ in SHOTS]
    starts = [0] + bounds[1:]
    for name, a, b in zip(names, starts, bounds[1:]):
        add("set_tag", name=name, from_frame=a + 1, to_frame=b, direction="forward")
    add("set_tag", name="point", from_frame=LAND_FRAME + 1, to_frame=FRAMES, direction="forward")

    # exports
    stem = os.path.join(out_dir, STEM)
    add("export_animation", output_filename=stem + ".gif", scale=4)
    add("export_spritesheet", output_filename=stem + "_sheet.png", sheet_type="rows",
        data_filename=stem + "_sheet.json", scale=1, list_tags=True)
    smash = next(f for n, _, f, _ in SHOTS if n == "jump_smash")
    add("export_frame", frame_index=smash + 1, output_filename=stem + "_smash.png", scale=4)
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
