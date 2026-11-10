extends RefCounted
## A sprite sheet exported by Aseprite (PNG + JSON array data with frame tags).

var texture: Texture2D
var rects: Array = []           # Rect2 per frame
var durations: Array = []       # ms per frame
var tags := {}                  # tag name -> Vector2i(from, to)


static func load_texture(path: String) -> Texture2D:
	## The imported texture, or the PNG read directly when the project has not
	## been imported yet (e.g. a first headless run).
	if ResourceLoader.exists(path):
		var res = load(path)
		if res is Texture2D:
			return res
	var img := Image.load_from_file(ProjectSettings.globalize_path(path))
	if img == null or img.is_empty():
		push_error("Cannot load image " + path)
		return null
	return ImageTexture.create_from_image(img)


static func read_json(path: String) -> Variant:
	var text := FileAccess.get_file_as_string(path)
	if text != "":
		return JSON.parse_string(text)
	if ResourceLoader.exists(path):
		var res = load(path)
		if res is JSON:
			return res.data
	push_error("Cannot read " + path + " (exported game? add *.json to the export filters)")
	return null


func open(png: String, json: String) -> bool:
	texture = load_texture(png)
	var data = read_json(json)
	if texture == null or not (data is Dictionary):
		return false
	var frames = data["frames"]
	if frames is Dictionary:            # json-hash export: keep the file's order
		frames = frames.values()
	for fr in frames:
		var r: Dictionary = fr["frame"]
		rects.append(Rect2(r["x"], r["y"], r["w"], r["h"]))
		durations.append(int(fr.get("duration", 100)))
	for t in data["meta"].get("frameTags", []):
		tags[t["name"]] = Vector2i(int(t["from"]), int(t["to"]))
	return true


func frame_index(tag: String, frame: int, time_ms: float, loop: bool) -> int:
	## Sheet frame for a tag: an explicit frame of the tag, or the frame showing
	## after `time_ms` (looping or holding the last frame).
	if not tags.has(tag):
		return 0
	var span: Vector2i = tags[tag]
	var count := span.y - span.x + 1
	if frame >= 0:
		return span.x + clampi(frame, 0, count - 1)
	var total := 0
	for i in count:
		total += durations[span.x + i]
	var t := time_ms
	if loop and total > 0:
		t = fmod(time_ms, float(total))
	for i in count:
		t -= durations[span.x + i]
		if t < 0.0:
			return span.x + i
	return span.y
