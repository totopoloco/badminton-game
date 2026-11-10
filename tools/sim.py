"""Reference model of the Godot game's rules, physics, strokes and CPU player.

scripts/*.gd is a port of this file (same names, same order of updates).
Court coordinates: x along the court (net at 96), y across it (0 = centre
line, + towards the camera), z height; x, y and z in court pixels.

  python3 sim.py --points 400 --level 1          # CPU vs CPU, normal level
  python3 sim.py --match --level 2               # a whole 3x15 match
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
RIG = json.load(open(os.environ.get("RIG", os.path.join(HERE, "..", "assets", "rig.json"))))

# ---------------------------------------------------------------- constants
TICK = 1.0 / 60.0
SUB = 2                      # shuttle substeps per tick
DT = TICK / SUB
G = 250.0                    # px/s^2
K = 0.016                    # quadratic drag, 1/px
NET_X = 96.0
NET_H = 28.0                 # tape height
HALF = 84.0                  # net to baseline
SHORT = 24.8                 # short service line, from the net
SIDE = 32.4                  # singles sideline, from the centre line
REACH = 9.0                  # racket-head to shuttle distance that still hits
REACH_Y = 14.0               # ... sideways (the arm reaches further across)
ARM_TICKS = 21               # a swing waits this long for the shuttle (0.35 s)
LOCK_TICKS = 8               # no running during the follow-through
SERVE_CONTACT = 7            # ticks from pressing serve to the contact
NET_GAP = 2.5                # below the tape the racket stays this far from the net
SOFT_MAX_SPEED = 120.0       # soft shots fly no faster than this on average
AIM_Y = 26.0                 # widest aim, from the centre line
SIDE_REACH = 0.4 * 14.0      # the CPU reaches this far across instead of running

SPEED = 92.0                 # px/s
ACCEL = 1000.0
DECEL = 1600.0
JUMP_V = 150.0
PLAYER_G = 600.0
X_NEAR, X_FAR = 10.0, 86.0   # feet limits, measured from the net
Y_LIM = 42.0                 # feet limit across the court

SERVER_U, RECEIVER_U = 44.0, 50.0
SERVE_Y = 15.0               # serving/receiving spot, from the centre line
HOME_U = 42.0

GROUND_STROKES = ["overhead", "kill", "drive", "block", "net", "lift"]
ZONE = {"kill": 22.0, "net": 45.0}   # stroke -> farthest contact from the net

# shot -> target depth u (from the net, other side), flight time s, net margin px,
#         max launch speed px/s, apex px, error weight, impact (0 soft, 1 normal, 2 hard)
SHOTS = {
    "clear":       dict(u=(66, 78), t=(1.10, 1.30), margin=6.0, vmax=950.0, apex=96.0, err=1.0, impact=1),
    "lift":        dict(u=(60, 76), t=(1.15, 1.40), margin=6.0, vmax=950.0, apex=115.0, err=0.8, impact=1),
    "drop":        dict(u=(12, 26), t=(0.90, 1.05), margin=2.5, vmax=400.0, apex=84.0, err=0.8, impact=0),
    "net":         dict(u=(7, 15),  t=(0.70, 0.90), margin=1.5, vmax=300.0, apex=84.0, err=0.6, impact=0),
    "block":       dict(u=(8, 18),  t=(0.75, 0.95), margin=2.0, vmax=300.0, apex=84.0, err=0.7, impact=0),
    "push":        dict(u=(50, 66), t=(0.90, 1.10), margin=3.0, vmax=650.0, apex=90.0, err=1.0, impact=1),
    "drive":       dict(u=(55, 75), t=(0.78, 0.90), margin=2.0, vmax=700.0, apex=84.0, err=1.1, impact=1),
    "smash":       dict(u=(35, 60), t=(0.50, 0.62), margin=3.0, vmax=850.0, apex=84.0, err=1.2, impact=2),
    "jsmash":      dict(u=(30, 55), t=(0.42, 0.52), margin=3.0, vmax=1050.0, apex=90.0, err=1.3, impact=2),
    "kill":        dict(u=(22, 40), t=(0.28, 0.36), margin=2.0, vmax=650.0, apex=84.0, err=1.2, impact=2),
    "serve_high":  dict(u=(72, 80), t=(1.25, 1.45), margin=5.0, vmax=900.0, apex=90.0, err=0.8, impact=1),
    "serve_short": dict(u=(27, 33), t=(0.75, 0.90), margin=2.0, vmax=300.0, apex=84.0, err=0.5, impact=0),
}

# button -> stroke -> shot (the human's three shot buttons)
SHOT_MAP = {
    "clear": dict(overhead="clear", jump_smash="clear", kill="push", drive="clear",
                  block="lift", net="lift", lift="lift"),
    "drop":  dict(overhead="drop", jump_smash="drop", kill="net", drive="block",
                  block="block", net="net", lift="net"),
    "smash": dict(overhead="smash", jump_smash="jsmash", kill="kill", drive="drive",
                  block="drive", net="push", lift="push"),
}

LEVELS = [   # easy, normal, hard
    dict(name="EASY", speed=0.80, react=0.30, pos_err=4.0, err=1.6, judge=0.55, jump=0.0,
         smart=0.3, lead=8, mistake=0.12, misjudge=0.06),
    dict(name="NORMAL", speed=0.92, react=0.20, pos_err=2.5, err=1.0, judge=0.80, jump=0.35,
         smart=0.6, lead=6, mistake=0.05, misjudge=0.02),
    dict(name="HARD", speed=1.00, react=0.13, pos_err=1.5, err=0.6, judge=0.95, jump=0.7,
         smart=0.85, lead=5, mistake=0.02, misjudge=0.005),
]
PREF = dict(kill=3.0, jump_smash=2.6, overhead=2.0, drive=1.4, net=1.2, block=1.0, lift=0.8)
SHOT_WEIGHTS = {
    "overhead": dict(clear=1.0, drop=1.0, smash=1.2),
    "jump_smash": dict(jsmash=3.0, drop=1.0),
    "kill": dict(kill=1.0),
    "drive": dict(drive=2.0, block=1.0, clear=0.5),
    "block": dict(block=1.5, lift=1.5, drive=0.5),
    "net": dict(net=2.0, lift=1.5, push=0.3),
    "lift": dict(lift=2.0, net=1.0),
}


def jump_apex():
    """(ticks, height) of the jump apex with the players' per-tick integration."""
    z, vz, best = 0.0, JUMP_V, (0, 0.0)
    for n in range(1, 120):
        vz -= PLAYER_G * TICK
        z += vz * TICK
        if z > best[1] + 1e-9:
            best = (n, z)
        if z <= 0:
            break
    return best


JUMP_APEX_TICKS, JUMP_APEX_H = jump_apex()


# ---------------------------------------------------------------- physics
def step3(s):
    """One substep of [x, y, z, vx, vy, vz] in place (semi-implicit Euler)."""
    vx, vy, vz = s[3], s[4], s[5]
    sp = math.sqrt(vx * vx + vy * vy + vz * vz)
    vx += -K * sp * vx * DT
    vy += -K * sp * vy * DT
    vz += (-G - K * sp * vz) * DT
    s[0] += vx * DT
    s[1] += vy * DT
    s[2] += vz * DT
    s[3], s[4], s[5] = vx, vy, vz


def fly_sens(z0, vs, vz, ticks, s_net):
    """Flight in the vertical plane of the shot (s = horizontal distance from the
    launch point). Returns [s, z, ds/dvs, ds/dvz, dz/dvs, dz/dvz, height where s
    passes s_net (-1e9 if never), apex]."""
    s, z = 0.0, z0
    jxa = jza = jxb = jzb = 0.0
    avx, avz, bvx, bvz = 1.0, 0.0, 0.0, 1.0
    cross = -1.0e9
    apex = z0
    for _ in range(ticks * SUB):
        sp = math.sqrt(vs * vs + vz * vz)
        if sp > 1e-9:
            dxx = -K * (sp + vs * vs / sp)
            dxz = -K * vs * vz / sp
            dzz = -K * (sp + vz * vz / sp)
        else:
            dxx = dxz = dzz = 0.0
        avx, avz = avx + (dxx * avx + dxz * avz) * DT, avz + (dxz * avx + dzz * avz) * DT
        bvx, bvz = bvx + (dxx * bvx + dxz * bvz) * DT, bvz + (dxz * bvx + dzz * bvz) * DT
        jxa += avx * DT
        jza += avz * DT
        jxb += bvx * DT
        jzb += bvz * DT
        nvs = vs - K * sp * vs * DT
        nvz = vz + (-G - K * sp * vz) * DT
        ns, nz = s + nvs * DT, z + nvz * DT
        if cross == -1.0e9 and (s - s_net) * (ns - s_net) <= 0.0 and ns != s:
            cross = z + (nz - z) * (s_net - s) / (ns - s)
        s, z, vs, vz = ns, nz, nvs, nvz
        apex = max(apex, z)
    return s, z, jxa, jxb, jza, jzb, cross, apex


def solve(z0, s1, z1, ticks, s_net):
    """Launch speed along the ground (vs) and up (vz) reaching horizontal distance s1
    at height z1 after exactly `ticks` ticks (damped Newton).
    Returns (vs, vz, height at the net, apex, miss distance)."""
    T = ticks * TICK
    vs, vz = s1 / T * 1.6, (z1 - z0) / T + 0.5 * G * T
    s, z, j00, j01, j10, j11, cross, apex = fly_sens(z0, vs, vz, ticks, s_net)
    err = math.hypot(s - s1, z - z1)
    for _ in range(30):
        ex, ez = s - s1, z - z1
        err = math.hypot(ex, ez)
        if err < 0.02:
            break
        det = j00 * j11 - j01 * j10
        if abs(det) < 1e-12:
            break
        dvs = (j11 * ex - j01 * ez) / det
        dvz = (-j10 * ex + j00 * ez) / det
        step, improved = 1.0, False
        while step > 1.0 / 64.0:
            r = fly_sens(z0, vs - step * dvs, vz - step * dvz, ticks, s_net)
            if math.hypot(r[0] - s1, r[1] - z1) < err:
                vs, vz = vs - step * dvs, vz - step * dvz
                s, z, j00, j01, j10, j11, cross, apex = r
                err = math.hypot(s - s1, z - z1)
                improved = True
                break
            step *= 0.5
        if not improved:
            break
    return vs, vz, cross, apex, err


def predict(x, y, z, vx, vy, vz, max_ticks):
    """Shuttle position at the start of each coming tick, until the floor or the net.
    Returns (points [(x, y, z)], outcome) with outcome 'land', 'net' or 'open'."""
    st = [x, y, z, vx, vy, vz]
    pts = [(x, y, z)]
    for _ in range(max_ticks):
        for _ in range(SUB):
            px, pz = st[0], st[2]
            step3(st)
            nx, nz = st[0], st[2]
            if (px - NET_X) * (nx - NET_X) <= 0.0 and nx != px:
                cz = pz + (nz - pz) * (NET_X - px) / (nx - px)
                if cz <= NET_H:
                    pts.append((NET_X, st[1], cz))
                    return pts, "net"
            if nz <= 0.0:
                pts.append((nx, st[1], 0.0))
                return pts, "land"
        pts.append((st[0], st[1], st[2]))
    return pts, "open"


# ---------------------------------------------------------------- shots
def aim_y(rng, aim, court):
    """Sideways target: rally shots anywhere inside the sidelines; a serve into
    the service court whose side of the centre line is `court` (+1 / -1)."""
    if court == 0:
        return max(-AIM_Y, min(AIM_Y, aim * AIM_Y + rng.uniform(-5.0, 5.0)))
    inner, outer = 5.0, AIM_Y
    a = 0.5 + 0.5 * aim * court                       # 0 = by the centre line, 1 = wide
    return court * (inner + (outer - inner) * max(0.0, min(1.0, a + rng.uniform(-0.15, 0.15))))


def plan_shot(rng, x0, y0, z0, f, shot, quality, err_scale, aim_x, aim_side, court=0):
    """Launch velocity for `shot` from (x0, y0, z0) by a player facing f.

    aim_x -1..1 picks the depth (-1 deepest, +1 shortest), aim_side -1..1 the side
    (-1 far sideline, +1 near). `court` != 0 for a serve: the receiver's service
    court side. The intended flight clears the net by the shot's margin, stays
    under its speed limit and apex (adapting flight time and depth); then the
    hitter's error is added, larger for a poor contact.
    Returns (vx, vy, vz, solves, shot)."""
    gap = abs(NET_X - x0)
    if shot in ("net", "block") and gap > 45.0:
        shot = "drop"                                   # too far back for a net shot
    elif z0 < NET_H + 2.0 and shot in ("lift", "push", "drive", "clear") and gap < 14.0:
        shot = "net" if gap < 8.0 else "lift"           # under the tape near the net: lift or net
    s = SHOTS[shot]
    hard = s["impact"] == 2
    lo, hi = s["u"]
    u = lo + (hi - lo) * (0.5 - 0.5 * aim_x) + rng.uniform(-0.1, 0.1) * (hi - lo)
    yt = aim_y(rng, aim_side, court)
    t = rng.uniform(s["t"][0], s["t"][1])
    if s["impact"] == 0:
        t = max(t, math.hypot(NET_X + f * u - x0, yt - y0) / SOFT_MAX_SPEED)

    def attempt(u_, y_, t_):
        dx, dy = NET_X + f * u_ - x0, y_ - y0
        dist = math.hypot(dx, dy)
        ux, uy = dx / dist, dy / dist
        s_net = (NET_X - x0) / ux
        vs, vz, cz, apex, miss = solve(z0, dist, 0.0, max(4, round(t_ / TICK)), s_net)
        return vs * ux, vs * uy, vz, cz, apex, miss

    best = None
    solves = 0
    for i in range(14):
        vx, vy, vz, cz, apex, miss = attempt(u, yt, t)
        solves += 1
        low = NET_H + s["margin"] - cz
        fast = math.sqrt(vx * vx + vy * vy + vz * vz) - s["vmax"]
        high = apex - s["apex"]
        pen = max(0.0, low) * 4.0 + max(0.0, fast) / 40.0 + max(0.0, high) + (1000.0 if miss > 1.0 else 0.0)
        if best is None or pen < best[0]:
            best = (pen, u, t, vx, vy, vz)
        if pen <= 0.0:
            break
        if miss > 1.0:
            t *= 0.9
        elif low > 0.0:
            t *= 1.12
            if hard and i % 3 == 2:
                u = min(u + 4.0, 80.0)
        elif fast > 0.0:
            if hard:
                t *= 1.08
            else:
                u = max(u - 5.0, 2.0)
        else:
            t *= 0.94
    _, u, t, vx, vy, vz = best
    sigma = err_scale * (1.0 + 5.0 * (1.0 - quality)) * s["err"]
    u_err = max(0.5, u + rng.gauss(0.0, sigma))          # too short: into the net
    y_err = yt + rng.gauss(0.0, sigma * 0.8)
    t_err = t * (1.0 + rng.gauss(0.0, 0.03 * err_scale * (1.0 - quality)))
    evx, evy, evz, _, _, miss = attempt(u_err, y_err, t_err)
    if miss <= 1.0:
        vx, vy, vz = evx, evy, evz
    return vx, vy, vz, solves + 1, shot


# ---------------------------------------------------------------- players
class Player:
    def __init__(self, who, f, x, y=0.0, err_scale=1.0):
        self.who, self.f = who, f
        self.c = RIG["characters"][who]
        self.x, self.y, self.z = x, y, 0.0
        self.vx = self.vy = self.vz = 0.0
        self.move_x = self.move_y = 0.0   # input, -1..1 each (screen directions)
        self.speed = SPEED
        self.stroke = None
        self.err_scale = err_scale

    def on_ground(self):
        return self.z <= 0.0 and self.vz <= 0.0

    def x_limits(self):
        a, b = NET_X - self.f * X_FAR, NET_X - self.f * X_NEAR
        return min(a, b), max(a, b)

    def locked(self):
        """No running while serving or during the follow-through of a ground stroke."""
        st = self.stroke
        if st is None:
            return False
        if st["phase"] == "serve":
            return True
        return st["phase"] == "follow" and st["t"] < LOCK_TICKS and st["name"] != "jump_smash"

    def jump(self):
        """Straight up: the run stops at take-off (no drifting through the air)."""
        if self.on_ground() and self.stroke is None:
            self.vz = JUMP_V
            self.vx = self.vy = 0.0
            return True
        return False

    def contact_point(self, stroke, x, y, z):
        dx, cz = self.c["contact"][stroke]
        return x + self.f * dx, y, z + cz

    def next_pos(self):
        if self.on_ground():
            return self.x + self.vx * TICK, self.y + self.vy * TICK, 0.0
        vz = self.vz - PLAYER_G * TICK
        return self.x + self.vx * TICK, self.y + self.vy * TICK, max(0.0, self.z + vz * TICK)

    @staticmethod
    def _axis(v, target):
        a = (ACCEL if abs(target) > abs(v) and target * v >= 0.0 else DECEL) * TICK
        return v + max(-a, min(a, target - v))

    def update(self):
        if self.locked():
            tx = ty = 0.0
        elif not self.on_ground():
            tx, ty = self.vx, self.vy                 # no air control
        else:
            mx, my = self.move_x, self.move_y
            n = math.hypot(mx, my)
            if n > 1.0:
                mx, my = mx / n, my / n
            tx, ty = mx * self.speed, my * self.speed
        self.vx = self._axis(self.vx, tx)
        self.vy = self._axis(self.vy, ty)
        lo, hi = self.x_limits()
        self.x += self.vx * TICK
        if self.x < lo or self.x > hi:
            self.x = max(lo, min(hi, self.x))
            self.vx = 0.0
        self.y += self.vy * TICK
        if abs(self.y) > Y_LIM:
            self.y = max(-Y_LIM, min(Y_LIM, self.y))
            self.vy = 0.0
        if self.z > 0.0 or self.vz > 0.0:
            self.vz -= PLAYER_G * TICK
            self.z += self.vz * TICK
            if self.z <= 0.0:
                self.z, self.vz = 0.0, 0.0
        st = self.stroke
        if st is not None:
            st["t"] += 1
            if st["phase"] == "armed" and st["t"] > ARM_TICKS:
                st["phase"], st["t"], st["follow_len"] = "follow", 0, 10     # whiff
            elif st["phase"] in ("follow", "serve") and st["t"] >= st["follow_len"]:
                self.stroke = None


class Shuttle:
    def __init__(self):
        self.s = [0.0] * 6           # x, y, z, vx, vy, vz
        self.state = "held"          # held, flight, net, landed
        self.via_net = False

    x = property(lambda self: self.s[0])
    y = property(lambda self: self.s[1])
    z = property(lambda self: self.s[2])

    def step(self):
        """One tick. Returns 'net' when it hits the net, 'land' when it lands."""
        s = self.s
        if self.state == "flight":
            for _ in range(SUB):
                px, pz = s[0], s[2]
                step3(s)
                if (px - NET_X) * (s[0] - NET_X) <= 0.0 and s[0] != px:
                    cz = pz + (s[2] - pz) * (NET_X - px) / (s[0] - px)
                    if cz <= NET_H:
                        side = -1.0 if px < NET_X else 1.0
                        s[0], s[2] = NET_X + side * 1.0, cz
                        s[3], s[4], s[5] = 0.0, 0.0, min(s[5], 0.0) * 0.3
                        self.state, self.via_net = "net", True
                        return "net"
                if s[2] <= 0.0:
                    s[2] = 0.0
                    self.state = "landed"
                    return "land"
        elif self.state == "net":
            for _ in range(SUB):
                s[3] = s[4] = 0.0
                step3(s)
                if s[2] <= 0.0:
                    s[2] = 0.0
                    self.state = "landed"
                    return "land"
        return ""

    def next_tick(self):
        st = list(self.s)
        for _ in range(SUB):
            step3(st)
        return st[0], st[1], st[2]


def scaled(p):
    """Reach space: sideways distances count less (the arm reaches further across)."""
    return (p[0], p[1] * REACH / REACH_Y, p[2])


def closest(s0, s1, c0, c1):
    """Closest approach between two points moving linearly over one tick (in reach
    space): (distance, tau)."""
    s0, s1, c0, c1 = scaled(s0), scaled(s1), scaled(c0), scaled(c1)
    r = [s0[i] - c0[i] for i in range(3)]
    w = [(s1[i] - s0[i]) - (c1[i] - c0[i]) for i in range(3)]
    ww = sum(v * v for v in w)
    tau = 0.0 if ww < 1e-12 else max(0.0, min(1.0, -sum(r[i] * w[i] for i in range(3)) / ww))
    return math.sqrt(sum((r[i] + tau * w[i]) ** 2 for i in range(3))), tau


def reachable(f, stroke, rx, rz, sx, margin=0.0):
    """Can a player facing f meet a shuttle at x `sx` with the racket head at (rx, rz)?"""
    if f * (NET_X - sx) < 0.5:
        return False
    gap = f * (NET_X - rx)
    low = rz < NET_H + 2.0
    if gap < (NET_GAP if low else 0.0) + margin or gap > ZONE.get(stroke, 999.0) - margin:
        return False
    return True


def racket_gap_min(cz):
    return NET_GAP if cz < NET_H + 2.0 else 0.0


def court_side(f, score):
    """Side of the centre line (+1 near, -1 far) a player serves or receives from:
    the right court on an even score. Right = +y for red (facing +x), -y for blue."""
    return f if score % 2 == 0 else -f


class Rally:
    """Serve and rally until the shuttle is down: the shared rules."""

    def __init__(self, rng, red, blue, server, server_score=0):
        self.rng = rng
        self.p = {"red": red, "blue": blue}
        self.server = server
        self.serve_court = -court_side(red.f if server == "red" else blue.f, server_score)
        self.s = Shuttle()
        self.last = None
        self.is_serve = True
        self.shots = []
        self.tick = 0
        self.solves = []

    @staticmethod
    def opponent(who):
        return "blue" if who == "red" else "red"

    def press(self, who, button=None, forced_stroke=None, shot=None, aim_x=0.0, aim_side=0.0, quality_scale=1.0):
        pl = self.p[who]
        if pl.stroke is not None:
            return False
        if forced_stroke:
            cands = [forced_stroke]
        elif not pl.on_ground():
            cands = ["jump_smash"]
        else:
            cands = list(GROUND_STROKES)
        pl.stroke = dict(phase="armed", t=0, cands=cands, button=button, shot=shot, aim_x=aim_x,
                         aim_side=aim_side, qscale=quality_scale, name=cands[0], follow_len=18)
        return True

    def serve(self, kind, aim_x=0.0, aim_side=0.0):
        pl = self.p[self.server]
        pl.stroke = dict(phase="serve", t=0, name="serve" if kind == "serve_high" else "serve_short",
                         shot=kind, follow_len=20, aim_x=aim_x, aim_side=aim_side, qscale=1.0)
        self.s.state = "held"

    def contacts(self):
        for who, pl in self.p.items():
            st = pl.stroke
            if st is None:
                continue
            if st["phase"] == "serve":
                if st["t"] == SERVE_CONTACT and self.s.state == "held":
                    c0 = pl.contact_point(st["name"], pl.x, pl.y, pl.z)
                    self.launch(who, pl, c0, st["shot"], 1.0, True, st)
                    st["phase"], st["t"] = "follow", 0
                    return who
                continue
            if st["phase"] != "armed" or self.s.state != "flight" or self.last == who:
                continue
            s0 = (self.s.x, self.s.y, self.s.z)
            s1 = self.s.next_tick()
            n = pl.next_pos()
            best = None
            for name in st["cands"]:
                c0 = pl.contact_point(name, pl.x, pl.y, pl.z)
                c1 = pl.contact_point(name, *n)
                d, tau = closest(s0, s1, c0, c1)
                if not reachable(pl.f, name, c0[0], c0[2], s0[0] + tau * (s1[0] - s0[0])):
                    continue
                if d <= REACH and (tau < 1.0 or st["t"] >= ARM_TICKS) and (best is None or d < best[0]):
                    best = (d, name, c0)
            if best is None:
                continue
            d, name, c0 = best
            shot = st["shot"] or SHOT_MAP[st["button"]][name]
            st["name"] = name
            self.launch(who, pl, c0, shot, (1.0 - d / REACH) * st["qscale"], False, st)
            st["phase"], st["t"] = "follow", 0
            if name != "jump_smash":
                pl.vx = pl.vy = 0.0
            return who
        return None

    def launch(self, who, pl, c0, shot, quality, is_serve, st):
        vx, vy, vz, n, shot = plan_shot(self.rng, c0[0], c0[1], c0[2], pl.f, shot, quality, pl.err_scale,
                                        st["aim_x"], st["aim_side"], self.serve_court if is_serve else 0)
        self.solves.append(n)
        self.s.s = [c0[0], c0[1], c0[2], vx, vy, vz]
        self.s.state, self.s.via_net = "flight", False
        self.last, self.is_serve = who, is_serve
        self.shots.append((who, st["name"], shot, round(quality, 2)))

    def decide(self):
        hitter = self.last
        opp = self.opponent(hitter)
        u = self.p[hitter].f * (self.s.x - NET_X)
        if self.s.via_net or u <= 0.0:
            return opp, "NET"
        if u > HALF or abs(self.s.y) > SIDE:
            return opp, "OUT"
        if self.is_serve:
            if u < SHORT:
                return opp, "SHORT"
            if self.s.y * self.serve_court < 0.0:
                return opp, "FAULT"                     # wrong service court
        return hitter, "IN"


# ---------------------------------------------------------------- CPU
class CPU:
    def __init__(self, rng, who, level):
        self.rng, self.who = rng, who
        self.L = LEVELS[level]
        self.plan = None

    def think(self, r, pl, opp):
        self.plan = None
        s = r.s
        path, outcome = predict(*s.s, 400)
        if outcome == "net":
            return
        lx, ly, _ = path[-1]
        u_land = -pl.f * (lx - NET_X)
        out = u_land > HALF + 1.0 or abs(ly) > SIDE + 1.0 or \
            (r.is_serve and ly * r.serve_court < -1.0)
        if outcome == "land" and out and self.rng.random() < self.L["judge"]:
            return
        if self.rng.random() < self.L["misjudge"]:
            return
        react = round(self.L["react"] / TICK)
        speed = SPEED * self.L["speed"]
        strokes = list(GROUND_STROKES)
        if self.rng.random() < self.L["jump"]:
            strokes.insert(0, "jump_smash")
        lo, hi = pl.x_limits()
        best = None
        for st in strokes:
            dx, cz = pl.c["contact"][st]
            jump = st == "jump_smash"
            if jump:
                cz += JUMP_APEX_H
            for k in range(react + 2, len(path)):
                X, Y, Z = path[k]
                if abs(Z - cz) > 3.0 or not reachable(pl.f, st, X, cz, X, 1.0):
                    continue
                x_need = X - pl.f * dx
                y_need = Y - max(-SIDE_REACH, min(SIDE_REACH, Y - pl.y))   # reach across, don't run
                if not lo <= x_need <= hi or abs(y_need) > Y_LIM:
                    continue
                ready = k - (JUMP_APEX_TICKS + 6 if jump else 0)
                if math.hypot(x_need - pl.x, y_need - pl.y) / speed + 0.05 > (ready - react) * TICK:
                    continue
                score = PREF[st] - 0.15 * k * TICK
                if best is None or score > best[0]:
                    best = (score, st, k, x_need, y_need)
                break
        if best is None:
            return
        _, st, k, x_need, y_need = best
        x = x_need + self.rng.gauss(0.0, self.L["pos_err"])
        y = y_need + self.rng.gauss(0.0, self.L["pos_err"])
        dx, cz = pl.c["contact"][st]
        gap = pl.f * (NET_X - (x + pl.f * dx))
        lim = racket_gap_min(cz) + 0.5
        if gap < lim:
            x -= pl.f * (lim - gap)
        shot, aim_side = self.choose_shot(st, opp, pl.f * (NET_X - x_need) - dx, cz)
        self.plan = dict(stroke=st, contact=r.tick + k, x=x, y=y, start=r.tick + react, shot=shot,
                         aim_side=aim_side, pressed=False, jumped=False)

    def choose_shot(self, st, opp, gap, cz):
        """Shot and side to aim at for a planned stroke; gap = contact distance from the net."""
        opp_u = abs(opp.x - NET_X)
        if cz < NET_H + 2.0 and gap < 20.0:
            w = dict(net=1.0, lift=1.0)
        else:
            w = dict(SHOT_WEIGHTS[st])
        side = self.rng.uniform(-1.0, 1.0)
        if self.rng.random() < self.L["smart"]:
            for shot in w:
                deep = SHOTS[shot]["u"][0] >= 45
                if (opp_u < 35 and deep) or (opp_u > 58 and not deep):
                    w[shot] *= 2.5
            if abs(opp.y) > 4.0:                          # away from the opponent
                side = -math.copysign(self.rng.uniform(0.5, 1.0), opp.y)
        pick = self.rng.random() * sum(w.values())
        for shot, wt in w.items():
            pick -= wt
            if pick <= 0.0:
                return shot, side
        return shot, side

    def update(self, r, pl):
        p = self.plan
        tx, ty = NET_X - pl.f * HOME_U, 0.0
        if p is not None:
            if r.tick < p["start"]:
                tx, ty = pl.x, pl.y
            else:
                tx, ty = p["x"], p["y"]
                jump = p["stroke"] == "jump_smash"
                if jump and r.tick >= p["contact"] - JUMP_APEX_TICKS and not p["jumped"]:
                    pl.jump()
                    p["jumped"] = True
                lead = 3 if jump else self.L["lead"]
                if not p["pressed"] and r.tick >= p["contact"] - lead:
                    q = 0.2 if self.rng.random() < self.L["mistake"] else 1.0
                    p["pressed"] = r.press(self.who, forced_stroke=p["stroke"], shot=p["shot"],
                                           aim_x=self.rng.uniform(-1.0, 1.0), aim_side=p["aim_side"],
                                           quality_scale=q)
                if p["pressed"] and (pl.stroke is None or pl.stroke["phase"] != "armed"):
                    self.plan = None
        dx, dy = tx - pl.x, ty - pl.y
        dist = math.hypot(dx, dy)
        if dist > 0.3:
            k = min(1.0, dist / 6.0) / dist
            pl.move_x, pl.move_y = dx * k, dy * k
        else:
            pl.move_x = pl.move_y = 0.0
        pl.speed = SPEED * self.L["speed"]


# ---------------------------------------------------------------- scoring (3 x 15)
class Score:
    def __init__(self):
        self.points = {"red": 0, "blue": 0}
        self.games = {"red": 0, "blue": 0}

    def game_won_by(self):
        a, b = self.points["red"], self.points["blue"]
        for me, other, who in ((a, b, "red"), (b, a, "blue")):
            if me >= 21 or (me >= 15 and me - other >= 2):
                return who
        return None

    def add(self, who):
        self.points[who] += 1
        g = self.game_won_by()
        if g is None:
            return "point"
        self.games[g] += 1
        return "match" if self.games[g] == 2 else "game"

    def new_game(self):
        self.points = {"red": 0, "blue": 0}


# ---------------------------------------------------------------- CPU vs CPU
def play_rally(rng, lv_red, lv_blue, server, server_score=0, men=True, trace=False):
    red = Player("red_man" if men else "red_woman", 1, 0.0, 0.0, LEVELS[lv_red]["err"])
    blue = Player("blue_man" if men else "blue_woman", -1, 0.0, 0.0, LEVELS[lv_blue]["err"])
    r = Rally(rng, red, blue, server, server_score)
    srv, rcv = r.p[server], r.p[Rally.opponent(server)]
    srv.x, srv.y = NET_X - srv.f * SERVER_U, -r.serve_court * SERVE_Y
    rcv.x, rcv.y = NET_X - rcv.f * RECEIVER_U, r.serve_court * SERVE_Y
    cpus = {"red": CPU(rng, "red", lv_red), "blue": CPU(rng, "blue", lv_blue)}
    kind = "serve_high" if rng.random() < 0.6 else "serve_short"
    max_z, serve_at = 0.0, 30
    while r.tick < 60 * 40:
        if r.tick == serve_at:
            r.serve(kind, rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0))
        if r.s.state != "held":                         # as in the game: CPUs wait for the serve
            for who in ("red", "blue"):
                cpus[who].update(r, r.p[who])
        hitter = r.contacts()
        if hitter:
            other = Rally.opponent(hitter)
            cpus[other].think(r, r.p[other], r.p[hitter])
            cpus[hitter].plan = None
            if trace:
                print(f"  t={r.tick} {hitter} {r.shots[-1]} from ({r.s.x:.0f},{r.s.y:.0f},{r.s.z:.0f}); "
                      f"{other} at ({r.p[other].x:.0f},{r.p[other].y:.0f}) plan {cpus[other].plan}")
        for pl in r.p.values():
            pl.update()
        ev = r.s.step()
        max_z = max(max_z, r.s.z)
        if ev == "land":
            winner, call = r.decide()
            return winner, call, r.shots, max_z, r.solves
        r.tick += 1
    return None, "TIMEOUT", r.shots, max_z, r.solves


def stats(a):
    rng = random.Random(a.seed)
    lv_b = a.level if a.vs is None else a.vs
    calls, lengths, shots, wins, heights, ends, solves = Counter(), [], Counter(), Counter(), [], Counter(), []
    server, score = "red", {"red": 0, "blue": 0}
    for _ in range(a.points):
        w, call, sh, mz, sv = play_rally(rng, a.level, lv_b, server, score[server], men=not a.women)
        calls[call] += 1
        lengths.append(len(sh))
        heights.append(mz)
        solves += sv
        for who, stroke, shot, q in sh:
            shots[(stroke, shot)] += 1
        if sh:
            ends[(sh[-1][2], call)] += 1
        if w:
            wins[w] += 1
            score[w] += 1
            server = w
    n = len(lengths)
    print(f"points {n}  wins {dict(wins)}  calls {dict(calls)}")
    print(f"shots/rally mean {sum(lengths) / n:.1f}  median {sorted(lengths)[n // 2]}  max {max(lengths)}")
    print("length histogram:", dict(sorted(Counter(min(x, 20) for x in lengths).items())))
    print("max shuttle height: median %.0f  p90 %.0f  max %.0f" % (
        sorted(heights)[n // 2], sorted(heights)[int(n * .9)], max(heights)))
    print("solves per shot: mean %.1f  max %d" % (sum(solves) / len(solves), max(solves)))
    print("strokes/shots:", ", ".join(f"{s}/{t}:{c}" for (s, t), c in shots.most_common()))
    print("last shot + call:", ", ".join(f"{s}->{c}:{k}" for (s, c), k in ends.most_common(14)))


def match(a):
    rng = random.Random(a.seed)
    sc, server, rallies = Score(), "red", 0
    lv_b = a.level if a.vs is None else a.vs
    while True:
        w, call, sh, mz, sv = play_rally(rng, a.level, lv_b, server, sc.points[server])
        rallies += 1
        res = sc.add(w)
        server = w
        if res != "point":
            print(f"game to {w}: {sc.points['red']}-{sc.points['blue']} (games {sc.games})")
            if res == "match":
                break
            sc.new_game()
    print("rallies", rallies)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", type=int, default=300)
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--vs", type=int, default=None)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--women", action="store_true")
    ap.add_argument("--match", action="store_true")
    ap.add_argument("--trace", type=int, default=0)
    a = ap.parse_args()
    if a.trace:
        rng = random.Random(a.seed)
        for _ in range(a.trace):
            res = play_rally(rng, a.level, a.level if a.vs is None else a.vs, "red", 0, trace=True)
            print("RESULT", res[0], res[1], "max z %.0f" % res[3])
        return
    match(a) if a.match else stats(a)


if __name__ == "__main__":
    main()
