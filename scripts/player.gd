extends RefCounted
## One player: movement, jumping, the current swing and which animation frame to show.

const C := preload("res://scripts/config.gd")

var side := 0                  # C.RED or C.BLUE
var f := 1.0                   # facing: +1 right (red), -1 left (blue)
var who := "red_man"           # character sheet
var contact := {}              # stroke -> Vector2(dx, z) of the racket head, facing right
var hold := {}                 # serve anim -> Array of Vector2(dx, z) of the free hand
var lifts := {}                # anim -> Array of pose lift per frame (for shadows)
var contact_frame := {}        # anim -> index of its contact frame

var x := 0.0
var y := 0.0                   # across the court (+ towards the camera)
var z := 0.0
var vx := 0.0
var vy := 0.0
var vz := 0.0
var move_x := 0.0              # input -1..1: screen right
var move_y := 0.0              # input -1..1: down the screen (towards the camera)
var speed: float = C.SPEED
var err_scale := 1.0
var stroke := {}               # empty, or the swing in progress (see rally.gd)

# presentation
var mood := ""                 # "", "celebrate", "dejected"
var serve_pose := ""           # "serve" / "serve_short" while holding the shuttle to serve
var receiving := false
var land_ticks := 0
var anim := "idle"
var anim_frame := -1           # explicit frame within the tag, or -1 to play by time
var anim_time := 0.0           # ms since the animation started


func setup(p_side: int, p_who: String, rig: Dictionary) -> void:
	side = p_side
	f = 1.0 if p_side == C.RED else -1.0
	who = p_who
	var ch: Dictionary = rig["characters"][p_who]
	contact.clear()
	for k in ch["contact"]:
		contact[k] = Vector2(ch["contact"][k][0], ch["contact"][k][1])
	hold.clear()
	for k in ch["hold"]:
		var pts: Array = []
		for p in ch["hold"][k]:
			pts.append(Vector2(p[0], p[1]))
		hold[k] = pts
	for k in rig["anims"]:
		lifts[k] = rig["anims"][k]["lift"]
		contact_frame[k] = int(rig["anims"][k]["contact"])


func reset(p: Vector2) -> void:
	x = p.x
	y = p.y
	z = 0.0
	vx = 0.0
	vy = 0.0
	vz = 0.0
	move_x = 0.0
	move_y = 0.0
	stroke = {}
	mood = ""
	serve_pose = ""
	receiving = false
	land_ticks = 0


func on_ground() -> bool:
	return z <= 0.0 and vz <= 0.0


func x_limits() -> Vector2:
	var a: float = C.NET_X - f * C.X_FAR
	var b: float = C.NET_X - f * C.X_NEAR
	return Vector2(minf(a, b), maxf(a, b))


func locked() -> bool:
	## No running while serving or during the follow-through of a ground stroke.
	if stroke.is_empty():
		return false
	if stroke["phase"] == "serve":
		return true
	return stroke["phase"] == "follow" and stroke["t"] < C.LOCK_TICKS and stroke["name"] != "jump_smash"


func busy() -> bool:
	return not stroke.is_empty()


func jump() -> bool:
	## Straight up: the run stops at take-off (no drifting through the air).
	if on_ground() and stroke.is_empty():
		vz = C.JUMP_V
		vx = 0.0
		vy = 0.0
		return true
	return false


func contact_point(stroke_name: String, px: float, py: float, pz: float) -> Vector3:
	var c: Vector2 = contact[stroke_name]
	return Vector3(px + f * c.x, py, pz + c.y)


func next_pos() -> Vector3:
	## Feet one tick ahead if nothing changes (for the swept contact test).
	if on_ground():
		return Vector3(x + vx * C.TICK, y + vy * C.TICK, 0.0)
	var nvz := vz - C.PLAYER_G * C.TICK
	return Vector3(x + vx * C.TICK, y + vy * C.TICK, maxf(0.0, z + nvz * C.TICK))


static func _axis(v: float, target: float) -> float:
	var a: float = (C.ACCEL if absf(target) > absf(v) and target * v >= 0.0 else C.DECEL) * C.TICK
	return v + clampf(target - v, -a, a)


func update() -> void:
	var tx := 0.0
	var ty := 0.0
	if locked():
		pass
	elif not on_ground():
		tx = vx                                        # no air control
		ty = vy
	else:
		var m := Vector2(move_x, move_y)
		if m.length() > 1.0:
			m = m.normalized()
		tx = m.x * speed
		ty = m.y * speed
	vx = _axis(vx, tx)
	vy = _axis(vy, ty)
	var lim := x_limits()
	x += vx * C.TICK
	if x < lim.x or x > lim.y:
		x = clampf(x, lim.x, lim.y)
		vx = 0.0
	y += vy * C.TICK
	if absf(y) > C.Y_LIM:
		y = clampf(y, -C.Y_LIM, C.Y_LIM)
		vy = 0.0
	if z > 0.0 or vz > 0.0:
		vz -= C.PLAYER_G * C.TICK
		z += vz * C.TICK
		if z <= 0.0:
			z = 0.0
			vz = 0.0
			land_ticks = 7
	elif land_ticks > 0:
		land_ticks -= 1
	if not stroke.is_empty():
		stroke["t"] += 1
		if stroke["phase"] == "armed" and stroke["t"] > C.ARM_TICKS:
			stroke["phase"] = "follow"                  # nothing came: a whiff
			stroke["t"] = 0
			stroke["whiff"] = true
			stroke["follow_len"] = 10                   # short recovery after a miss
		elif (stroke["phase"] == "follow" or stroke["phase"] == "serve") and stroke["t"] >= stroke["follow_len"]:
			stroke = {}
	_pick_anim()


func _set_anim(anim_name: String, frame: int = -1) -> void:
	if anim_name != anim:
		anim = anim_name
		anim_time = 0.0
	else:
		anim_time += C.TICK * 1000.0
	anim_frame = frame


func _pick_anim() -> void:
	if mood != "":
		_set_anim(mood)
	elif not stroke.is_empty():
		var sname: String = stroke["name"]
		var t: int = stroke["t"]
		var cf: int = contact_frame.get(sname, 1)
		match stroke["phase"]:
			"serve":
				_set_anim(sname, 1 if t < C.SERVE_CONTACT else 2)
			"armed":
				_set_anim(sname, mini(cf - 1, floori(t / 4.0)) if cf > 0 else 0)
			_:
				if sname == "jump_smash" and on_ground():
					_set_anim("smash_land", 0)
				elif t < 5:
					_set_anim(sname, cf)
				else:
					var n: int = lifts.get(sname, [0]).size()
					_set_anim(sname, mini(n - 1, cf + 1 + floori((t - 5) / 6.0)))
	elif serve_pose != "":
		_set_anim(serve_pose, 0)
	elif not on_ground():
		_set_anim("jump", 1 if vz > 0.0 else 2)
	elif land_ticks > 0:
		_set_anim("land", 0)
	elif Vector2(vx, vy).length() > 12.0:
		var back := vx * f < 0.0 and absf(vx) >= 0.5 * absf(vy)
		_set_anim("back" if back else "run")
	elif receiving:
		_set_anim("receive")
	else:
		_set_anim("idle")


func pose_lift() -> float:
	## The drawn pose's own jump lift (sprite already raised by this much).
	var arr: Array = lifts.get(anim, [0])
	var i := anim_frame if anim_frame >= 0 else 0
	return float(arr[clampi(i, 0, arr.size() - 1)])


func held_shuttle() -> Vector3:
	## Where the shuttle hangs from the free hand while serving.
	var key := serve_pose
	var frame := 0
	if not stroke.is_empty() and stroke["phase"] == "serve":
		key = stroke["name"]
		frame = 1
	if key == "" or not hold.has(key):
		return Vector3(x + f * 8.0, y, 14.0)
	var p: Vector2 = hold[key][frame]
	var drop := 4.0 if frame == 1 else 0.0
	return Vector3(x + f * p.x, y, z + p.y - 2.5 - drop)
