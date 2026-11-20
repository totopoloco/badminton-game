extends RefCounted
## Rally-point scoring, 3 x 15: games to 15; from 14-all a side needs a two-point
## lead; at 20-all the next point wins (21 caps the game). Best of three games.
## Players change ends after the first game, after the second when there is a
## third, and in the third game when a side first reaches 8 points (law 8).

const ENDS_AT := 8             # third game: change ends when a side first reaches this

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


func change_ends_after(side: int, outcome: String) -> bool:
	## Whether the point `side` just won (add() returned `outcome`) is followed by
	## a change of ends.
	if outcome == "game":
		return true                # a game ended and another one follows
	return outcome == "point" and game_no == 3 and points[side] == ENDS_AT \
			and points[1 - side] < ENDS_AT


func ends_changes_so_far() -> int:
	## How many changes of ends law 8 requires by now: one after every finished
	## game that another game follows (at most two), and one in the third game at 8.
	var over: bool = games[0] == 2 or games[1] == 2
	var between := mini(history.size() - (1 if over else 0), 2)
	var third := 1 if game_no == 3 and maxi(points[0], points[1]) >= ENDS_AT else 0
	return between + third


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
