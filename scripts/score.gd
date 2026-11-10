extends RefCounted
## Rally-point scoring, 3 x 15: games to 15; from 14-all a side needs a two-point
## lead; at 20-all the next point wins (21 caps the game). Best of three games.

var points := [0, 0]
var games := [0, 0]
var game_no := 1
var history: Array = []        # [red, blue] points of every finished game


func reset() -> void:
	points = [0, 0]
	games = [0, 0]
	game_no = 1
	history = []


func game_winner() -> int:
	for side in 2:
		var me: int = points[side]
		var them: int = points[1 - side]
		if me >= 21 or (me >= 15 and me - them >= 2):
			return side
	return -1


func add(side: int) -> String:
	## A point to `side`. Returns "point", "game" or "match".
	points[side] += 1
	var g := game_winner()
	if g < 0:
		return "point"
	games[g] += 1
	history.append(points.duplicate())
	return "match" if games[g] == 2 else "game"


func new_game() -> void:
	points = [0, 0]
	game_no += 1


func game_point(side: int) -> bool:
	## Would one more point win the game for `side`?
	var me: int = points[side] + 1
	var them: int = points[1 - side]
	return me >= 21 or (me >= 15 and me - them >= 2)


func match_point(side: int) -> bool:
	return game_point(side) and games[side] == 1
