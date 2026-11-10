extends RefCounted
## The shuttle: held, in flight, falling from the net, or on the floor.

const C := preload("res://scripts/config.gd")
const Phys := preload("res://scripts/physics.gd")

var x := 0.0
var y := 0.0
var z := 0.0
var vx := 0.0
var vy := 0.0
var vz := 0.0
var state := "held"        # held, flight, net, landed
var via_net := false
var spin := 0.0            # tumbling angle after hitting the net


func step() -> String:
	## One tick. Returns "net" when it hits the net, "land" when it lands, else "".
	if state == "flight":
		for _j in C.SUB:
			var st := [x, y, z, vx, vy, vz]
			Phys.step(st)
			var nx: float = st[0]
			var nz: float = st[2]
			if (x - C.NET_X) * (nx - C.NET_X) <= 0.0 and nx != x:
				var cz := z + (nz - z) * (C.NET_X - x) / (nx - x)
				if cz <= C.NET_H:
					var side := -1.0 if x < C.NET_X else 1.0
					x = C.NET_X + side * 1.0
					y = st[1]
					z = cz
					vx = 0.0
					vy = 0.0
					vz = minf(st[5], 0.0) * 0.3
					state = "net"
					via_net = true
					return "net"
			x = nx
			y = st[1]
			z = nz
			vx = st[3]
			vy = st[4]
			vz = st[5]
			if z <= 0.0:
				z = 0.0
				state = "landed"
				return "land"
	elif state == "net":
		spin += 0.35
		for _j in C.SUB:
			var st := [x, y, z, 0.0, 0.0, vz]
			Phys.step(st)
			z = st[2]
			vz = st[5]
			if z <= 0.0:
				z = 0.0
				state = "landed"
				return "land"
	return ""


func pos() -> Vector3:
	return Vector3(x, y, z)


func vel() -> Vector3:
	return Vector3(vx, vy, vz)


func next_tick() -> Vector3:
	## Position one tick ahead (no net or floor handling).
	var st := [x, y, z, vx, vy, vz]
	for _j in C.SUB:
		Phys.step(st)
	return Vector3(st[0], st[1], st[2])


func launch(p: Vector3, v: Vector3) -> void:
	x = p.x
	y = p.y
	z = p.z
	vx = v.x
	vy = v.y
	vz = v.z
	state = "flight"
	via_net = false
	spin = 0.0
