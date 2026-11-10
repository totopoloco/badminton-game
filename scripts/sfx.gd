extends Node
## Sound effects synthesized at startup (no audio files needed).

const RATE := 22050

var streams := {}
var players: Array = []
var muted := false
var crowd_muted := false            # the crowd's cheering only (N)
var _crowd: AudioStreamPlayer       # the crowd has its own player, so short sounds never cut it
var _next := 0
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	_rng.seed = 1234
	streams["hit"] = _make(_hit(0.10, 1400.0, 0.012, 0.55))
	streams["soft"] = _make(_hit(0.07, 1900.0, 0.006, 0.30))
	streams["smash"] = _make(_smash())
	streams["net"] = _make(_net())
	streams["land"] = _make(_land())
	streams["swing"] = _make(_swing())
	streams["point"] = _make(_beeps([880.0, 1320.0], 0.11, 0.35))
	streams["lose"] = _make(_beeps([520.0, 390.0], 0.12, 0.30))
	streams["game"] = _make(_beeps([660.0, 880.0, 1100.0, 1320.0], 0.10, 0.35))
	streams["select"] = _make(_beeps([1000.0], 0.05, 0.25))
	streams["cheer"] = _make(_cheer(1.8, 40.0, 0))
	streams["cheer_big"] = _make(_cheer(3.0, 60.0, 2))
	for i in 6:
		var pl := AudioStreamPlayer.new()
		add_child(pl)
		players.append(pl)
	_crowd = AudioStreamPlayer.new()
	add_child(_crowd)


func play(sound: String, volume_db: float = 0.0, pitch: float = 1.0) -> void:
	if muted or not streams.has(sound):
		return
	var pl: AudioStreamPlayer = _crowd
	if sound.begins_with("cheer"):
		if crowd_muted:
			return
	else:
		pl = players[_next]
		_next = (_next + 1) % players.size()
	pl.stream = streams[sound]
	pl.volume_db = volume_db
	pl.pitch_scale = pitch
	pl.play()


func set_crowd(on: bool) -> void:
	## Crowd sound on or off; turning it off also stops a cheer in progress.
	crowd_muted = not on
	if not on:
		_crowd.stop()


func silence() -> void:
	for pl in players + [_crowd]:
		pl.stop()


func _make(samples: PackedFloat32Array) -> AudioStreamWAV:
	var data := PackedByteArray()
	data.resize(samples.size() * 2)
	for i in samples.size():
		data.encode_s16(i * 2, int(clampf(samples[i], -1.0, 1.0) * 32767.0))
	var s := AudioStreamWAV.new()
	s.format = AudioStreamWAV.FORMAT_16_BITS
	s.mix_rate = RATE
	s.stereo = false
	s.data = data
	return s


func _noise() -> float:
	return _rng.randf_range(-1.0, 1.0)


func _hit(dur: float, tone: float, crack: float, amp: float) -> PackedFloat32Array:
	## Racket on cork: a short crack of noise and a damped "pock".
	var n := int(dur * RATE)
	var out := PackedFloat32Array()
	out.resize(n)
	for i in n:
		var t := float(i) / RATE
		var v := _noise() * exp(-t / crack) * 0.8
		v += sin(TAU * tone * t) * exp(-t / 0.022) * 0.7
		v += sin(TAU * tone * 2.3 * t) * exp(-t / 0.010) * 0.25
		out[i] = v * amp
	return out


func _smash() -> PackedFloat32Array:
	var n := int(0.16 * RATE)
	var out := PackedFloat32Array()
	out.resize(n)
	var lp := 0.0
	for i in n:
		var t := float(i) / RATE
		lp += (_noise() - lp) * 0.35
		var v := lp * exp(-t / 0.030) * 1.2 + _noise() * exp(-t / 0.006) * 0.6
		v += sin(TAU * 950.0 * t) * exp(-t / 0.030) * 0.6
		v += sin(TAU * 2300.0 * t) * exp(-t / 0.012) * 0.3
		out[i] = v * 0.75
	return out


func _net() -> PackedFloat32Array:
	var n := int(0.28 * RATE)
	var out := PackedFloat32Array()
	out.resize(n)
	for i in n:
		var t := float(i) / RATE
		var rattle := (0.5 + 0.5 * sin(TAU * 28.0 * t)) * _noise() * exp(-t / 0.08) * 0.35
		out[i] = (sin(TAU * 170.0 * t) * exp(-t / 0.07) * 0.8 + rattle) * 0.7
	return out


func _land() -> PackedFloat32Array:
	var n := int(0.12 * RATE)
	var out := PackedFloat32Array()
	out.resize(n)
	var lp := 0.0
	for i in n:
		var t := float(i) / RATE
		lp += (_noise() - lp) * 0.15
		out[i] = (sin(TAU * 120.0 * t) * exp(-t / 0.03) * 0.7 + lp * exp(-t / 0.02) * 0.8) * 0.55
	return out


func _swing() -> PackedFloat32Array:
	## A racket whoosh: band-limited noise swelling and fading.
	var n := int(0.13 * RATE)
	var out := PackedFloat32Array()
	out.resize(n)
	var lp := 0.0
	var lp2 := 0.0
	for i in n:
		var t := float(i) / n
		lp += (_noise() - lp) * 0.25
		lp2 += (lp - lp2) * 0.25
		out[i] = (lp - lp2) * sin(PI * t) * 1.6
	return out


func _beeps(tones: Array, each: float, amp: float) -> PackedFloat32Array:
	var n := int(each * RATE)
	var out := PackedFloat32Array()
	out.resize(n * tones.size())
	for k in tones.size():
		var tone: float = tones[k]
		for i in n:
			var t := float(i) / RATE
			var env := minf(1.0, t / 0.005) * minf(1.0, (each - t) / 0.02)
			var v := sin(TAU * tone * t) + 0.3 * sin(TAU * tone * 2.0 * t)
			out[k * n + i] = v * env * amp
	return out


func _cheer(dur: float, claps_per_s: float, whistles: int) -> PackedFloat32Array:
	## A crowd cheering: noise through two vowel-like resonances (the voices),
	## short bursts of noise at random times (the applause) and, for the big
	## moments, a couple of whistles; it swells up quickly and dies away.
	var n := int(dur * RATE)
	var out := PackedFloat32Array()
	out.resize(n)
	var fa := _bandpass(560.0, 0.8)
	var fb := _bandpass(1150.0, 1.2)
	var a0: float = fa[0]
	var a1: float = fa[1]
	var a2: float = fa[2]
	var a3: float = fa[3]
	var b0: float = fb[0]
	var b1: float = fb[1]
	var b2: float = fb[2]
	var b3: float = fb[3]
	var x1 := 0.0
	var x2 := 0.0
	var ya1 := 0.0
	var ya2 := 0.0
	var yb1 := 0.0
	var yb2 := 0.0
	var attack := int(0.12 * RATE)
	var hold := int(dur * 0.3 * RATE)
	var fade := pow(0.03, 1.0 / (n - hold))
	var env := 0.0
	var swell := 1.0
	var step := 0.0
	for i in n:
		if i % 1024 == 0:                          # many voices: a slow, uneven swell
			step = (_rng.randf_range(0.75, 1.15) - swell) / 1024.0
		swell += step
		if i < attack:
			env = float(i) / attack
		elif i >= hold:
			env *= fade
		var x := _noise()
		var ya := a0 * x + a1 * x2 - a2 * ya1 - a3 * ya2
		var yb := b0 * x + b1 * x2 - b2 * yb1 - b3 * yb2
		x2 = x1
		x1 = x
		ya2 = ya1
		ya1 = ya
		yb2 = yb1
		yb1 = yb
		out[i] = (0.75 * ya + 0.45 * yb) * env * swell * 0.9
	var clap_fade := exp(-1.0 / (0.004 * RATE))
	for _c in int(dur * claps_per_s):             # applause, thicker at the start
		var t0 := pow(_rng.randf(), 1.5) * (dur - 0.03)
		var e := _applause_env(t0, dur) * _rng.randf_range(0.25, 0.8) * 0.55
		var i0 := int(t0 * RATE)
		var prev := 0.0
		for j in mini(int(_rng.randf_range(0.010, 0.020) * RATE), n - i0):
			var nz := _noise()
			out[i0 + j] += (nz - 0.7 * prev) * e
			prev = nz
			e *= clap_fade
	for _w in whistles:                           # a quick rise, a wobble, a fade
		var i0 := int(_rng.randf_range(0.10, 0.45) * dur * RATE)
		var f0 := _rng.randf_range(1900.0, 2400.0)
		var ph := 0.0
		for j in mini(int(0.42 * RATE), n - i0):
			var t := float(j) / RATE
			var f := f0 * (1.0 + 0.22 * minf(1.0, t / 0.09)) * (1.0 + 0.012 * sin(TAU * 6.5 * t))
			ph += TAU * f / RATE
			out[i0 + j] += sin(ph) * minf(1.0, t / 0.02) * minf(1.0, (0.42 - t) / 0.12) * 0.16
	var peak := 0.0
	for v in out:
		peak = maxf(peak, absf(v))
	if peak > 0.0:
		for i in n:
			out[i] *= 0.85 / peak
	return out


static func _bandpass(f0: float, q: float) -> Array:
	## Band-pass biquad (b0, b2, a1, a2 over a0; b1 is 0), peak gain 1.
	var w0 := TAU * f0 / RATE
	var alpha := sin(w0) / (2.0 * q)
	var norm := 1.0 + alpha
	return [alpha / norm, -alpha / norm, -2.0 * cos(w0) / norm, (1.0 - alpha) / norm]


static func _applause_env(t: float, dur: float) -> float:
	if t < 0.05:
		return t / 0.05
	var hold := dur * 0.45
	if t < hold:
		return 1.0
	return exp(log(0.05) * (t - hold) / (dur - hold))
