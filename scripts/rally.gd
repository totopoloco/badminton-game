extends RefCounted
## The rules of one rally: serving, swinging, contacts, shots, and the call.

const C := preload("res://scripts/config.gd")
const Phys := preload("res://scripts/physics.gd")
const Shuttle := preload("res://scripts/shuttle.gd")

var rng: RandomNumberGenerator
var p: Array = []              # [red player, blue player]
var server := 0
var serve_court := 1.0         # side of the centre line the serve must land on
var s = Shuttle.new()
var last := -1                 # side that hit last
var is_serve := true
var tick := 0
var shots := 0
var hit := {}                  # the latest contact, for effects: side, x, y, z, shot, impact


func _init(p_rng: RandomNumberGenerator, red, blue, p_server: int, server_points: int) -> void:
	rng = p_rng
	p = [red, blue]
	server = p_server
	serve_court = -C.court_side(p[p_server].f, server_points)   # diagonally opposite


static func other(side: int) -> int:
	return 1 - side


func press(side: int, button: String, forced_stroke: String = "", shot: String = "",
		aim_x: float = 0.0, aim_y: float = 0.0, quality_scale: float = 1.0) -> bool:
	## A shot button: arm a swing; the contact happens when the shuttle comes.
	var pl = p[side]
	if not pl.stroke.is_empty() and pl.stroke["phase"] == "armed" and forced_stroke == "":
		pl.stroke["t"] = 0                         # pressed again while waiting: wait longer
		pl.stroke["button"] = button
		pl.stroke["aim_x"] = aim_x
		pl.stroke["aim_y"] = aim_y
		return true
	if pl.busy():
		return false
	var cands: Array = []
	if forced_stroke != "":
		cands = [forced_stroke]
	elif not pl.on_ground():
		cands = ["jump_smash"]
	else:
		cands = C.GROUND_STROKES.duplicate()
	pl.stroke = {"phase": "armed", "t": 0, "cands": cands, "button": button, "shot": shot,
			"aim_x": aim_x, "aim_y": aim_y, "qscale": quality_scale, "name": guess_stroke(pl, cands),
			"follow_len": 18, "whiff": false}
	return true


func guess_stroke(pl, cands: Array) -> String:
	## The stroke the swing will most likely use (only for the wind-up frames).
	if cands.size() == 1:
		return cands[0]
	if s.state != "flight":
		return "overhead"
	var pts: PackedVector3Array = Phys.predict(s.x, s.y, s.z, s.vx, s.vy, s.vz, C.ARM_TICKS)["pts"]
	var best := INF
	var sname := "overhead"
	for st in cands:
		for k in pts.size():
			var t := k * C.TICK
			var c: Vector3 = pl.contact_point(st, pl.x + pl.vx * t, pl.y + pl.vy * t, 0.0)
			var d := Phys.reach_space(pts[k]).distance_to(Phys.reach_space(c))
			if d < best:
				best = d
				sname = st
	return sname


func serve(kind: String, aim_x: float = 0.0, aim_y: float = 0.0) -> void:
	var pl = p[server]
	pl.serve_pose = ""
	pl.stroke = {"phase": "serve", "t": 0, "name": "serve" if kind == "serve_high" else "serve_short",
			"shot": kind, "follow_len": 20, "aim_x": aim_x, "aim_y": aim_y, "qscale": 1.0, "whiff": false}
	s.state = "held"


func contacts() -> int:
	## Hits due this tick. Returns the hitter's side, or -1.
	for side in 2:
		var pl = p[side]
		if pl.stroke.is_empty():
			continue
		var st: Dictionary = pl.stroke
		if st["phase"] == "serve":
			if st["t"] == C.SERVE_CONTACT and s.state == "held":
				var c0: Vector3 = pl.contact_point(st["name"], pl.x, pl.y, pl.z)
				_launch(side, pl, c0, st["shot"], 1.0, true, st)
				st["phase"] = "follow"
				st["t"] = 0
				return side
			continue
		if st["phase"] != "armed" or s.state != "flight" or last == side:
			continue
		var s0: Vector3 = s.pos()
		var s1: Vector3 = s.next_tick()
		var n: Vector3 = pl.next_pos()
		var best_d := INF
		var best_name := ""
		var best_c := Vector3.ZERO
		for sname in st["cands"]:
			var c0: Vector3 = pl.contact_point(sname, pl.x, pl.y, pl.z)
			var c1: Vector3 = pl.contact_point(sname, n.x, n.y, n.z)
			var ct := Phys.closest(s0, s1, c0, c1)
			var sx := s0.x + ct.y * (s1.x - s0.x)
			if not Phys.reachable(pl.f, sname, c0.x, c0.z, sx):
				continue
			if ct.x <= C.REACH and (ct.y < 1.0 or st["t"] >= C.ARM_TICKS) and ct.x < best_d:
				best_d = ct.x
				best_name = sname
				best_c = c0
		if best_name == "":
			continue
		var shot: String = st["shot"]
		if shot == "":
			shot = C.SHOT_MAP[st["button"]][best_name]
		st["name"] = best_name
		_launch(side, pl, best_c, shot, (1.0 - best_d / C.REACH) * st["qscale"], false, st)
		st["phase"] = "follow"
		st["t"] = 0
		if best_name != "jump_smash":
			pl.vx = 0.0
			pl.vy = 0.0
		return side
	return -1


func _launch(side: int, pl, c0: Vector3, shot: String, quality: float, serving: bool, st: Dictionary) -> void:
	var t0 := Time.get_ticks_usec()
	var r := Phys.plan_shot(rng, c0.x, c0.y, c0.z, pl.f, shot, quality, pl.err_scale,
			st["aim_x"], st["aim_y"], serve_court if serving else 0.0)
	var usec := Time.get_ticks_usec() - t0
	s.launch(c0, Vector3(r["vx"], r["vy"], r["vz"]))
	last = side
	is_serve = serving
	shots += 1
	hit = {"side": side, "x": c0.x, "y": c0.y, "z": c0.z, "shot": r["shot"], "quality": quality,
			"impact": C.SHOTS[r["shot"]]["impact"], "solves": r["solves"], "usec": usec}


func decide() -> Array:
	## [winner side, call] once the shuttle is down.
	var opp := other(last)
	var u: float = p[last].f * (s.x - C.NET_X)          # > 0: on the other side
	if s.via_net or u <= 0.0:
		return [opp, "NET"]
	if u > C.HALF or absf(s.y) > C.SIDE:
		return [opp, "OUT"]
	if is_serve:
		if u < C.SHORT:
			return [opp, "SHORT"]
		if s.y * serve_court < 0.0:
			return [opp, "FAULT"]                      # wrong service court
	return [last, "IN"]
