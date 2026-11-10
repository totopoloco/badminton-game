extends RefCounted
## The computer player: reads the shuttle when the other side hits, picks where
## and how to meet it, runs there, swings, and goes back to the middle.

const C := preload("res://scripts/config.gd")
const Phys := preload("res://scripts/physics.gd")

var rng: RandomNumberGenerator
var side := 1
var lv: Dictionary
var plan := {}
var apex := Vector2.ZERO        # jump apex (ticks, height)


func _init(p_rng: RandomNumberGenerator, p_side: int, level: int) -> void:
	rng = p_rng
	side = p_side
	lv = C.LEVELS[clampi(level, 0, C.LEVELS.size() - 1)]
	apex = Phys.jump_apex()


func think(r, pl, opp) -> void:
	## Plan the return as soon as the other player has hit.
	plan = {}
	var s = r.s
	var pr := Phys.predict(s.x, s.y, s.z, s.vx, s.vy, s.vz, 400)
	var pts: PackedVector3Array = pr["pts"]
	if pr["outcome"] == "net":
		return
	var land: Vector3 = pts[pts.size() - 1]
	var u_land: float = -pl.f * (land.x - C.NET_X)                # > 0 on our side
	var out: bool = u_land > C.HALF + 1.0 or absf(land.y) > C.SIDE + 1.0 \
			or (r.is_serve and land.y * r.serve_court < -1.0)
	if pr["outcome"] == "land" and out and rng.randf() < lv["judge"]:
		return                                       # let it go out
	if rng.randf() < lv["misjudge"]:
		return                                       # thinks it is going out
	var react := roundi(lv["react"] / C.TICK)
	var spd: float = C.SPEED * lv["speed"]
	var strokes: Array = C.GROUND_STROKES.duplicate()
	if rng.randf() < lv["jump"]:
		strokes.insert(0, "jump_smash")
	var lim: Vector2 = pl.x_limits()
	var best_score := -INF
	var best_stroke := ""
	var best_k := 0
	var best_at := Vector2.ZERO
	for st in strokes:
		var c: Vector2 = pl.contact[st]
		var cz := c.y
		var jump: bool = st == "jump_smash"
		if jump:
			cz += apex.y
		for k in range(react + 2, pts.size()):
			var p3 := pts[k]
			if absf(p3.z - cz) > 3.0 or not Phys.reachable(pl.f, st, p3.x, cz, p3.x, 1.0):
				continue
			var x_need: float = p3.x - pl.f * c.x
			var y_need: float = p3.y - clampf(p3.y - pl.y, -C.SIDE_REACH, C.SIDE_REACH)   # reach across
			if x_need < lim.x or x_need > lim.y or absf(y_need) > C.Y_LIM:
				continue
			var ready := k - (int(apex.x) + 6 if jump else 0)        # must be in place by then
			var dist := Vector2(x_need - pl.x, y_need - pl.y).length()
			if dist / spd + 0.05 > (ready - react) * C.TICK:
				continue
			var score: float = C.PREF[st] - 0.15 * k * C.TICK
			if score > best_score:
				best_score = score
				best_stroke = st
				best_k = k
				best_at = Vector2(x_need, y_need)
			break
	if best_stroke == "":
		return
	var x := best_at.x + rng.randfn(0.0, lv["pos_err"])
	var y := best_at.y + rng.randfn(0.0, lv["pos_err"])
	var cc: Vector2 = pl.contact[best_stroke]
	var gap: float = pl.f * (C.NET_X - (x + pl.f * cc.x))       # keep the racket off the net
	var need: float = Phys.racket_gap_min(cc.y) + 0.5
	if gap < need:
		x -= pl.f * (need - gap)
	var choice := choose_shot(best_stroke, opp, pl.f * (C.NET_X - best_at.x) - cc.x, cc.y)
	plan = {"stroke": best_stroke, "contact": r.tick + best_k, "x": x, "y": y, "start": r.tick + react,
			"shot": choice[0], "aim_y": choice[1], "pressed": false, "jumped": false}


func choose_shot(st: String, opp, gap: float, cz: float) -> Array:
	## [shot, sideways aim] for a planned stroke; gap = contact distance from the net.
	var opp_u := absf(opp.x - C.NET_X)
	var w := {}
	if cz < C.NET_H + 2.0 and gap < 20.0:
		w = {"net": 1.0, "lift": 1.0}                # under the tape at the net
	else:
		w = C.SHOT_WEIGHTS[st].duplicate()
	var aim := rng.randf_range(-1.0, 1.0)
	if rng.randf() < lv["smart"]:
		for shot in w:
			var deep: bool = C.SHOTS[shot]["u"][0] >= 45.0
			if (opp_u < 35.0 and deep) or (opp_u > 58.0 and not deep):
				w[shot] *= 2.5
		if absf(opp.y) > 4.0:                        # away from the opponent
			aim = -signf(opp.y) * rng.randf_range(0.5, 1.0)
	var total := 0.0
	for shot in w:
		total += w[shot]
	var pick := rng.randf() * total
	var last := ""
	for shot in w:
		last = shot
		pick -= w[shot]
		if pick <= 0.0:
			return [shot, aim]
	return [last, aim]


func update(r, pl) -> void:
	## Every tick of a rally: move, jump, swing.
	var target := Vector2(C.NET_X - pl.f * C.HOME_U, 0.0)       # home: mid court
	if not plan.is_empty():
		if r.tick < plan["start"]:
			target = Vector2(pl.x, pl.y)                       # still reacting
		else:
			target = Vector2(plan["x"], plan["y"])
			var jump: bool = plan["stroke"] == "jump_smash"
			if jump and not plan["jumped"] and r.tick >= plan["contact"] - int(apex.x):
				pl.jump()
				plan["jumped"] = true
			var lead: int = 3 if jump else lv["lead"]
			if not plan["pressed"] and r.tick >= plan["contact"] - lead:
				var q := 0.2 if rng.randf() < lv["mistake"] else 1.0
				plan["pressed"] = r.press(side, "", plan["stroke"], plan["shot"],
						rng.randf_range(-1.0, 1.0), plan["aim_y"], q)
			if plan["pressed"] and (pl.stroke.is_empty() or pl.stroke["phase"] != "armed"):
				plan = {}                                      # swung (hit or missed)
	var d := target - Vector2(pl.x, pl.y)
	var dist := d.length()
	if dist > 0.3:
		var m := d * (minf(1.0, dist / 6.0) / dist)
		pl.move_x = m.x
		pl.move_y = m.y
	else:
		pl.move_x = 0.0
		pl.move_y = 0.0
	pl.speed = C.SPEED * lv["speed"]
