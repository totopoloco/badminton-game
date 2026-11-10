extends Node2D
## Badminton singles against the computer: title menu, serving, rallies, the
## call, 3 x 15 scoring, and the drawing of court, players, shuttle and HUD.
##
## Command line (after `--`): --autoplay [--points=N] [--level=0..2] [--seed=N]
## [--women] [--speed=TICKS_PER_FRAME] [--shots=DIR] plays CPU against CPU,
## prints a report and quits (exit code 1 if something looked wrong).
## --licenses[=FILE] prints (or writes) Godot's license and third-party notices
## and quits; tools/export.sh ships that file with every build.

const C := preload("res://scripts/config.gd")
const Phys := preload("res://scripts/physics.gd")
const PlayerT := preload("res://scripts/player.gd")
const Rally := preload("res://scripts/rally.gd")
const CPU := preload("res://scripts/cpu.gd")
const Score := preload("res://scripts/score.gd")
const Sheet := preload("res://scripts/sheet.gd")
const PixelFont := preload("res://scripts/pixel_font.gd")
const Sfx := preload("res://scripts/sfx.gd")

enum St { TITLE, SERVE, RALLY, POINT, WALK, GAME_END, MATCH_END }

const COL_RED := Color("#ff6464")
const COL_RED_DIM := Color("#7a3434")
const COL_BLUE := Color("#62a8ff")
const COL_BLUE_DIM := Color("#2c4a70")
const COL_COLON := Color("#cfd6e2")
const COL_TEXT := Color("#eef0e6")
const COL_INK := Color("#0d111d")
const COL_GOLD := Color("#fff2a0")
const COL_SHADOW := Color("#0a0e1a66")
const COL_TRAIL := Color("#ffffff60")
const COL_FLASH_SOFT := Color("#fff6c890")
const COL_DUST := Color("#e3d6c2a0")
const COL_PANEL := Color("#0d111de0")
const COL_MARK := Color("#fff2a0a0")
const CALLS := {"IN": "IN!", "OUT": "OUT", "NET": "NET", "SHORT": "SHORT SERVE", "FAULT": "SERVICE FAULT"}
const LEVEL_NAMES := ["EASY", "NORMAL", "HARD"]

var rig: Dictionary = {}
var sheets := {}
var shuttle_sheet
var cell := Vector2(53, 61)
var anchor := Vector2(26, 55)

var sprites: Array = []
var crowd_sheet = null              # the stands (optional: the game runs without them)
var crowd_sprite: Sprite2D
var crowd_cheer := 0                # ticks the crowd keeps cheering
var crowd_ms := 0.0                 # time into the crowd's current animation
var layer_shadow: Node2D
var layer_shuttle: Node2D
var layer_hud: Node2D
var sfx

var rng := RandomNumberGenerator.new()
var players: Array = []
var cpus: Array = [null, null]
var human := 0
var level := 1
var women := false
var menu_row := 0

var score = Score.new()
var rally = null
var state := St.TITLE
var state_t := 0
var server := 0
var serve_kind := "serve_high"
var serve_delay := 50
var call_text := ""
var winner := -1
var outcome := "point"
var hitstop := 0
var flash := {}
var dust := {}
var trail: Array = []
var land_mark := Vector2.ZERO      # where the CPU's shot will land (x, y)
var mark_on := false
var land_hop := 0
var land_dir := 1.0
var paused := false
var show_keys := true               # the controls bar under the court (H toggles it)
var toast := ""                     # a short note at the top, e.g. "CROWD SOUND OFF"
var toast_t := 0
var ok := true

# autoplay / test mode
var auto := false
var seeded := false
var auto_points := 40
var auto_speed := 1
var shots_dir := ""
var shot_count := 0
var pending_shots: Array = []
var stats := {"points": 0, "shots": 0, "calls": {}, "strokes": {}, "longest": 0,
		"max_solves": 0, "max_ticks": 0, "usec": 0, "max_usec": 0}
var licenses_to := ""                  # --licenses: "-" prints, otherwise a file path


# ------------------------------------------------------------------ setup
func _ready() -> void:
	_parse_args()
	if licenses_to != "":
		ok = false                     # nothing else runs; quits at the end of this frame
		_write_licenses()
		return
	if OS.has_feature("template"):
		print(_license_notice(false))  # exported builds: the notice Godot's MIT license asks for
	if not seeded:
		rng.randomize()
	_setup_input()
	sfx = Sfx.new()
	add_child(sfx)
	if not _load_assets():
		push_error("Assets are missing: run badminton_game_assets.py first.")
		ok = false
		if auto:
			get_tree().quit(1)
		return
	_build_scene()
	_make_players()
	_to_title()
	if auto:
		human = -1
		sfx.muted = true


func _parse_args() -> void:
	for a in OS.get_cmdline_user_args():
		var kv: PackedStringArray = a.split("=", true, 1)
		var key: String = kv[0]
		var val: String = kv[1] if kv.size() > 1 else ""
		match key:
			"--autoplay":
				auto = true
			"--points":
				auto_points = maxi(1, val.to_int())
			"--level":
				level = clampi(val.to_int(), 0, 2)
			"--seed":
				rng.seed = val.to_int()
				seeded = true
			"--women":
				women = true
			"--speed":
				auto_speed = clampi(val.to_int(), 1, 64)
			"--shots":
				shots_dir = val
			"--licenses":
				licenses_to = val if val != "" else "-"


func _setup_input() -> void:
	_bind("left", [KEY_LEFT], [JOY_BUTTON_DPAD_LEFT], [[JOY_AXIS_LEFT_X, -1.0]])
	_bind("right", [KEY_RIGHT], [JOY_BUTTON_DPAD_RIGHT], [[JOY_AXIS_LEFT_X, 1.0]])
	_bind("up", [KEY_UP], [JOY_BUTTON_DPAD_UP], [[JOY_AXIS_LEFT_Y, -1.0]])
	_bind("down", [KEY_DOWN], [JOY_BUTTON_DPAD_DOWN], [[JOY_AXIS_LEFT_Y, 1.0]])
	# 1 jumps, 2-4 hit: the number keys above the letters, matched by position,
	# so they work with any keyboard layout. Space and Z/X/C do the same.
	_bind("jump", [KEY_1, KEY_SPACE], [JOY_BUTTON_Y, JOY_BUTTON_RIGHT_SHOULDER], [])
	_bind("clear", [KEY_2, KEY_Z], [JOY_BUTTON_A], [])
	_bind("drop", [KEY_3, KEY_X], [JOY_BUTTON_X], [])
	_bind("smash", [KEY_4, KEY_C], [JOY_BUTTON_B], [])
	_bind("start", [KEY_ENTER, KEY_KP_ENTER], [JOY_BUTTON_START], [])
	_bind("pause", [KEY_ESCAPE, KEY_P], [JOY_BUTTON_START], [])
	_bind("back", [KEY_Q, KEY_BACKSPACE], [JOY_BUTTON_BACK], [])
	_bind("fullscreen", [KEY_F11], [], [])
	_bind("mute", [KEY_M], [], [])
	_bind("crowd", [KEY_N], [], [])
	_bind("keys", [KEY_H], [], [])


func _bind(action: String, keys: Array, buttons: Array, axes: Array) -> void:
	if InputMap.has_action(action):
		return                                   # keep remaps made in Project Settings
	InputMap.add_action(action, 0.4)
	for k in keys:
		var ek := InputEventKey.new()
		ek.physical_keycode = k
		InputMap.action_add_event(action, ek)
	for b in buttons:
		var eb := InputEventJoypadButton.new()
		eb.button_index = b
		InputMap.action_add_event(action, eb)
	for ax in axes:
		var em := InputEventJoypadMotion.new()
		em.axis = ax[0]
		em.axis_value = ax[1]
		InputMap.action_add_event(action, em)


func _load_assets() -> bool:
	var data = Sheet.read_json("res://assets/rig.json")
	if not (data is Dictionary):
		return false
	rig = data
	cell = Vector2(rig["cell"]["w"], rig["cell"]["h"])
	anchor = Vector2(rig["cell"]["ax"], rig["cell"]["ay"])
	for who in rig["characters"]:
		var sh = Sheet.new()
		var ch: Dictionary = rig["characters"][who]
		if not sh.open(ch["sheet"], ch["data"]):
			return false
		sheets[who] = sh
	shuttle_sheet = Sheet.new()
	if not shuttle_sheet.open("res://assets/sprites/shuttle.png", "res://assets/sprites/shuttle.json"):
		return false
	var cr: Dictionary = rig.get("crowd", {})
	if not cr.is_empty():
		crowd_sheet = Sheet.new()
		if not crowd_sheet.open(cr["sheet"], cr["data"]):
			crowd_sheet = null
	return true


func _sprite(tex: Texture2D, z: int) -> Sprite2D:
	var s := Sprite2D.new()
	s.texture = tex
	s.centered = false
	s.z_index = z
	add_child(s)
	return s


func _layer(z: int, painter: Callable) -> Node2D:
	var n := Node2D.new()
	n.z_index = z
	n.draw.connect(painter)
	add_child(n)
	return n


func _build_scene() -> void:
	# Seen from this camera, the net always covers red (left of it) and is always
	# covered by blue (right of it), whatever their depth: draw red, net, blue.
	_sprite(Sheet.load_texture("res://assets/court/background.png"), 0)
	if crowd_sheet != null:
		crowd_sprite = _sprite(crowd_sheet.texture, 0)
		crowd_sprite.region_enabled = true
		crowd_sprite.position = Vector2(rig["crowd"]["x"], rig["crowd"]["y"])
	layer_shadow = _layer(1, _draw_shadows)
	for side in 2:
		var s := _sprite(null, 3 if side == C.RED else 7)
		s.region_enabled = true
		s.offset = -anchor
		sprites.append(s)
	_sprite(Sheet.load_texture("res://assets/court/net_back.png"), 5)
	_sprite(Sheet.load_texture("res://assets/court/net_front.png"), 5)
	layer_shuttle = _layer(4, _draw_shuttle)
	layer_hud = _layer(10, _draw_hud)


func _make_players() -> void:
	players = []
	var names := ["red_woman", "blue_woman"] if women else ["red_man", "blue_man"]
	for side in 2:
		var pl = PlayerT.new()
		pl.setup(side, names[side], rig)
		players.append(pl)
		sprites[side].texture = sheets[names[side]].texture


# ------------------------------------------------------------------ flow
func _to_title() -> void:
	state = St.TITLE
	state_t = 0
	rally = null
	crowd_cheer = 0
	for side in 2:
		players[side].reset(Vector2(C.NET_X - players[side].f * C.HOME_U, 0.0))


func _start_match() -> void:
	_make_players()
	score.reset()
	for side in 2:
		cpus[side] = null if side == human else CPU.new(rng, side, level)
		players[side].err_scale = 1.0 if side == human else C.LEVELS[level]["err"]
	server = rng.randi() % 2
	_begin_serve()


func _serve_spots() -> Array:
	## Server and receiver stand diagonally: the server in the right court on an
	## even score, the left one on an odd score.
	var court := C.court_side(players[server].f, score.points[server])
	var spots := [Vector2.ZERO, Vector2.ZERO]
	for side in 2:
		var u: float = C.SERVER_U if side == server else C.RECEIVER_U
		var y: float = C.SERVE_Y * (court if side == server else -court)
		spots[side] = Vector2(C.NET_X - players[side].f * u, y)
	return spots


func _begin_serve() -> void:
	rally = Rally.new(rng, players[0], players[1], server, score.points[server])
	var spots := _serve_spots()
	for side in 2:
		players[side].reset(spots[side])
	var srv = players[server]
	if cpus[server] != null:
		serve_kind = "serve_high" if rng.randf() < 0.6 else "serve_short"
		serve_delay = rng.randi_range(40, 70)
	else:
		serve_kind = "serve_high"
	srv.serve_pose = "serve" if serve_kind == "serve_high" else "serve_short"
	players[1 - server].receiving = true
	trail.clear()
	mark_on = false
	state = St.SERVE
	state_t = 0
	if auto and stats["points"] < 2:
		_snapshot("serve")


func _do_serve(kind: String, aim_x: float, aim_y: float) -> void:
	rally.serve(kind, aim_x, aim_y)
	players[1 - server].receiving = false
	state = St.RALLY
	state_t = 0


# ------------------------------------------------------------------ ticking
func _physics_process(_delta: float) -> void:
	if not ok:
		return
	if Input.is_action_just_pressed("fullscreen"):
		var full := DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED if full
				else DisplayServer.WINDOW_MODE_FULLSCREEN)
	if Input.is_action_just_pressed("keys"):
		show_keys = not show_keys
	if Input.is_action_just_pressed("mute"):
		sfx.muted = not sfx.muted
		if sfx.muted:
			sfx.silence()                          # the crowd can run for 3 seconds
		_toast("SOUND OFF" if sfx.muted else "SOUND ON")
	if Input.is_action_just_pressed("crowd"):
		var on: bool = sfx.crowd_muted             # it was off, so it goes on
		sfx.set_crowd(on)
		_toast("CROWD SOUND ON" if on else "CROWD SOUND OFF")
	if toast_t > 0:
		toast_t -= 1
	if state != St.TITLE and state != St.MATCH_END and not auto and Input.is_action_just_pressed("pause"):
		paused = not paused
	elif paused and Input.is_action_just_pressed("back"):
		paused = false
		_to_title()
	if not paused:
		for _i in (auto_speed if auto else 1):
			_tick()
	_update_view()


func _tick() -> void:
	crowd_ms += 1000.0 / 60.0
	if crowd_cheer > 0:
		crowd_cheer -= 1
		if crowd_cheer == 0:
			crowd_ms = 0.0
	if hitstop > 0:
		hitstop -= 1
		return
	state_t += 1
	match state:
		St.TITLE:
			_title_tick()
		St.SERVE:
			_serve_tick()
		St.RALLY:
			_rally_tick()
		St.POINT:
			_point_tick()
		St.WALK:
			_walk_tick()
		St.GAME_END:
			_game_end_tick()
		St.MATCH_END:
			_match_end_tick()
	if not flash.is_empty():
		flash["t"] += 1
		if flash["t"] > 5:
			flash = {}
	if not dust.is_empty():
		dust["t"] += 1
		if dust["t"] > 10:
			dust = {}


func _title_tick() -> void:
	for pl in players:
		pl.move_x = 0.0
		pl.move_y = 0.0
		pl.update()
	if auto:
		var hold := 60 if shots_dir != "" else 10   # leave time to draw the title
		if state_t == floori(hold / 2.0):
			_snapshot("title")
		if state_t > hold:
			_start_match()
		return
	if Input.is_action_just_pressed("up"):
		menu_row = (menu_row + 2) % 3
		sfx.play("select", -8.0)
	if Input.is_action_just_pressed("down"):
		menu_row = (menu_row + 1) % 3
		sfx.play("select", -8.0)
	var step := 0
	if Input.is_action_just_pressed("left"):
		step = -1
	if Input.is_action_just_pressed("right"):
		step = 1
	if step != 0:
		if menu_row == 1:
			level = clampi(level + step, 0, 2)
		elif menu_row == 2:
			women = not women
			_make_players()
			_to_title()
		sfx.play("select", -8.0)
	if Input.is_action_just_pressed("start") or (menu_row == 0 and Input.is_action_just_pressed("clear")):
		sfx.play("select")
		_start_match()


func _human_input(allow_shots: bool) -> void:
	var pl = players[human]
	pl.move_x = Input.get_axis("left", "right")
	pl.move_y = Input.get_axis("up", "down")
	if Input.is_action_just_pressed("jump") and pl.jump():
		sfx.play("swing", -18.0, 0.7)
	if not allow_shots:
		return
	for b in ["clear", "drop", "smash"]:
		if Input.is_action_just_pressed(b):
			var aim_x := clampf(pl.move_x * pl.f, -1.0, 1.0)     # towards the net = short
			if rally.press(human, b, "", "", aim_x, pl.move_y):
				sfx.play("swing", -12.0)
			break


func _serve_tick() -> void:
	var srv = players[server]
	if cpus[server] != null:
		if state_t >= serve_delay:
			_do_serve(serve_kind, rng.randf_range(-1.0, 1.0), rng.randf_range(-1.0, 1.0))
	elif human == server:
		var aim_x := clampf(Input.get_axis("left", "right") * srv.f, -1.0, 1.0)
		var aim_y := Input.get_axis("up", "down")
		if Input.is_action_just_pressed("clear"):
			_do_serve("serve_high", aim_x, aim_y)
		elif Input.is_action_just_pressed("drop"):
			_do_serve("serve_short", aim_x, aim_y)
	if human >= 0 and human != server:
		_human_input(false)
	for pl in players:
		pl.update()


func _rally_tick() -> void:
	# 1. controllers
	if human >= 0:
		_human_input(true)
	if rally.s.state != "held":
		for side in 2:
			if cpus[side] != null:
				cpus[side].update(rally, players[side])
	# 2. contacts
	var hitter: int = rally.contacts()
	if hitter >= 0:
		_on_hit(hitter)
	# 3. players
	for pl in players:
		pl.update()
	# 4. shuttle
	var ev: String = rally.s.step()
	if ev == "net":
		sfx.play("net")
	elif ev == "land":
		_on_land()
		return
	rally.tick += 1
	if rally.s.state == "flight":
		trail.append(C.screen(rally.s.x, rally.s.y, rally.s.z))
		if trail.size() > 4:
			trail.pop_front()
	if rally.tick > 60 * 180:                      # safety net: a rally can't go on for ever
		if auto:
			print("rally stopped after %d ticks" % rally.tick)
		rally.s.state = "landed"
		_on_land()


func _on_hit(hitter: int) -> void:
	var other := 1 - hitter
	if cpus[other] != null:
		cpus[other].think(rally, players[other], players[hitter])
	if cpus[hitter] != null:
		cpus[hitter].plan = {}
	var h: Dictionary = rally.hit
	var impact: int = h["impact"]
	flash = {"pos": C.screen(h["x"], h["y"], h["z"]), "level": impact, "t": 0}
	hitstop = [0, 2, 4][impact]
	sfx.play(["soft", "hit", "smash"][impact], 0.0, rng.randf_range(0.95, 1.05))
	trail.clear()
	mark_on = false
	if human >= 0 and hitter != human and level < 2:
		var s = rally.s
		var pr := Phys.predict(s.x, s.y, s.z, s.vx, s.vy, s.vz, 400)
		if pr["outcome"] == "land":
			var pts: PackedVector3Array = pr["pts"]
			var land: Vector3 = pts[pts.size() - 1]
			land_mark = Vector2(land.x, land.y)
			mark_on = true
	if auto:
		stats["shots"] += 1
		var key := "%s/%s" % [players[hitter].stroke.get("name", "serve"), h["shot"]]
		stats["strokes"][key] = stats["strokes"].get(key, 0) + 1
		stats["max_solves"] = maxi(stats["max_solves"], h["solves"])
		stats["usec"] += h["usec"]
		stats["max_usec"] = maxi(stats["max_usec"], h["usec"])
		if stats["shots"] % 9 == 4:
			_snapshot("hit")


func _on_land() -> void:
	var res: Array = rally.decide()
	winner = res[0]
	call_text = CALLS.get(res[1], res[1])
	dust = {"pos": C.screen(rally.s.x, rally.s.y, 0.0), "t": 0}
	land_hop = 0
	land_dir = signf(rally.s.x - C.NET_X) if rally.s.via_net else signf(rally.s.vx)
	if land_dir == 0.0:
		land_dir = 1.0
	mark_on = false
	sfx.play("land", -4.0)
	outcome = score.add(winner)
	server = winner
	for side in 2:
		players[side].stroke = {}
		players[side].move_x = 0.0
		players[side].move_y = 0.0
		players[side].mood = "celebrate" if side == winner else "dejected"
	if human < 0 or winner == human:
		sfx.play("point", -6.0)
	else:
		sfx.play("lose", -6.0)
	crowd_cheer = {"point": 110, "game": 200, "match": 330}.get(outcome, 110)
	crowd_ms = 0.0
	if outcome == "point":
		sfx.play("cheer", -8.0, randf_range(0.94, 1.06))   # global RNG: leaves seeded play alone
	else:
		sfx.play("cheer_big", -4.0)
	state = St.POINT
	state_t = 0
	if auto:
		stats["points"] += 1
		stats["calls"][res[1]] = stats["calls"].get(res[1], 0) + 1
		stats["longest"] = maxi(stats["longest"], rally.shots)
		stats["max_ticks"] = maxi(stats["max_ticks"], rally.tick)
		print("point %3d  %s  %-5s after %2d shots  score %d-%d  games %d-%d" % [
				stats["points"], "RED " if winner == C.RED else "BLUE", res[1], rally.shots,
				score.points[0], score.points[1], score.games[0], score.games[1]])
		if stats["points"] % 5 == 1:
			_snapshot("point")


func _point_tick() -> void:
	land_hop += 1
	for pl in players:
		pl.update()
	if state_t > 80:
		if outcome == "point":
			state = St.WALK
		elif outcome == "game":
			state = St.GAME_END
			sfx.play("game", -4.0)
		else:
			state = St.MATCH_END
			sfx.play("game", -4.0)
		state_t = 0
		if auto and stats["points"] >= auto_points and outcome != "match":
			_finish_auto()


func _walk_tick() -> void:
	if state_t == 1:
		for pl in players:
			pl.mood = ""
	var spots := _serve_spots()
	var arrived := true
	for side in 2:
		var pl = players[side]
		var d: Vector2 = spots[side] - Vector2(pl.x, pl.y)
		var dist := d.length()
		if dist > 0.5:
			arrived = false
			var m := d * (minf(1.0, dist / 6.0) / dist)
			pl.move_x = m.x
			pl.move_y = m.y
		else:
			pl.move_x = 0.0
			pl.move_y = 0.0
		pl.update()
	if arrived or state_t > 75:
		_begin_serve()


func _game_end_tick() -> void:
	for pl in players:
		pl.update()
	if state_t > 150:
		score.new_game()
		state = St.WALK
		state_t = 0


func _match_end_tick() -> void:
	for pl in players:
		pl.mood = "celebrate" if score.games[pl.side] == 2 else "dejected"
		pl.update()
	if auto:
		if state_t == 30:
			_snapshot("match")
		if state_t > 40:
			_finish_auto()
		return
	if state_t > 60 and (Input.is_action_just_pressed("start") or Input.is_action_just_pressed("clear")):
		sfx.play("select")
		_to_title()


# ------------------------------------------------------------------ test mode
func _snapshot(tag: String) -> void:
	## Saves the next drawn frame (x4) as a PNG when --shots=DIR was given.
	if shots_dir == "" or DisplayServer.get_name() == "headless":
		return
	shot_count += 1
	var dir := shots_dir if shots_dir.is_absolute_path() else ProjectSettings.globalize_path("res://" + shots_dir)
	DirAccess.make_dir_recursive_absolute(dir)
	var ignore := dir.path_join(".gdignore")    # keeps the editor from importing the screenshots
	if not FileAccess.file_exists(ignore):
		FileAccess.open(ignore, FileAccess.WRITE)
	pending_shots.append(dir.path_join("%02d_%s.png" % [shot_count, tag]))
	if not RenderingServer.frame_post_draw.is_connected(_save_pending):
		RenderingServer.frame_post_draw.connect(_save_pending)


func _save_pending() -> void:
	## Saves one queued screenshot per drawn frame.
	if pending_shots.is_empty():
		return
	var img := get_viewport().get_texture().get_image()
	img.resize(C.W * 4, C.H * 4, Image.INTERPOLATE_NEAREST)
	img.save_png(pending_shots.pop_front())


func _finish_auto() -> void:
	if not auto:
		return
	auto = false
	var calls: Dictionary = stats["calls"]
	print("")
	print("AUTOPLAY REPORT  level %s  %s" % [LEVEL_NAMES[level], "women" if women else "men"])
	print("points %d  shots %d  (%.1f per point)  longest rally %d shots" % [stats["points"],
			stats["shots"], float(stats["shots"]) / maxi(1, stats["points"]), stats["longest"]])
	print("calls %s" % [calls])
	print("games %s  current %d-%d" % [score.history, score.points[0], score.points[1]])
	print("aiming a shot: %.1f ms on average, %.1f ms at most (%d solver runs at most)" % [
			stats["usec"] / 1000.0 / maxi(1, stats["shots"]), stats["max_usec"] / 1000.0, stats["max_solves"]])
	var keys: Array = stats["strokes"].keys()
	keys.sort_custom(func(a, b): return stats["strokes"][a] > stats["strokes"][b])
	var parts: Array = []
	for k in keys:
		parts.append("%s:%d" % [k, stats["strokes"][k]])
	print("strokes/shots %s" % [", ".join(parts)])
	var sane: bool = ok and stats["points"] > 0 and stats["shots"] >= stats["points"]
	print("RESULT %s" % ["OK" if sane else "PROBLEM"])
	get_tree().quit(0 if sane else 1)


# ------------------------------------------------------------------ licenses
func _license_notice(full: bool) -> String:
	## Godot is MIT licensed; its only condition is that the notice ships with the
	## game. `full` adds the engine's third-party components (FreeType, mbed TLS...).
	var out := PackedStringArray(["This game uses Godot Engine, available under the following license:",
			"", Engine.get_license_text()])
	if not full:
		out.append("Third-party components of Godot Engine and their licenses: https://godotengine.org/license")
		return "\n".join(out)
	out.append("")
	out.append("Godot Engine includes the following third-party components:")
	for info in Engine.get_copyright_info():
		for part in info["parts"]:
			out.append("")
			out.append("Comment: %s" % info["name"])
			out.append("Files: %s" % ", ".join(PackedStringArray(part["files"])))
			for holder in part["copyright"]:
				out.append("Copyright: %s" % holder)
			out.append("License: %s" % part["license"])
	var texts: Dictionary = Engine.get_license_info()
	for key in texts:
		out.append("")
		out.append("License: %s" % key)
		out.append("")
		out.append(str(texts[key]))
	return "\n".join(out)


func _write_licenses() -> void:
	var text := _license_notice(true)
	if licenses_to == "-":
		print(text)
		get_tree().quit()
		return
	var f := FileAccess.open(licenses_to, FileAccess.WRITE)
	if f == null:
		push_error("Cannot write %s" % licenses_to)
		get_tree().quit(1)
		return
	f.store_string(text + "\n")
	f.close()
	get_tree().quit()


# ------------------------------------------------------------------ view
func _update_view() -> void:
	if players.is_empty():
		return
	for side in 2:
		var pl = players[side]
		var sh = sheets[pl.who]
		var loop: bool = rig["anims"].get(pl.anim, {}).get("loop", false)
		var idx: int = sh.frame_index(pl.anim, pl.anim_frame, pl.anim_time, loop)
		sprites[side].region_rect = sh.rects[idx]
		var p := C.screen(pl.x, pl.y, pl.z)
		sprites[side].position = Vector2(roundf(p.x), roundf(p.y))
	if crowd_sprite != null:
		var tag := "cheer" if crowd_cheer > 0 else "idle"
		crowd_sprite.region_rect = crowd_sheet.rects[crowd_sheet.frame_index(tag, -1, crowd_ms, true)]
	layer_shuttle.z_index = _shuttle_layer()
	layer_shadow.queue_redraw()
	layer_shuttle.queue_redraw()
	layer_hud.queue_redraw()


func _px(ci: CanvasItem, x: float, y: float, col: Color) -> void:
	ci.draw_rect(Rect2(roundf(x), roundf(y), 1, 1), col)


func _draw_shadows() -> void:
	var ci := layer_shadow
	for pl in players:
		var p := C.screen(pl.x, pl.y, 0.0)
		var rx := roundf(p.x)
		var ry := roundf(p.y)
		var hw := maxf(2.5, 5.5 - 0.3 * pl.pose_lift() - 0.12 * pl.z)
		for y in [ry - 1.0, ry, ry + 1.0]:
			for x in range(floori(rx - hw), ceili(rx + hw) + 1):
				if pow((x - rx) / hw, 2.0) + pow((y - ry) / 1.4, 2.0) <= 1.0:
					ci.draw_rect(Rect2(x, y, 1, 1), COL_SHADOW)
	if rally != null and (rally.s.state == "flight" or rally.s.state == "net") and rally.s.z > 1.0:
		var fp := C.screen(rally.s.x, rally.s.y, 0.0)
		var w := 2 if rally.s.z < 25.0 else 1
		for x in range(roundi(fp.x) - w, roundi(fp.x) + w + 1):
			ci.draw_rect(Rect2(x, roundf(fp.y) + 1.0, 1, 1), COL_SHADOW)
	if mark_on and state == St.RALLY:
		var m := C.screen(land_mark.x, land_mark.y, 0.0)
		for d in [Vector2(-2, 1), Vector2(2, 1), Vector2(-1, 0), Vector2(1, 0), Vector2(-1, 2), Vector2(1, 2)]:
			_px(ci, m.x + d.x, m.y + d.y, COL_MARK)


func _shuttle_pose() -> Array:
	## [court position, screen direction] of the shuttle to draw, or [] when hidden.
	if rally == null or state == St.TITLE or state == St.WALK or state == St.GAME_END \
			or state == St.MATCH_END:
		return []
	var s = rally.s
	if s.state == "held":
		return [players[rally.server].held_shuttle(), Vector2(0, 1)]
	if s.state == "flight":
		return [s.pos(), C.screen_dir(s.vel())]
	if s.state == "net":
		return [s.pos(), Vector2(0, 1).rotated(s.spin)]
	var hop := 0.0
	if land_hop < 10:
		hop = sin(land_hop / 10.0 * PI) * 2.5
	return [Vector3(s.x + land_dir * minf(land_hop, 8.0) * 0.4, s.y, hop + 0.6), Vector2(land_dir, 0.35)]


func _shuttle_layer() -> int:
	## Draw order of the shuttle: in front of or behind the player on its side of
	## the net (nearer the camera = drawn later); red side below the net, blue above.
	var pose := _shuttle_pose()
	if pose.is_empty():
		return 4
	var p: Vector3 = pose[0]
	if p.x < C.NET_X:
		return 4 if p.y >= players[C.RED].y else 2
	return 8 if p.y >= players[C.BLUE].y else 6


func _draw_shuttle() -> void:
	var ci := layer_shuttle
	var pose := _shuttle_pose()
	if not pose.is_empty():
		var at: Vector3 = pose[0]
		var p := C.screen(at.x, at.y, at.z)
		var dir: Vector2 = pose[1]
		var i := posmod(roundi(dir.angle() / (TAU / 32.0)), 32)
		var r: Rect2 = shuttle_sheet.rects[i]
		ci.draw_texture_rect_region(shuttle_sheet.texture,
				Rect2(roundf(p.x) - 6.0, roundf(p.y) - 6.0, r.size.x, r.size.y), r)
		if trail.size() >= 2:                       # speed trail
			var a: Vector2 = trail[0]
			var dist := a.distance_to(p)
			if dist > 10.0:
				var n := int(dist)
				for k in range(1, n):
					var q := a.lerp(p, float(k) / n)
					if q.distance_to(p) > 3.2 and (k % 2 == 0 or dist > 25.0):
						_px(ci, q.x, q.y, COL_TRAIL)
		if p.y < 2.0:                               # off the top: an arrow
			var ax := roundf(p.x)
			for d in [Vector2(0, 1), Vector2(-1, 2), Vector2(1, 2), Vector2(-2, 3), Vector2(2, 3), Vector2(0, 2), Vector2(0, 3)]:
				_px(ci, ax + d.x, d.y, COL_TEXT)
	if not flash.is_empty():
		var c: Vector2 = flash["pos"]
		var rays: Array = [Vector2(4, 0), Vector2(-4, 0), Vector2(0, 4), Vector2(0, -4)]
		if flash["level"] >= 1:
			rays = [Vector2(5, 0), Vector2(6, 0), Vector2(-5, 0), Vector2(-6, 0), Vector2(0, 5), Vector2(0, 6),
					Vector2(0, -5), Vector2(0, -6), Vector2(4, 4), Vector2(-4, 4), Vector2(4, -4), Vector2(-4, -4)]
		if flash["level"] >= 2:
			rays.append_array([Vector2(7, 0), Vector2(-7, 0), Vector2(0, 7), Vector2(0, -7), Vector2(5, 5),
					Vector2(-5, 5), Vector2(5, -5), Vector2(-5, -5)])
		var col := COL_FLASH_SOFT if flash["level"] == 0 else COL_GOLD
		for d in rays:
			_px(ci, c.x + d.x, c.y + d.y, col)
	if not dust.is_empty():
		var c2: Vector2 = dust["pos"]
		var spread := 3.0 if dust["t"] < 5 else 5.0
		for d in [Vector2(-spread, 0), Vector2(spread, 0), Vector2(-spread + 1, -1), Vector2(spread - 1, -1)]:
			_px(ci, c2.x + d.x, c2.y + d.y, COL_DUST)


func _draw_score(ci: CanvasItem) -> void:
	var sbx := 8.0
	var blink := state == St.POINT and floori(state_t / 8.0) % 2 == 1
	for side in 2:
		var pts: int = score.points[side]
		var col := COL_RED if side == C.RED else COL_BLUE
		if blink and side == winner:
			col = COL_RED_DIM if side == C.RED else COL_BLUE_DIM
		var tens_x := sbx + (5.0 if side == C.RED else 24.0)
		if pts >= 10:
			PixelFont.draw(ci, Vector2(tens_x, 16), str(floori(pts / 10.0)), col)
		PixelFont.draw(ci, Vector2(tens_x + 4.0, 16), str(pts % 10), col)
		for g in score.games[side]:                 # games won: dots under the digits
			ci.draw_rect(Rect2(tens_x + 1.0 + g * 4.0, 23, 2, 1), col)
	ci.draw_rect(Rect2(sbx + 17.0, 17, 1, 1), COL_COLON)
	ci.draw_rect(Rect2(sbx + 17.0, 20, 1, 1), COL_COLON)
	if state == St.SERVE or state == St.RALLY or state == St.POINT:
		var sx := sbx + (10.0 if server == C.RED else 29.0)
		ci.draw_rect(Rect2(sx, 13, 2, 1), COL_GOLD)     # who serves
	var game := "GAME %d" % score.game_no
	PixelFont.draw(ci, Vector2(C.W - 6 - PixelFont.width(game), 12), game, COL_TEXT, 1, COL_INK)


func _box(ci: CanvasItem, lines: Array, y: float, colors: Array) -> void:
	var w := 0
	for ln in lines:
		w = maxi(w, PixelFont.width(ln))
	var h := lines.size() * 7 + 3
	ci.draw_rect(Rect2(96 - w / 2.0 - 4.0, y - 2.0, w + 8.0, h), COL_PANEL)
	for i in lines.size():
		var col: Color = colors[mini(i, colors.size() - 1)]
		PixelFont.draw_centered(ci, 96.0, y + i * 7.0, lines[i], col)


func _side_name(side: int) -> String:
	if human < 0:
		return "RED" if side == C.RED else "BLUE"
	return "YOU" if side == human else "CPU"


func _draw_hud() -> void:
	var ci := layer_hud
	if players.is_empty():
		return
	if state == St.TITLE:
		_draw_title(ci)
		_draw_toast(ci)
		return
	_draw_score(ci)
	if show_keys and human >= 0:
		_draw_keys(ci)
	match state:
		St.SERVE:
			var sub := ""
			if score.match_point(0) or score.match_point(1):
				sub = "MATCH POINT"
			elif score.game_point(0) or score.game_point(1):
				sub = "GAME POINT"
			if sub != "":
				_box(ci, [sub], 30.0, [COL_GOLD])
			if server == human and state_t > 10 and not show_keys:
				PixelFont.draw_centered(ci, 96.0, 100.0, "2 HIGH SERVE   3 SHORT SERVE", COL_TEXT, 1, COL_INK)
		St.POINT:
			var who := _side_name(winner)
			_box(ci, [call_text, "%s %d-%d" % ["POINT " + who, score.points[0], score.points[1]]], 28.0,
					[COL_GOLD, COL_TEXT])
		St.GAME_END:
			var last: Array = score.history[score.history.size() - 1]
			var gw := 0 if last[0] > last[1] else 1
			_box(ci, ["GAME %s" % _side_name(gw), "%d-%d" % [last[0], last[1]],
					"GAMES %d-%d" % [score.games[0], score.games[1]]], 26.0, [COL_GOLD, COL_TEXT])
		St.MATCH_END:
			var mw := 0 if score.games[0] == 2 else 1
			var title := "%s WIN!" % _side_name(mw) if _side_name(mw) == "YOU" else "%s WINS" % _side_name(mw)
			var games: Array = []
			for g in score.history:
				games.append("%d-%d" % [g[0], g[1]])
			var lines := [title, "  ".join(games)]
			if state_t > 60 and human >= 0:
				lines.append("ENTER: MENU")
			_box(ci, lines, 26.0, [COL_GOLD, COL_TEXT])
	if paused:
		ci.draw_rect(Rect2(0, 0, C.W, C.H), Color(0, 0, 0, 0.55))
		_box(ci, ["PAUSED", "ESC: PLAY   Q: MENU", "H: SHOW/HIDE KEYS",
				"M: SOUND %s   N: CROWD %s" % ["OFF" if sfx.muted else "ON", "OFF" if sfx.crowd_muted else "ON"]],
				44.0, [COL_GOLD, COL_TEXT])
	else:
		_draw_toast(ci)


func _toast(text: String) -> void:
	toast = text
	toast_t = 70


func _draw_toast(ci: CanvasItem) -> void:
	if toast_t > 0:
		_box(ci, [toast], 1.0, [COL_GOLD])


func _draw_keys(ci: CanvasItem) -> void:
	## One line of keyboard controls on the floor strip below the court (rows
	## 99-107, which no player, shadow or shuttle reaches); keys in gold.
	var pairs := [["←↑↓→", "MOVE"], ["1", "JUMP"], ["2", "CLEAR"], ["3", "DROP"], ["4", "SMASH"]]
	if state == St.SERVE and server == human:
		pairs = [["2", "HIGH SERVE"], ["3", "SHORT SERVE"], ["←↑↓→", "AIM"]]
	var parts: Array = []
	for pr in pairs:
		parts.append("%s %s" % [pr[0], pr[1]])
	var x := roundf(96.0 - PixelFont.width("  ".join(parts)) / 2.0)
	ci.draw_rect(Rect2(0, 99, C.W, C.H - 99), COL_PANEL)
	for pr in pairs:
		var key: String = pr[0]
		var action: String = " " + pr[1] + "  "
		PixelFont.draw(ci, Vector2(x, 101), key, COL_GOLD)
		x += key.length() * 4
		PixelFont.draw(ci, Vector2(x, 101), action, COL_TEXT)
		x += action.length() * 4


func _draw_title(ci: CanvasItem) -> void:
	ci.draw_rect(Rect2(48, 7, 96, 24), COL_PANEL)        # keeps the title clear of the crowd
	PixelFont.draw_centered(ci, 96.0, 10.0, "BADMINTON", COL_TEXT, 2, COL_INK)
	PixelFont.draw_centered(ci, 96.0, 24.0, "SINGLES - 3x15 SCORING", COL_GOLD, 1, COL_INK)
	var rows := ["PLAY", "LEVEL  < %s >" % LEVEL_NAMES[level],
			"EVENT  < %s >" % ("WOMEN'S SINGLES" if women else "MEN'S SINGLES")]
	ci.draw_rect(Rect2(36, 34, 120, 25), COL_PANEL)
	for i in rows.size():
		var col := COL_GOLD if i == menu_row else COL_TEXT
		PixelFont.draw_centered(ci, 96.0, 37.0 + i * 7.0, rows[i], col)
		if i == menu_row:
			PixelFont.draw(ci, Vector2(40, 37.0 + i * 7.0), ">", COL_GOLD)
	ci.draw_rect(Rect2(10, 92, 172, 15), COL_PANEL)
	PixelFont.draw_centered(ci, 96.0, 94.0, "ARROWS MOVE   ENTER START", COL_TEXT)
	PixelFont.draw_centered(ci, 96.0, 101.0, "1 JUMP   2 CLEAR   3 DROP   4 SMASH", COL_TEXT)
