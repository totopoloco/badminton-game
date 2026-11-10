extends RefCounted
## Shuttle flight (gravity + quadratic drag), the shot solver and the reach rules.
## A port of the reference model tools/sim.py.

const C := preload("res://scripts/config.gd")


static func step(st: Array) -> void:
	## One substep of [x, y, z, vx, vy, vz] in place (semi-implicit Euler).
	var vx: float = st[3]
	var vy: float = st[4]
	var vz: float = st[5]
	var sp := sqrt(vx * vx + vy * vy + vz * vz)
	vx += -C.K * sp * vx * C.DT
	vy += -C.K * sp * vy * C.DT
	vz += (-C.G - C.K * sp * vz) * C.DT
	st[0] = st[0] + vx * C.DT
	st[1] = st[1] + vy * C.DT
	st[2] = st[2] + vz * C.DT
	st[3] = vx
	st[4] = vy
	st[5] = vz


static func fly_sens(z0: float, vs0: float, vz0: float, ticks: int, s_net: float) -> Array:
	## Flight in the vertical plane of the shot (s = distance along the ground from
	## the launch point). Returns [s, z, ds/dvs, ds/dvz, dz/dvs, dz/dvz, height
	## where s passes s_net (-1e9 if never), apex].
	var s := 0.0
	var z: float = z0
	var vs: float = vs0
	var vz: float = vz0
	var jxa := 0.0
	var jza := 0.0
	var jxb := 0.0
	var jzb := 0.0
	var avx := 1.0
	var avz := 0.0
	var bvx := 0.0
	var bvz := 1.0
	var cross := -1.0e9
	var crossed := false
	var apex: float = z0
	var dt: float = C.DT
	var k: float = C.K
	for _i in ticks * C.SUB:
		var sp := sqrt(vs * vs + vz * vz)
		var dxx := 0.0
		var dxz := 0.0
		var dzz := 0.0
		if sp > 1.0e-9:
			dxx = -k * (sp + vs * vs / sp)
			dxz = -k * vs * vz / sp
			dzz = -k * (sp + vz * vz / sp)
		var navx := avx + (dxx * avx + dxz * avz) * dt
		var navz := avz + (dxz * avx + dzz * avz) * dt
		var nbvx := bvx + (dxx * bvx + dxz * bvz) * dt
		var nbvz := bvz + (dxz * bvx + dzz * bvz) * dt
		avx = navx
		avz = navz
		bvx = nbvx
		bvz = nbvz
		jxa += avx * dt
		jza += avz * dt
		jxb += bvx * dt
		jzb += bvz * dt
		var nvs := vs - k * sp * vs * dt
		var nvz := vz + (-C.G - k * sp * vz) * dt
		var ns := s + nvs * dt
		var nz := z + nvz * dt
		if not crossed and (s - s_net) * (ns - s_net) <= 0.0 and ns != s:
			cross = z + (nz - z) * (s_net - s) / (ns - s)
			crossed = true
		s = ns
		z = nz
		vs = nvs
		vz = nvz
		apex = maxf(apex, z)
	return [s, z, jxa, jxb, jza, jzb, cross, apex]


static func solve(z0: float, s1: float, z1: float, ticks: int, s_net: float) -> Array:
	## Launch speed along the ground (vs) and up (vz) that reaches distance s1 at
	## height z1 after exactly `ticks` ticks (damped Newton).
	## Returns [vs, vz, height at the net, apex, miss distance].
	var t: float = ticks * C.TICK
	var vs: float = s1 / t * 1.6
	var vz: float = (z1 - z0) / t + 0.5 * C.G * t
	var r := fly_sens(z0, vs, vz, ticks, s_net)
	var err: float = Vector2(r[0] - s1, r[1] - z1).length()
	for _it in 30:
		if err < 0.02:
			break
		var ex: float = r[0] - s1
		var ez: float = r[1] - z1
		var det: float = r[2] * r[5] - r[3] * r[4]
		if absf(det) < 1.0e-12:
			break
		var dvs: float = (r[5] * ex - r[3] * ez) / det
		var dvz: float = (-r[4] * ex + r[2] * ez) / det
		var stp := 1.0
		var improved := false
		while stp > 1.0 / 64.0:
			var q := fly_sens(z0, vs - stp * dvs, vz - stp * dvz, ticks, s_net)
			var e2: float = Vector2(q[0] - s1, q[1] - z1).length()
			if e2 < err:
				vs -= stp * dvs
				vz -= stp * dvz
				r = q
				err = e2
				improved = true
				break
			stp *= 0.5
		if not improved:
			break
	return [vs, vz, r[6], r[7], err]


static func predict(x: float, y: float, z: float, vx: float, vy: float, vz: float, max_ticks: int) -> Dictionary:
	## Shuttle position at the start of each coming tick until it reaches the floor
	## or the net. Returns {"pts": PackedVector3Array, "outcome": "land" | "net" | "open"}.
	var pts := PackedVector3Array([Vector3(x, y, z)])
	var st := [x, y, z, vx, vy, vz]
	for _i in max_ticks:
		for _j in C.SUB:
			var px: float = st[0]
			var pz: float = st[2]
			step(st)
			var nx: float = st[0]
			var nz: float = st[2]
			if (px - C.NET_X) * (nx - C.NET_X) <= 0.0 and nx != px:
				var cz := pz + (nz - pz) * (C.NET_X - px) / (nx - px)
				if cz <= C.NET_H:
					pts.append(Vector3(C.NET_X, st[1], cz))
					return {"pts": pts, "outcome": "net"}
			if nz <= 0.0:
				pts.append(Vector3(nx, st[1], 0.0))
				return {"pts": pts, "outcome": "land"}
		pts.append(Vector3(st[0], st[1], st[2]))
	return {"pts": pts, "outcome": "open"}


static func aim_side(rng: RandomNumberGenerator, aim: float, court: float) -> float:
	## Sideways target: rally shots anywhere inside the sidelines; a serve into the
	## service court on the `court` side of the centre line (+1 / -1).
	if court == 0.0:
		return clampf(aim * C.AIM_Y + rng.randf_range(-5.0, 5.0), -C.AIM_Y, C.AIM_Y)
	var inner := 5.0
	var a := clampf(0.5 + 0.5 * aim * court + rng.randf_range(-0.15, 0.15), 0.0, 1.0)
	return court * (inner + (C.AIM_Y - inner) * a)


static func _attempt(x0: float, y0: float, z0: float, f: float, u: float, yt: float, t: float) -> Array:
	## Solve one candidate shot. Returns [vx, vy, vz, height at the net, apex, miss].
	var dx := C.NET_X + f * u - x0
	var dy := yt - y0
	var dist := sqrt(dx * dx + dy * dy)
	var ux := dx / dist
	var uy := dy / dist
	var s_net := (C.NET_X - x0) / ux
	var r := solve(z0, dist, 0.0, maxi(4, roundi(t / C.TICK)), s_net)
	return [r[0] * ux, r[0] * uy, r[1], r[2], r[3], r[4]]


static func plan_shot(rng: RandomNumberGenerator, x0: float, y0: float, z0: float, f: float, shot: String,
		quality: float, err_scale: float, aim_x: float, aim_y: float, court: float = 0.0) -> Dictionary:
	## Launch velocity for `shot` from (x0, y0, z0) by a player facing f (+1 right).
	## aim_x -1..1 picks the depth (-1 deepest, +1 shortest), aim_y the side (-1 far
	## sideline, +1 near). `court` != 0 for a serve: the receiver's service court.
	## The intended flight clears the net by the shot's margin and keeps under its
	## speed limit and apex (adapting flight time and depth); then the hitter's
	## error is added, larger for a poor contact.
	## Returns {"vx", "vy", "vz", "shot", "solves"}.
	var gap := absf(C.NET_X - x0)
	if (shot == "net" or shot == "block") and gap > 45.0:
		shot = "drop"                                  # too far back for a net shot
	elif z0 < C.NET_H + 2.0 and shot in ["lift", "push", "drive", "clear"] and gap < 14.0:
		shot = "net" if gap < 8.0 else "lift"          # under the tape near the net
	var s: Dictionary = C.SHOTS[shot]
	var hard: bool = s["impact"] == 2
	var lo: float = s["u"][0]
	var hi: float = s["u"][1]
	var u := lo + (hi - lo) * (0.5 - 0.5 * aim_x) + rng.randf_range(-0.1, 0.1) * (hi - lo)
	var yt := aim_side(rng, aim_y, court)
	var t := rng.randf_range(s["t"][0], s["t"][1])
	if s["impact"] == 0:
		t = maxf(t, Vector2(C.NET_X + f * u - x0, yt - y0).length() / C.SOFT_MAX_SPEED)
	var best_pen := INF
	var best := [u, t, 0.0, 0.0, 0.0]
	var solves := 0
	for attempt in 14:
		var r := _attempt(x0, y0, z0, f, u, yt, t)
		solves += 1
		var low: float = C.NET_H + s["margin"] - r[3]
		var fast: float = Vector3(r[0], r[1], r[2]).length() - s["vmax"]
		var high: float = r[4] - s["apex"]
		var pen := maxf(0.0, low) * 4.0 + maxf(0.0, fast) / 40.0 + maxf(0.0, high)
		if r[5] > 1.0:
			pen += 1000.0
		if pen < best_pen:
			best_pen = pen
			best = [u, t, r[0], r[1], r[2]]
		if pen <= 0.0:
			break
		if r[5] > 1.0:
			t *= 0.9
		elif low > 0.0:
			t *= 1.12
			if hard and attempt % 3 == 2:
				u = minf(u + 4.0, 80.0)
		elif fast > 0.0:
			if hard:
				t *= 1.08
			else:
				u = maxf(u - 5.0, 2.0)
		else:
			t *= 0.94
	u = best[0]
	t = best[1]
	var v := Vector3(best[2], best[3], best[4])
	var sigma: float = err_scale * (1.0 + 5.0 * (1.0 - quality)) * s["err"]
	var u_err := maxf(0.5, u + rng.randfn(0.0, sigma))             # too short: into the net
	var y_err := yt + rng.randfn(0.0, sigma * 0.8)
	var t_err := t * (1.0 + rng.randfn(0.0, 0.03 * err_scale * (1.0 - quality)))
	var e := _attempt(x0, y0, z0, f, u_err, y_err, t_err)
	if e[5] <= 1.0:
		v = Vector3(e[0], e[1], e[2])
	return {"vx": v.x, "vy": v.y, "vz": v.z, "shot": shot, "solves": solves + 1}


static func reach_space(p: Vector3) -> Vector3:
	## Sideways distances count less: the arm reaches further across than along.
	return Vector3(p.x, p.y * C.REACH / C.REACH_Y, p.z)


static func closest(s0: Vector3, s1: Vector3, c0: Vector3, c1: Vector3) -> Vector2:
	## Closest approach of the shuttle (s0 -> s1) and the racket head (c0 -> c1)
	## during one tick, in reach space: (distance, tau).
	var a0 := reach_space(s0)
	var a1 := reach_space(s1)
	var b0 := reach_space(c0)
	var b1 := reach_space(c1)
	var r := a0 - b0
	var w := (a1 - a0) - (b1 - b0)
	var ww := w.dot(w)
	var tau := 0.0
	if ww > 1.0e-12:
		tau = clampf(-r.dot(w) / ww, 0.0, 1.0)
	return Vector2((r + w * tau).length(), tau)


static func reachable(f: float, stroke: String, rx: float, rz: float, sx: float, margin: float = 0.0) -> bool:
	## Can a player facing f meet a shuttle at x `sx` with the racket head at (rx, rz)?
	## The shuttle must be on the player's side, the racket must not reach over the
	## net or touch it from below the tape, and kills and net shots are played near
	## the net only. `margin` adds safety room (for planning).
	if f * (C.NET_X - sx) < 0.5:
		return false
	var gap := f * (C.NET_X - rx)
	var low := rz < C.NET_H + 2.0
	var near := (C.NET_GAP if low else 0.0) + margin
	var far: float = C.ZONE.get(stroke, 999.0) - margin
	return gap >= near and gap <= far


static func racket_gap_min(cz: float) -> float:
	## Smallest racket-to-net distance for a contact at height cz.
	return C.NET_GAP if cz < C.NET_H + 2.0 else 0.0


static func jump_apex() -> Vector2:
	## (ticks, height) of the jump apex with the players' per-tick integration.
	var z := 0.0
	var vz: float = C.JUMP_V
	var best := Vector2(0, 0)
	for n in range(1, 120):
		vz -= C.PLAYER_G * C.TICK
		z += vz * C.TICK
		if z > best.y + 1.0e-9:
			best = Vector2(n, z)
		if z <= 0.0:
			break
	return best
