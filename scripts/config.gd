extends RefCounted
## Game constants: court, physics, players, shots and CPU levels.
## The numbers were tuned with the reference model sim/sim.py (same names).
## Units: px (court art pixels), seconds. x runs along the court (net at 96),
## y across it (0 = centre line, + towards the camera), z is height.

const TICK := 1.0 / 60.0          # one simulation tick
const SUB := 2                    # shuttle substeps per tick
const DT := TICK / SUB
const G := 250.0                  # gravity, px/s^2
const K := 0.016                  # quadratic air drag, 1/px
const NET_X := 96.0               # net position along the court
const NET_H := 28.0               # tape height
const HALF := 84.0                # net to baseline
const SHORT := 24.8               # short service line, from the net
const REACH := 9.0                # racket head to shuttle distance that still hits
const ARM_TICKS := 21             # a swing waits this long for the shuttle (0.35 s)
const LOCK_TICKS := 8             # no running during the follow-through
const SERVE_CONTACT := 7          # ticks from pressing serve to the contact
const NET_GAP := 2.5              # below the tape the racket stays this far from the net
const SOFT_MAX_SPEED := 120.0     # soft shots fly no faster than this on average
const SIDE := 32.4                # singles sideline, from the centre line (y)
const REACH_Y := 14.0             # sideways reach (the arm reaches further across)
const AIM_Y := 26.0               # widest aim, from the centre line
const SIDE_REACH := 5.6           # the CPU reaches this far across instead of running

const SPEED := 92.0               # running speed, px/s
const ACCEL := 1000.0
const DECEL := 1600.0
const JUMP_V := 150.0
const PLAYER_G := 600.0
const X_NEAR := 10.0              # feet limits, measured from the net
const X_FAR := 86.0
const Y_LIM := 42.0               # feet limit across the court
const SERVER_U := 44.0            # serving and receiving spots, from the net
const RECEIVER_U := 50.0
const SERVE_Y := 15.0             # ... and from the centre line
const HOME_U := 42.0              # where the CPU waits

# Drawing: the oblique court of the animations (badminton_rally.py). Court y maps
# to a floor row: the centre line is row 85, the singles sidelines rows 76 and 94.
const GROUND := 88.0
const SKEW := 0.5
const ROW_C := 85.0
const ROW_K := 9.0 / 32.4
const W := 192
const H := 108

const RED := 0
const BLUE := 1

const GROUND_STROKES := ["overhead", "kill", "drive", "block", "net", "lift"]
const ZONE := {"kill": 22.0, "net": 45.0}   # stroke -> farthest contact from the net

# shot -> target depth u (from the net, other side), flight time (s), net margin,
#         max launch speed, highest point, error weight, impact (0 soft, 1 normal, 2 hard)
const SHOTS := {
	"clear":       {"u": [66.0, 78.0], "t": [1.10, 1.30], "margin": 6.0, "vmax": 950.0, "apex": 96.0, "err": 1.0, "impact": 1},
	"lift":        {"u": [60.0, 76.0], "t": [1.15, 1.40], "margin": 6.0, "vmax": 950.0, "apex": 115.0, "err": 0.8, "impact": 1},
	"drop":        {"u": [12.0, 26.0], "t": [0.90, 1.05], "margin": 2.5, "vmax": 400.0, "apex": 84.0, "err": 0.8, "impact": 0},
	"net":         {"u": [7.0, 15.0], "t": [0.70, 0.90], "margin": 1.5, "vmax": 300.0, "apex": 84.0, "err": 0.6, "impact": 0},
	"block":       {"u": [8.0, 18.0], "t": [0.75, 0.95], "margin": 2.0, "vmax": 300.0, "apex": 84.0, "err": 0.7, "impact": 0},
	"push":        {"u": [50.0, 66.0], "t": [0.90, 1.10], "margin": 3.0, "vmax": 650.0, "apex": 90.0, "err": 1.0, "impact": 1},
	"drive":       {"u": [55.0, 75.0], "t": [0.78, 0.90], "margin": 2.0, "vmax": 700.0, "apex": 84.0, "err": 1.1, "impact": 1},
	"smash":       {"u": [35.0, 60.0], "t": [0.50, 0.62], "margin": 3.0, "vmax": 850.0, "apex": 84.0, "err": 1.2, "impact": 2},
	"jsmash":      {"u": [30.0, 55.0], "t": [0.42, 0.52], "margin": 3.0, "vmax": 1050.0, "apex": 90.0, "err": 1.3, "impact": 2},
	"kill":        {"u": [22.0, 40.0], "t": [0.28, 0.36], "margin": 2.0, "vmax": 650.0, "apex": 84.0, "err": 1.2, "impact": 2},
	"serve_high":  {"u": [72.0, 80.0], "t": [1.25, 1.45], "margin": 5.0, "vmax": 900.0, "apex": 90.0, "err": 0.8, "impact": 1},
	"serve_short": {"u": [27.0, 33.0], "t": [0.75, 0.90], "margin": 2.0, "vmax": 300.0, "apex": 84.0, "err": 0.5, "impact": 0},
}

# button -> stroke -> shot, for the three shot buttons
const SHOT_MAP := {
	"clear": {"overhead": "clear", "jump_smash": "clear", "kill": "push", "drive": "clear",
			"block": "lift", "net": "lift", "lift": "lift"},
	"drop": {"overhead": "drop", "jump_smash": "drop", "kill": "net", "drive": "block",
			"block": "block", "net": "net", "lift": "net"},
	"smash": {"overhead": "smash", "jump_smash": "jsmash", "kill": "kill", "drive": "drive",
			"block": "drive", "net": "push", "lift": "push"},
}

# CPU levels: speed factor, reaction (s), positioning error (px), shot error scale,
# chance to leave a shuttle that is going out, chance to jump-smash, tactical sense,
# ticks between pressing and contact, unforced-error and misjudgement chances.
const LEVELS := [
	{"name": "EASY", "speed": 0.80, "react": 0.30, "pos_err": 4.0, "err": 1.6, "judge": 0.55,
		"jump": 0.0, "smart": 0.3, "lead": 8, "mistake": 0.12, "misjudge": 0.06},
	{"name": "NORMAL", "speed": 0.92, "react": 0.20, "pos_err": 2.5, "err": 1.0, "judge": 0.80,
		"jump": 0.35, "smart": 0.6, "lead": 6, "mistake": 0.05, "misjudge": 0.02},
	{"name": "HARD", "speed": 1.00, "react": 0.13, "pos_err": 1.5, "err": 0.6, "judge": 0.95,
		"jump": 0.7, "smart": 0.85, "lead": 5, "mistake": 0.02, "misjudge": 0.005},
]
const PREF := {"kill": 3.0, "jump_smash": 2.6, "overhead": 2.0, "drive": 1.4, "net": 1.2,
		"block": 1.0, "lift": 0.8}
const SHOT_WEIGHTS := {
	"overhead": {"clear": 1.0, "drop": 1.0, "smash": 1.2},
	"jump_smash": {"jsmash": 3.0, "drop": 1.0},
	"kill": {"kill": 1.0},
	"drive": {"drive": 2.0, "block": 1.0, "clear": 0.5},
	"block": {"block": 1.5, "lift": 1.5, "drive": 0.5},
	"net": {"net": 2.0, "lift": 1.5, "push": 0.3},
	"lift": {"lift": 2.0, "net": 1.0},
}


static func row(y: float) -> float:
	## Floor row of a point y across the court (+y towards the camera).
	return ROW_C + y * ROW_K


static func screen(x: float, y: float, z: float) -> Vector2:
	## Court point (along, across, height) -> canvas pixel.
	var d := row(y)
	return Vector2(x + (GROUND - d) * SKEW, d - z)


static func screen_dir(v: Vector3) -> Vector2:
	## A velocity on the court as a direction on screen.
	return Vector2(v.x - v.y * ROW_K * SKEW, v.y * ROW_K - v.z)


static func court_side(f: float, points: int) -> float:
	## Side of the centre line a player serves or receives from: the right court
	## on an even score. Right = +y for red (facing +x), -y for blue.
	return f if points % 2 == 0 else -f
