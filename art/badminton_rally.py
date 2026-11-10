#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.6", "pillow>=10"]
# ///
"""Draw a looping pixel-art badminton rally in Aseprite through aseprite-mcp.

The script only decides *what* to draw. Every pixel reaches Aseprite through
the MCP server's own tools: create_canvas, rename_layer, add_layer,
add_frames, draw_rectangle_at, draw_line_at, draw_rows, propagate_cels,
set_frame_duration_all, set_frame_duration, set_tag, export_animation,
export_spritesheet and export_frame.

  # Drive the real MCP server (needs a full Aseprite; the trial cannot
  # run scripts or save, so the server fails with it):
  uv run badminton_rally.py mcp --mcp-dir ~/aseprite-mcp \
      --aseprite ~/aseprite-src/build/bin/aseprite --out ~/badminton

  # Render the same tool calls locally with Pillow (no Aseprite needed):
  uv run badminton_rally.py preview --out ./preview

  # Write the planned tool calls as JSON:
  uv run badminton_rally.py plan --out ./plan.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Scene constants
# --------------------------------------------------------------------------

W, H = 192, 108          # canvas
FRAMES = 24              # one full rally: red clear (1-12), blue clear (13-24)
HALF = FRAMES // 2
GROUND = 88              # y of the players' ground contact
RED_X, BLUE_X = 46, 146  # players' root x (feet centre)
NET_X = 96

FRAME_MS = 90            # normal frame (GIF delays are 10 ms steps)
HIT_MS = 160             # hit-stop on the contact frames

OUT = "#191a26"          # outline / near-black

PLAYERS = {
    "red": dict(
        shirt=("#d94a4a", "#a23434"),
        shorts=("#2c2c40", "#202030"),
        skin=("#f0bd8e", "#c98d63"),
        hair=("#5a341f", "#3e2416"),
        sock="#f4f4f4", shoe="#f4f4f4", sole="#d94a4a",
    ),
    "blue": dict(
        shirt=("#3f84dc", "#2b5ea6"),
        shorts=("#eef0f4", "#bfc5cf"),
        skin=("#a36a44", "#7a4c2f"),
        hair=("#2f2b3d", "#221f2d"),
        sock="#f4f4f4", shoe="#f4f4f4", sole="#3f84dc",
    ),
}

RACKET_FRAME = "#eef1f6"
RACKET_SHAFT = "#9aa3b2"
RACKET_GRIP = "#3b3b4d"
RACKET_STRINGS = "#d8e0ea70"   # semi-transparent string bed

SHUTTLE_CORK = "#f6edd6"
SHUTTLE_CORK_SHADE = "#c8ad7f"
SHUTTLE_FEATHER = "#ffffff"
SHUTTLE_FEATHER_EDGE = "#c3cad6"
TRAIL = "#ffffff60"
FLASH = "#fff2a0"
SHADOW = "#0a0e1a66"

# --------------------------------------------------------------------------
# Small raster helpers (root-relative integer pixel coords, y down)
# --------------------------------------------------------------------------


def rgba(hexstr: str) -> tuple[int, int, int, int]:
    h = hexstr.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r, g, b, int(h[6:8], 16) if len(h) == 8 else 255


def to_hex(c) -> str:
    r, g, b, a = c
    return f"#{r:02x}{g:02x}{b:02x}" + ("" if a == 255 else f"{a:02x}")


def over(dst: str, src: str) -> str:
    """src composited over dst (Porter-Duff), as hex."""
    sr, sg, sb, sa = rgba(src)
    dr, dg, db, da = rgba(dst)
    sa_, da_ = sa / 255, da / 255
    oa = sa_ + da_ * (1 - sa_)
    if oa == 0:
        return "#00000000"
    mix = lambda s, d: round((s * sa_ + d * da_ * (1 - sa_)) / oa)
    return to_hex((mix(sr, dr), mix(sg, dg), mix(sb, db), round(oa * 255)))


def darken(c: str, k: float) -> str:
    r, g, b, a = rgba(c)
    return to_hex((round(r * k), round(g * k), round(b * k), a))


def tint(base: str, overlay: str) -> str:
    """Opaque result of overlay over an opaque base (for putPixel layers)."""
    return over(base, overlay)


class Raster:
    """A sparse pixel grid: {(x, y): '#rrggbb[aa]'}.

    Writes composite like paint: a semi-transparent colour over an existing
    pixel is blended into it, because Aseprite's putPixel (what draw_rows
    uses) replaces pixels rather than blending them.
    """

    def __init__(self):
        self.px: dict[tuple[int, int], str] = {}

    def set(self, key, c):
        if key in self.px and rgba(c)[3] < 255:
            self.px[key] = over(self.px[key], c)
        else:
            self.px[key] = c

    def put(self, x, y, c, only_empty=False):
        key = (int(round(x)), int(round(y)))
        if only_empty and key in self.px:
            return
        self.set(key, c)

    def capsule(self, p, q, r, color, only_empty=False):
        (x0, y0), (x1, y1) = p, q
        minx, maxx = math.floor(min(x0, x1) - r), math.ceil(max(x0, x1) + r)
        miny, maxy = math.floor(min(y0, y1) - r), math.ceil(max(y0, y1) + r)
        dx, dy = x1 - x0, y1 - y0
        ll = dx * dx + dy * dy
        for y in range(miny, maxy + 1):
            for x in range(minx, maxx + 1):
                t = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / ll))
                cx, cy = x0 + t * dx, y0 + t * dy
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    if only_empty and (x, y) in self.px:
                        continue
                    self.set((x, y), color)

    def disc(self, c, r, color):
        self.capsule(c, c, r, color)

    def line(self, p, q, color, only_empty=False):
        for x, y in bresenham(round(p[0]), round(p[1]), round(q[0]), round(q[1])):
            self.put(x, y, color, only_empty)

    def outline(self, color, skip=()):
        """1 px outline on the outside of the shape (4-neighbourhood)."""
        solid = {k for k, v in self.px.items() if v not in skip}
        edge = set()
        for (x, y) in solid:
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n not in self.px:
                    edge.add(n)
        for k in edge:
            self.px[k] = color

    def mirrored(self):
        r = Raster()
        r.px = {(-x, y): c for (x, y), c in self.px.items()}
        return r

    def to_rows(self, ox, oy):
        """-> (x, y, rows, legend) for draw_rows, placed with root at (ox, oy)."""
        xs = [x for x, _ in self.px]
        ys = [y for _, y in self.px]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        legend: dict[str, str] = {}
        rev: dict[str, str] = {}
        rows = []
        for y in range(y0, y1 + 1):
            row = []
            for x in range(x0, x1 + 1):
                c = self.px.get((x, y))
                if c is None:
                    row.append(".")
                    continue
                if c not in rev:
                    ch = pool[len(rev)]
                    rev[c] = ch
                    legend[ch] = c
                row.append(rev[c])
            rows.append("".join(row))
        return ox + x0, oy + y0, rows, legend


def bresenham(x0, y0, x1, y1):
    """Same integer line as aseprite-mcp's draw_line_at (Lua) uses."""
    pts = []
    dx, sx = abs(x1 - x0), (1 if x0 < x1 else -1)
    dy, sy = -abs(y1 - y0), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


def lerp(p, q, t):
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def polar(p, ang_deg, dist):
    a = math.radians(ang_deg)
    return (p[0] + math.cos(a) * dist, p[1] + math.sin(a) * dist)


# --------------------------------------------------------------------------
# Player poses: a right-handed player facing right (+x); y is up-negative,
# root (0, 0) is the ground under the body. The blue player is the mirror
# image (so blue plays left-handed).
# --------------------------------------------------------------------------

BASE = dict(
    head=(1, -27), sh=(0, -21), hip=(-1, -12),
    fk=(3, -7), fa=(4, -2), bk=(-4, -7), ba=(-5, -2),
    re=(3, -17), rh=(6, -20), ang=-75,
    fe=(-1, -16), fh=(3, -15),
    racket_behind=False, smear=None, lift=0, back_heel=False,
)


def pose(**kw):
    p = dict(BASE)
    p.update(kw)
    return p


POSES = {
    "ready_a": pose(),
    "ready_b": pose(head=(1, -26), sh=(0, -20), hip=(-1, -11), fk=(4, -6), bk=(-5, -6),
                    re=(3, -16), rh=(6, -19), fe=(-1, -15), fh=(3, -14)),
    # turning side-on, free arm tracking the shuttle, racket raised
    "prep": pose(head=(0, -27), sh=(-1, -21), hip=(-1, -12),
                 fk=(3, -7), fa=(5, -2), bk=(-4, -7), ba=(-6, -2),
                 fe=(2, -25), fh=(5, -29), re=(-4, -23), rh=(-6, -28), ang=-95),
    # "back scratch": elbow high, racket dropped behind the back
    "windup": pose(head=(-1, -27), sh=(-1, -21), hip=(0, -12),
                   fk=(3, -7), fa=(5, -2), bk=(-4, -6), ba=(-6, -2),
                   fe=(3, -24), fh=(5, -28), re=(-3, -30), rh=(-6, -25), ang=115,
                   racket_behind=True),
    # whip forward: racket still trailing, motion smear behind the head
    "swing": pose(head=(0, -28), sh=(0, -22), hip=(0, -12),
                  fk=(3, -7), fa=(4, -2), bk=(-3, -7), ba=(-5, -3), back_heel=True,
                  fe=(1, -18), fh=(3, -16), re=(-2, -29), rh=(-1, -34), ang=-100,
                  smear=dict(pivot=(-1, -27), r=12, a0=-215, a1=-108)),
    # contact: arm fully extended above and in front of the head
    "contact": pose(head=(-1, -28), sh=(0, -22), hip=(0, -12), lift=1,
                    fk=(3, -7), fa=(4, -2), bk=(-3, -7), ba=(-5, -3), back_heel=True,
                    fe=(1, -17), fh=(3, -15), re=(3, -28), rh=(4, -33), ang=-70),
    # follow-through across the body, back leg scissoring forward
    "follow": pose(head=(3, -26), sh=(2, -20), hip=(0, -12),
                   fk=(4, -7), fa=(6, -2), bk=(-1, -7), ba=(-2, -2),
                   re=(5, -16), rh=(3, -12), ang=165, racket_behind=True,
                   fe=(-2, -17), fh=(-5, -15)),
    "recover": pose(head=(2, -27), sh=(1, -21), hip=(-1, -12),
                    re=(4, -16), rh=(6, -18), ang=-55,
                    fe=(-1, -16), fh=(2, -14)),
}

# Pose per frame for the player who hits at frame 0 (the other player is the
# same timeline shifted by half a rally).
TIMELINE = (
    ["contact", "follow", "follow", "recover"]
    + ["ready_a", "ready_a", "ready_b", "ready_b"] * 3 + ["ready_a", "ready_a", "ready_b"]
    + ["prep", "prep", "windup", "windup", "swing"]
)
assert len(TIMELINE) == FRAMES, len(TIMELINE)

RACKET_GRIP_LEN = 2
RACKET_HEAD_DIST = 9.0
RACKET_HEAD_A = 3.3   # half-length along the racket
RACKET_HEAD_B = 2.4   # half-width


def racket_head_centre(p):
    return polar(p["rh"], p["ang"], RACKET_HEAD_DIST)


def draw_racket(r: Raster, p):
    hand, ang = p["rh"], p["ang"]
    a = math.radians(ang)
    d = (math.cos(a), math.sin(a))
    n = (-d[1], d[0])
    r.line(polar(hand, ang, 2), polar(hand, ang, 5.6), RACKET_SHAFT)
    c = racket_head_centre(p)
    box = math.ceil(RACKET_HEAD_A) + 1
    for y in range(math.floor(c[1]) - box, math.ceil(c[1]) + box + 1):
        for x in range(math.floor(c[0]) - box, math.ceil(c[0]) + box + 1):
            u = ((x - c[0]) * d[0] + (y - c[1]) * d[1]) / RACKET_HEAD_A
            v = ((x - c[0]) * n[0] + (y - c[1]) * n[1]) / RACKET_HEAD_B
            e = u * u + v * v
            if e <= 1.0:
                r.set((x, y), RACKET_FRAME if e >= 0.42 else RACKET_STRINGS)
    r.line(polar(hand, ang, -1), polar(hand, ang, RACKET_GRIP_LEN), RACKET_GRIP)


def draw_leg(r: Raster, p, knee, ankle, col, shade: bool):
    i = 1 if shade else 0
    hip = p["hip"]
    top = lerp(hip, knee, 0.55)
    r.capsule(hip, top, 1.6, col["shorts"][i])
    r.capsule(top, knee, 1.05, col["skin"][i], only_empty=False)
    r.capsule(knee, ankle, 1.0, col["skin"][i])
    ax, ay = round(ankle[0]), round(ankle[1])
    r.put(ax, ay - 1, col["sock"])
    r.put(ax + 1, ay - 1, col["sock"])
    if p.get("back_heel") and shade:
        # pushing off the toes: heel raised
        r.put(ax, ay, col["shoe"])
        r.put(ax + 1, ay, col["shoe"])
        r.put(ax + 1, ay + 1, col["sole"])
        r.put(ax + 2, ay + 1, col["sole"])
    else:
        for x in range(ax - 1, ax + 3):
            r.put(x, ay, col["shoe"])
            r.put(x, ay + 1, col["sole"] if x >= ax + 1 else col["shoe"])


def draw_arm(r: Raster, sh, elbow, hand, col, shade: bool):
    i = 1 if shade else 0
    sleeve = lerp(sh, elbow, 0.45)
    r.capsule(sh, sleeve, 1.25, col["shirt"][i])
    r.capsule(sleeve, elbow, 0.95, col["skin"][i])
    r.capsule(elbow, hand, 0.95, col["skin"][i])
    r.disc(hand, 1.0, col["skin"][i])


def draw_head(r: Raster, c, col):
    cx, cy = c
    rad = 3.3
    for y in range(math.floor(cy - rad), math.ceil(cy + rad) + 1):
        for x in range(math.floor(cx - rad), math.ceil(cx + rad) + 1):
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy <= rad * rad:
                hair = dy < -0.9 or (dx < -1.1 and dy < 1.6)
                if hair:
                    r.px[(x, y)] = col["hair"][1] if dx < -1.5 and dy > -1.5 else col["hair"][0]
                else:
                    r.px[(x, y)] = col["skin"][0]
    r.put(cx + 1.6, cy - 0.2, OUT)                    # eye
    r.put(cx + 0.4, cy + 1.6, col["skin"][1])          # jaw shade


def render_player(name: str, pose_name: str) -> Raster:
    col = PLAYERS[name]
    p = dict(POSES[pose_name])
    lift = p["lift"]
    if lift:
        for k in ("head", "sh", "hip", "fk", "fa", "bk", "ba", "re", "rh", "fe", "fh"):
            p[k] = (p[k][0], p[k][1] - lift)
    r = Raster()
    if p["racket_behind"]:
        draw_racket(r, p)
    draw_arm(r, p["sh"], p["fe"], p["fh"], col, shade=True)          # far arm
    draw_leg(r, p, p["bk"], p["ba"], col, shade=True)                 # far leg
    # torso and shorts
    r.capsule(p["sh"], lerp(p["sh"], p["hip"], 0.8), 2.5, col["shirt"][0])
    back = (p["sh"][0] - 1.6, p["sh"][1] + 1)
    r.capsule(back, (p["hip"][0] - 1.6, p["hip"][1] - 2), 0.9, col["shirt"][1])
    r.capsule((p["hip"][0], p["hip"][1] - 1.5), p["hip"], 2.6, col["shorts"][0])
    draw_leg(r, p, p["fk"], p["fa"], col, shade=False)                # near leg
    neck_top = (p["head"][0] - 0.5, p["head"][1] + 2.5)
    r.capsule(neck_top, p["sh"], 0.8, col["skin"][1])
    draw_head(r, p["head"], col)
    # The racket arm is the near arm: draw it on its own, then darken the body
    # pixels it borders (a selective contour) so it reads in front of the
    # head and torso instead of merging with same-coloured skin.
    arm = Raster()
    if not p["racket_behind"]:
        draw_racket(arm, p)
    draw_arm(arm, p["sh"], p["re"], p["rh"], col, shade=False)
    for (x, y), c in list(r.px.items()):
        if (x, y) not in arm.px and any(n in arm.px for n in
                                        ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))):
            r.px[(x, y)] = darken(c, 0.62)
    for k, c in arm.px.items():
        r.set(k, c)
    r.outline(OUT, skip=(RACKET_STRINGS,))
    if p["smear"]:
        s = p["smear"]
        steps = 60
        for k in range(steps, -1, -1):                    # strongest (racket end) first
            t = k / steps
            a = s["a0"] + (s["a1"] - s["a0"]) * t
            alpha = (0x22, 0x3a, 0x5c)[min(2, int(t * 3))]   # 3 fixed levels
            for rr in (s["r"] - 3.0, s["r"] - 2.0, s["r"] - 1.0, s["r"], s["r"] + 0.8):
                x, y = polar(s["pivot"], a, rr)
                r.put(x, y - lift, f"#ffffff{alpha:02x}", only_empty=True)
    return r


def contact_point(name: str):
    """Scene coords of the racket head centre in the contact pose."""
    p = POSES["contact"]
    cx, cy = racket_head_centre(p)
    cy -= p["lift"]
    if name == "red":
        return (RED_X + cx, GROUND + cy)
    return (BLUE_X - cx, GROUND + cy)


# --------------------------------------------------------------------------
# Shuttle: a high clear with quadratic air drag (fast off the racket, steep
# fall at the end), solved so it lands on the other racket after HALF frames.
# --------------------------------------------------------------------------

GRAVITY = 1.7    # px / frame^2
DRAG = 0.02      # 1 / px
SUBSTEPS = 40


def simulate(p0, v0, frames):
    """Positions and velocities at every whole frame 0..frames."""
    x, y = p0
    vx, vy = v0
    dt = 1.0 / SUBSTEPS
    out = [((x, y), (vx, vy))]
    for _ in range(frames):
        for _ in range(SUBSTEPS):
            sp = math.hypot(vx, vy)
            ax, ay = -DRAG * sp * vx, GRAVITY - DRAG * sp * vy
            vx += ax * dt
            vy += ay * dt
            x += vx * dt
            y += vy * dt
        out.append(((x, y), (vx, vy)))
    return out


def solve_clear(p0, p1, frames):
    """Find launch velocity so the shuttle reaches p1 at the last frame."""
    v = [(p1[0] - p0[0]) / frames * 2.2, -9.0]
    for _ in range(60):
        (x, y), _ = simulate(p0, v, frames)[-1]
        ex, ey = x - p1[0], y - p1[1]
        if abs(ex) < 1e-6 and abs(ey) < 1e-6:
            break
        h = 1e-4
        (xa, ya), _ = simulate(p0, (v[0] + h, v[1]), frames)[-1]
        (xb, yb), _ = simulate(p0, (v[0], v[1] + h), frames)[-1]
        j = [[(xa - x) / h, (xb - x) / h], [(ya - y) / h, (yb - y) / h]]
        det = j[0][0] * j[1][1] - j[0][1] * j[1][0]
        v[0] -= (j[1][1] * ex - j[0][1] * ey) / det
        v[1] -= (-j[1][0] * ex + j[0][0] * ey) / det
    return simulate(p0, v, frames)


def shuttle_raster(pos, vel) -> Raster:
    r = Raster()
    sp = math.hypot(*vel) or 1.0
    d = (vel[0] / sp, vel[1] / sp)
    n = (-d[1], d[0])
    px, py = pos
    for y in range(math.floor(py) - 6, math.ceil(py) + 7):
        for x in range(math.floor(px) - 6, math.ceil(px) + 7):
            qx, qy = x - px, y - py
            along = qx * d[0] + qy * d[1]        # + towards the cork
            perp = qx * n[0] + qy * n[1]
            if -0.2 <= along <= 1.3 and abs(perp) <= 0.95:
                r.px[(x, y)] = SHUTTLE_CORK if along > 0.5 else SHUTTLE_CORK_SHADE
            elif -4.3 <= along < -0.2:
                lim = 0.7 + (-along - 0.2) / 4.1 * 1.6
                if abs(perp) <= lim:
                    r.px[(x, y)] = SHUTTLE_FEATHER_EDGE if abs(perp) > lim - 0.75 and -along > 1.5 else SHUTTLE_FEATHER
    return r


def shuttle_track():
    """Per frame: (pos, vel, prev_pos, t) for the loop; t = frames since the hit."""
    a, b = contact_point("red"), contact_point("blue")
    there = solve_clear(a, b, HALF)
    back = [((2 * NET_X - p[0], p[1]), (-v[0], v[1])) for p, v in there]   # mirror image
    track = []
    for f in range(FRAMES):
        flight, t = (there, f) if f < HALF else (back, f - HALF)
        pos, vel = flight[t]
        if t == 0:
            # at contact the shuttle is still arriving: cork faces the racket
            prev_flight = back if flight is there else there
            vel = prev_flight[HALF][1]
        prev = flight[t - 1][0] if t > 0 else None
        track.append((pos, vel, prev, t))
    return track, there


# --------------------------------------------------------------------------
# Background, net and scoreboard
# --------------------------------------------------------------------------

C = dict(
    ceiling="#121827", light="#fff3c6", glow="#7c7a68",
    wall_hi="#1d2a45", trim="#33496f", wall_lo="#25375a", skirting="#141b2c",
    boards=("#2f5f96", "#8f3a3a", "#a8842f", "#2f7f62"),
    wood="#9a693e", wood_seam="#86592f", court="#2f7d52", line="#eef0e6",
    panel="#0d111d", panel_rim="#3a4a68", red_digit="#ff6464", blue_digit="#62a8ff",
    colon="#cfd6e2",
    post="#6c7587", post_hi="#a3acbe", base="#2a2f3b", tape="#ffffff", mesh="#c4ccd8",
)

FAR_Y, NEAR_Y = 74, 96          # court sidelines (rows): far and near
COURT_HALF = 84                 # net to baseline along the court, px
SKEW = 0.5                      # oblique floor: each row further back shifts 0.5 px right
NET_H = 28                      # post height (1.55 m at the players' scale)
MESH_H = 14                     # depth of the netting (0.76 m)
NET_MESH = "#dfe5ee9c"          # semi-transparent netting
NET_CORD = "#c9d1dc"            # bottom cord of the net

DIGITS = {
    "0": ["###", "#.#", "#.#", "#.#", "###"],
    "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"],
    "9": ["###", "#.#", "###", "..#", "###"],
}


def court_x(frac_from_net: float, y: float, side: int) -> int:
    """x of a court point: frac 0 = net, 1 = baseline; side -1 left, +1 right; on row y.

    The floor is an oblique view (rows further back shift right), so the net,
    which spans the court's width, shows as an angled panel between its two
    sideline posts rather than edge-on.
    """
    return math.floor(NET_X + side * frac_from_net * COURT_HALF + (GROUND - y) * SKEW + 0.5)


def depth_line(frac_from_net: float, side: int):
    """Pixels of a line across the court's width (far sideline to near sideline)."""
    return bresenham(court_x(frac_from_net, FAR_Y, side), FAR_Y,
                     court_x(frac_from_net, NEAR_Y, side), NEAR_Y)


def x_on_row(pixels, y, pick=min):
    return pick(x for x, yy in pixels if yy == y)


def court_mat_rows():
    left, right = depth_line(1, -1), depth_line(1, 1)
    x0, x1 = min(x for x, _ in left), max(x for x, _ in right)
    rows = []
    for y in range(FAR_Y, NEAR_Y + 1):
        xl, xr = x_on_row(left, y, min), x_on_row(right, y, max)
        rows.append("".join("g" if xl <= x <= xr else "." for x in range(x0, x1 + 1)))
    return x0, FAR_Y, rows


def court_lines():
    """Line segments (x1, y1, x2, y2) of a doubles court."""
    segs = []
    short_srv = 1.98 / 6.70
    long_dbl = (6.70 - 0.76) / 6.70
    left, right = depth_line(1, -1), depth_line(1, 1)
    for y in (FAR_Y, NEAR_Y, FAR_Y + 2, NEAR_Y - 2):              # doubles + singles sidelines
        segs.append((x_on_row(left, y, min), y, x_on_row(right, y, max), y))
    ym = (FAR_Y + NEAR_Y) // 2                                      # centre line row
    for side in (-1, 1):
        for frac in (1.0, long_dbl, short_srv):                     # baseline, service lines
            segs.append((court_x(frac, FAR_Y, side), FAR_Y, court_x(frac, NEAR_Y, side), NEAR_Y))
        base = left if side < 0 else right
        segs.append((x_on_row(depth_line(short_srv, side), ym), ym, x_on_row(base, ym), ym))
    return segs


def net_raster():
    """The net between its two sideline posts, as one draw_rows block.

    Returns (raster, near_post_pixels): the near post stands in front of the
    players' plane, so floor shadows must not be drawn over it.
    """
    r = Raster()
    fx, nx = court_x(0, FAR_Y, 1), court_x(0, NEAR_Y, 1)      # floor under each post
    ftop, ntop = FAR_Y - NET_H, NEAR_Y - NET_H
    # far post, base outside the court (behind the far sideline)
    for x in range(fx - 3, fx + 3):
        for y in (FAR_Y - 1, FAR_Y):
            r.put(x, y, C["base"])
    for y in range(ftop, FAR_Y + 1):
        r.put(fx - 1, y, C["post_hi"])
        r.put(fx, y, C["post"])
    # netting under the tape: see-through mesh plus a bottom cord
    tape = bresenham(fx, ftop, nx, ntop)
    cols: dict[int, list[int]] = {}
    for x, y in tape:
        cols.setdefault(x, []).append(y)
    for x, ys in cols.items():
        top, bottom = max(ys) + 2, min(ys) + MESH_H
        for y in range(top, bottom):
            if (x + y) % 2 == 0:
                r.put(x, y, NET_MESH)
        r.put(x, bottom, NET_CORD)
    # white tape along the top, 2 px
    for x, y in tape:
        r.put(x, y, C["tape"])
        r.put(x, y + 1, C["tape"])
    # near post in front, base outside the court (in front of the near sideline)
    near: set[tuple[int, int]] = set()
    for x in range(nx - 3, nx + 3):
        for y in (NEAR_Y, NEAR_Y + 1):
            r.px[(x, y)] = C["base"]
            near.add((x, y))
    for y in range(ntop, NEAR_Y + 1):
        for x, c in ((nx - 1, C["post_hi"]), (nx, C["post"])):
            r.px[(x, y)] = c
            near.add((x, y))
    return r, near


# --------------------------------------------------------------------------
# The plan: an ordered list of MCP tool calls
# --------------------------------------------------------------------------


@dataclass
class Call:
    tool: str
    args: dict = field(default_factory=dict)


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

    # -- sprite, layers, frames ------------------------------------------
    calls.append(Call("create_canvas", {"width": W, "height": H, "filename": sprite}))
    add("rename_layer", layer_name="Layer 1", new_name="background")
    for name in ("net", "shadows", "player_red", "player_blue", "shuttle"):
        add("add_layer", layer_name=name)
    add("add_frames", count=FRAMES - 1, duration_ms=FRAME_MS)
    add("set_frame_duration_all", duration_ms=FRAME_MS)

    # -- background (frame 1) ---------------------------------------------
    bg = "background"
    rect(bg, 0, 0, W, 42, C["wall_hi"])
    rect(bg, 0, 0, W, 6, C["ceiling"])
    for lx in (10, 58, 114, 162):
        rect(bg, lx, 1, 20, 2, C["light"])
        rect(bg, lx + 2, 3, 16, 1, C["glow"])
    rect(bg, 0, 42, W, 1, C["trim"])
    rect(bg, 0, 43, W, 27, C["wall_lo"])
    for i, bx in enumerate((4, 52, 104, 152)):                      # sponsor boards
        hi = tint(C["boards"][i], "#ffffff40")
        rect(bg, bx, 56, 36, 12, C["boards"][i])
        line(bg, bx, 56, bx + 35, 56, hi)
        rect(bg, bx + 4, 60, 28, 1, hi)
        rect(bg, bx + 8, 63, 20, 1, hi)
    rect(bg, 0, 70, W, 2, C["skirting"])
    rect(bg, 0, 72, W, H - 72, C["wood"])
    for sy in (75, 79, 84, 90, 97, 105):
        line(bg, 0, sy, W - 1, sy, C["wood_seam"])
    mx, my, mrows = court_mat_rows()
    rows(bg, 1, mrows, x=mx, y=my, legend={"g": C["court"]})
    for x1, y1, x2, y2 in court_lines():
        line(bg, x1, y1, x2, y2, C["line"])
    # scoreboard: game point, 20-19
    sbx = 8                      # upper-left wall, clear of the shuttle's arc
    rect(bg, sbx, 11, 36, 15, C["panel_rim"])
    rect(bg, sbx + 1, 12, 34, 13, C["panel"])
    score = [("2", 5, "red_digit"), ("0", 9, "red_digit"),
             ("1", 24, "blue_digit"), ("9", 28, "blue_digit")]
    for ch, dx, colour in score:
        rows(bg, 1, [s.replace("#", "D") for s in DIGITS[ch]], x=sbx + dx, y=16,
             legend={"D": C[colour]})
    rows(bg, 1, ["c", ".", ".", "c"], x=sbx + 17, y=17, legend={"c": C["colon"]})

    # -- net (frame 1) ----------------------------------------------------
    net, near_post = net_raster()
    rows("net", 1, net)

    # -- copy the static layers to every frame ----------------------------
    add("propagate_cels", layer_names=["background", "net"], source_frame=1,
        start_frame=1, end_frame=FRAMES)

    # -- per-frame: shadows, players, shuttle ---------------------------------
    track, _ = shuttle_track()
    for f in range(FRAMES):
        fi = f + 1
        red_pose = TIMELINE[f]
        blue_pose = TIMELINE[(f + HALF) % FRAMES]

        sh = Raster()
        for root, pname in ((RED_X, red_pose), (BLUE_X, blue_pose)):
            half_w = 5.5 if POSES[pname]["lift"] == 0 else 4.5
            for x in range(math.floor(root - half_w), math.ceil(root + half_w) + 1):
                for y in (GROUND - 1, GROUND, GROUND + 1):
                    if ((x - root) / half_w) ** 2 + ((y - GROUND) / 1.4) ** 2 <= 1.0:
                        sh.put(x, y, SHADOW)
        (sx, sy), _, _, _ = track[f]
        height = GROUND - sy
        sw = 2 if height < 25 else 1
        for x in range(round(sx) - sw, round(sx) + sw + 1):
            sh.put(x, GROUND + 1, SHADOW)
        for k in near_post & set(sh.px):                           # near post is in front
            del sh.px[k]
        rows("shadows", fi, sh)

        red = render_player("red", red_pose)
        x, y, rws, legend = red.to_rows(RED_X, GROUND)
        rows("player_red", fi, rws, x=x, y=y, legend=legend)
        blue = render_player("blue", blue_pose).mirrored()
        x, y, rws, legend = blue.to_rows(BLUE_X, GROUND)
        rows("player_blue", fi, rws, x=x, y=y, legend=legend)

        pos, vel, prev, t = track[f]
        s = shuttle_raster(pos, vel)
        if prev is not None and t <= 2:                            # speed trail
            for k in range(1, 9):
                q = lerp(prev, pos, k / 10)
                if math.dist(q, pos) > 3.2:
                    s.put(q[0], q[1], TRAIL, only_empty=True)
        if t == 0:                                                 # impact flash
            cx, cy = round(pos[0]), round(pos[1])
            for dx, dy in ((5, 0), (6, 0), (-5, 0), (-6, 0), (0, 5), (0, 6), (0, -5), (0, -6),
                           (4, 4), (-4, 4), (4, -4), (-4, -4)):
                s.put(cx + dx, cy + dy, FLASH, only_empty=True)
        rows("shuttle", fi, s)

    # -- timing, tags --------------------------------------------------------
    for fi in (1, HALF + 1):
        add("set_frame_duration", frame_index=fi, duration_ms=HIT_MS)
    add("set_tag", name="red_clear", from_frame=1, to_frame=HALF, direction="forward")
    add("set_tag", name="blue_clear", from_frame=HALF + 1, to_frame=FRAMES, direction="forward")

    # -- exports ---------------------------------------------------------------
    stem = os.path.join(out_dir, "badminton_rally")
    add("export_animation", output_filename=stem + ".gif", scale=4)
    add("export_spritesheet", output_filename=stem + "_sheet.png", sheet_type="rows",
        data_filename=stem + "_sheet.json", scale=1)
    add("export_frame", frame_index=1, output_filename=stem + "_frame1.png", scale=4)
    return calls


# --------------------------------------------------------------------------
# Backend 1: the real aseprite-mcp server over stdio
# --------------------------------------------------------------------------

FAIL_PREFIXES = ("Failed", "Invalid", "Error", "ERROR", "Unsupported", "File ")


def looks_failed(text: str) -> bool:
    return text.startswith(FAIL_PREFIXES) or " not found" in text


async def run_mcp(calls: list[Call], mcp_dir: str, aseprite: str | None, uv: str, quiet: bool):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)           # this script's uv env, not the server's
    if aseprite:
        env["ASEPRITE_PATH"] = aseprite
    env.setdefault("ASEPRITE_TIMEOUT_SECONDS", "120")
    env.setdefault("FASTMCP_LOG_LEVEL", "WARNING")   # hide per-request INFO lines
    params = StdioServerParameters(
        command=uv, args=["--directory", mcp_dir, "run", "-m", "aseprite_mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            available = {t.name for t in (await session.list_tools()).tools}
            missing = sorted({c.tool for c in calls} - available)
            if missing:
                sys.exit(f"The MCP server has no tool(s) {missing}; update aseprite-mcp.")
            for i, c in enumerate(calls, 1):
                res = await session.call_tool(c.tool, c.args)
                text = " ".join(getattr(p, "text", "") for p in res.content).strip()
                # the mcp SDK 2.x names it is_error; 1.x used isError
                is_error = getattr(res, "is_error", None)
                if is_error is None:
                    is_error = getattr(res, "isError", False)
                if is_error or looks_failed(text):
                    sys.exit(f"[{i}/{len(calls)}] {c.tool} failed: {text}")
                if not quiet:
                    print(f"[{i:3}/{len(calls)}] {c.tool:22} {text[:110]}")


# --------------------------------------------------------------------------
# Backend 2: a local stand-in that applies the same calls with Pillow.
# It mirrors the server's pixel semantics (draw_rows / draw_line_at replace
# pixels, filled rectangles paint with Aseprite's simple ink) so the preview
# matches what Aseprite will produce.
# --------------------------------------------------------------------------


class Preview:
    def __init__(self):
        from PIL import Image  # noqa: F401  (fail early if Pillow is missing)
        self.s: dict[str, dict] = {}

    def call(self, c: Call):
        getattr(self, "t_" + c.tool)(**c.args)

    # -- helpers ----------------------------------------------------------------
    def _cel(self, f, layer, frame):
        from PIL import Image
        spr = self.s[f]
        assert layer in spr["layers"], f"layer {layer!r} not found"
        assert 1 <= frame <= len(spr["dur"]), f"frame {frame} out of range"
        key = (layer, frame)
        if key not in spr["cels"]:
            spr["cels"][key] = Image.new("RGBA", (spr["w"], spr["h"]), (0, 0, 0, 0))
        return spr["cels"][key]

    def _put(self, img, x, y, c):
        if 0 <= x < img.width and 0 <= y < img.height:
            img.putpixel((x, y), c)

    def _frame(self, f, frame):
        from PIL import Image
        spr = self.s[f]
        out = Image.new("RGBA", (spr["w"], spr["h"]), (0, 0, 0, 0))
        for layer in spr["layers"]:
            cel = spr["cels"].get((layer, frame))
            if cel is not None:
                out = Image.alpha_composite(out, cel)
        return out

    # -- tools --------------------------------------------------------------------
    def t_create_canvas(self, width, height, filename):
        self.s[filename] = dict(w=width, h=height, layers=["Layer 1"], dur=[100], cels={}, tags={})

    def t_rename_layer(self, filename, layer_name, new_name):
        spr = self.s[filename]
        i = spr["layers"].index(layer_name)
        spr["layers"][i] = new_name
        spr["cels"] = {((new_name if l == layer_name else l), fr): im for (l, fr), im in spr["cels"].items()}

    def t_add_layer(self, filename, layer_name, group=""):
        self.s[filename]["layers"].append(layer_name)

    def t_add_frames(self, filename, count, duration_ms=None):
        self.s[filename]["dur"] += [duration_ms or 100] * count

    def t_set_frame_duration_all(self, filename, duration_ms):
        spr = self.s[filename]
        spr["dur"] = [duration_ms] * len(spr["dur"])

    def t_set_frame_duration(self, filename, frame_index, duration_ms):
        self.s[filename]["dur"][frame_index - 1] = duration_ms

    def t_set_tag(self, filename, name, from_frame, to_frame, direction="forward"):
        self.s[filename]["tags"][name] = (from_frame, to_frame, direction)

    def t_draw_rectangle_at(self, filename, layer_name, frame_index, x, y, width, height,
                            color="#000000", fill=False, create_if_missing=True):
        from PIL import Image
        img = self._cel(filename, layer_name, frame_index)
        patch = Image.new("RGBA", img.size, (0, 0, 0, 0))
        c = rgba(color)
        for yy in range(y, y + height):
            for xx in range(x, x + width):
                if fill or yy in (y, y + height - 1) or xx in (x, x + width - 1):
                    self._put(patch, xx, yy, c)
        img.alpha_composite(patch)            # simple ink blends

    def t_draw_line_at(self, filename, layer_name, frame_index, x1, y1, x2, y2,
                       color="#000000", thickness=1, create_if_missing=True):
        assert thickness == 1
        img = self._cel(filename, layer_name, frame_index)
        for x, y in bresenham(x1, y1, x2, y2):
            self._put(img, x, y, rgba(color))  # putPixel replaces

    def t_draw_rows(self, filename, layer_name, frame_index, x, y, rows, legend,
                    outline=None, create_if_missing=True):
        assert outline is None
        img = self._cel(filename, layer_name, frame_index)
        width = len(rows[0])
        for r, row in enumerate(rows):
            assert len(row) == width, "ragged rows"
            for cidx, ch in enumerate(row):
                if ch in legend:
                    self._put(img, x + cidx, y + r, rgba(legend[ch]))

    def t_propagate_cels(self, filename, layer_names, source_frame, start_frame, end_frame,
                         replace=True):
        spr = self.s[filename]
        for fi in range(start_frame, end_frame + 1):
            if fi == source_frame:
                continue
            for layer in layer_names:
                src = spr["cels"].get((layer, source_frame))
                if src is not None and (replace or (layer, fi) not in spr["cels"]):
                    spr["cels"][(layer, fi)] = src.copy()

    def t_export_animation(self, filename, output_filename, tag="", scale=1, background=""):
        from PIL import Image
        spr = self.s[filename]
        frames = [self._frame(filename, i + 1) for i in range(len(spr["dur"]))]
        frames = [fr.resize((fr.width * scale, fr.height * scale), Image.NEAREST) for fr in frames]
        rgb = [fr.convert("RGB") for fr in frames]
        colours = sorted({c for fr in rgb for _, c in fr.getcolors(1 << 20)})
        assert len(colours) <= 256, f"{len(colours)} colours"
        pal = Image.new("P", (1, 1))
        pal.putpalette([v for c in colours for v in c] + [0] * (768 - 3 * len(colours)))
        pframes = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in rgb]
        pframes[0].save(output_filename, save_all=True, append_images=pframes[1:],
                        duration=spr["dur"], loop=0, disposal=1, optimize=False)

    def t_export_spritesheet(self, filename, output_filename, sheet_type="horizontal",
                             data_filename="", scale=1, padding=0, tag_name="",
                             data_format="json-array", list_tags=False):
        from PIL import Image
        spr = self.s[filename]
        n = len(spr["dur"])
        cols = math.ceil(math.sqrt(n)) if sheet_type == "rows" else n
        rows_n = math.ceil(n / cols)
        sheet = Image.new("RGBA", (cols * spr["w"], rows_n * spr["h"]), (0, 0, 0, 0))
        data = {"frames": [], "meta": {"size": {"w": sheet.width, "h": sheet.height},
                                       "frameTags": [{"name": k, "from": a - 1, "to": b - 1,
                                                      "direction": d}
                                                     for k, (a, b, d) in spr["tags"].items()]}}
        for i in range(n):
            x, y = (i % cols) * spr["w"], (i // cols) * spr["h"]
            sheet.alpha_composite(self._frame(filename, i + 1), (x, y))
            data["frames"].append({"filename": f"badminton_rally {i}.aseprite",
                                   "frame": {"x": x, "y": y, "w": spr["w"], "h": spr["h"]},
                                   "duration": spr["dur"][i]})
        sheet.save(output_filename)
        if data_filename:
            with open(data_filename, "w") as fh:
                json.dump(data, fh, indent=1)

    def t_export_frame(self, filename, frame_index, output_filename, scale=1):
        from PIL import Image
        fr = self._frame(filename, frame_index)
        fr.resize((fr.width * scale, fr.height * scale), Image.NEAREST).save(output_filename)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


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
        calls = build_plan("/ABS/PATH/badminton_rally.aseprite", "/ABS/PATH")
        with open(a.out, "w") as fh:
            json.dump([{"tool": c.tool, "arguments": c.args} for c in calls], fh, indent=1)
        print(f"{len(calls)} tool calls -> {a.out}")
        return

    out = os.path.abspath(os.path.expanduser(a.out))
    os.makedirs(out, exist_ok=True)
    sprite = os.path.join(out, "badminton_rally.aseprite")
    calls = build_plan(sprite, out)
    counts: dict[str, int] = {}
    for c in calls:
        counts[c.tool] = counts.get(c.tool, 0) + 1

    if a.cmd == "preview":
        pv = Preview()
        for c in calls:
            pv.call(c)
    else:
        mcp_dir = os.path.abspath(os.path.expanduser(a.mcp_dir))
        aseprite = os.path.abspath(os.path.expanduser(a.aseprite)) if a.aseprite else None
        asyncio.run(run_mcp(calls, mcp_dir, aseprite, a.uv, a.quiet))
    print(f"{len(calls)} tool calls: " + ", ".join(f"{k} x{v}" for k, v in counts.items()))
    print("Wrote:", *sorted(os.listdir(out)), sep="\n  ")


if __name__ == "__main__":
    main()
