# Badminton — singles against the computer (Godot 4)

A pixel-art badminton game built from the Aseprite animations: the same hall,
court, net, players and shuttle, drawn through aseprite-mcp and exported as
sprite sheets. You play red; the computer plays blue. A crowd in the stands
cheers every point (longer after a game or the match), and the boards along
the court carry invented sponsors.

**Play it in your browser: https://totopoloco.github.io/badminton-game/**
(a desktop browser with a keyboard; click the game once so it gets the keys).

[![Web build](https://github.com/totopoloco/badminton-game/actions/workflows/pages.yml/badge.svg)](https://github.com/totopoloco/badminton-game/actions/workflows/pages.yml)

How the code fits together, with diagrams: [ARCHITECTURE.md](ARCHITECTURE.md).

## Run it

Needs Godot 4.3 or newer (standard build; the project uses the GL Compatibility
renderer, so it runs on almost any GPU).

- **Editor:** open Godot, *Import*, pick `~/badminton/game/project.godot`, then
  press **F5**. The first open imports the PNGs (a few seconds).
- **Command line:** `/path/to/Godot --path ~/badminton/game`

F11 toggles fullscreen (the 192×108 picture scales by whole pixels), M turns all
sound off or on, N only the crowd's cheering, H shows or hides the controls bar
under the court, Esc pauses (Q from the pause screen goes back to the menu; the
pause screen also shows whether sound and crowd are on). To share the game or play it in a browser, see
*Sharing the game* below.

## Controls

| | Keyboard | Gamepad |
|---|---|---|
| Move along the court | ← / → | left stick or D-pad |
| Move across the court | ↑ / ↓ | left stick or D-pad |
| Jump | 1 (or Space) | Y or RB |
| Clear / lift | 2 (or Z) | A |
| Drop / net shot | 3 (or X) | X |
| Smash / drive / kill | 4 (or C) | B |
| Serve | 2 = high serve, 3 = short serve | A / X |
| Menu | ↑ / ↓ to choose, ← / → to change, Enter to start | D-pad, Start |

1 to 4 are the number keys above the letters (not the numeric keypad), so one
hand plays the shots while the other moves. They go by key position, so they work
with any keyboard layout. Space, Z, X and C do the same as 1, 2, 3 and 4.

How a swing works:

- Press a shot button a moment **before** the shuttle reaches you (up to about a
  third of a second early); the racket meets it when it arrives. You can keep
  moving while you wait.
- The stroke is chosen from where the shuttle is: overhead when it is high,
  drive or block at chest height, lunge (net shot / lift) when it is low, kill
  when it is above the tape close to the net. The button decides the shot.
- The direction you are moving aims it: towards the net = shorter, away =
  deeper; up = towards the far sideline, down = towards the near one.
- You can reach a little further sideways than forwards, but wide shots still
  need footwork.
- **Jump smash:** jump (1) under a high shuttle and press 4 in the air.
  Jumps go straight up, so get under the shuttle first.
- On Easy and Normal a small yellow mark shows where the computer's shot will
  land, so you can leave shuttles that are going out.

## Rules

Rally-point scoring, best of three games under the 3×15 system: games to 15;
from 14-all a side needs a two-point lead; at 20-all the next point wins.
The rally winner serves, from the right service court on an even score and the
left one on an odd score, diagonally into the opposite service court (past the
short service line; landing in the wrong court is a service fault). A shot is
out beyond the baseline or the singles sideline (the inner one), and a shuttle
that hits the net or doesn't cross it loses the point. Levels: Easy, Normal,
Hard. Event: men's or women's singles.

## Self-test (computer against computer)

Headless, prints a line per point and a report, exits with code 0 if all is well:

    /path/to/Godot --headless --path ~/badminton/game -- --autoplay --points=40 --speed=8

With a window it also saves screenshots to `~/badminton/game/test_out/`:

    /path/to/Godot --path ~/badminton/game -- --autoplay --points=12 --speed=2 --shots=test_out

Options: `--level=0|1|2`, `--seed=N`, `--women`.

## Redrawing the art in Aseprite

All sprites come from `art/badminton_game_assets.py`, which draws with the
renderer of the three animation scripts next to it (`badminton_rally.py`,
`badminton_point.py`, `badminton_doubles.py`). To redraw them with your Aseprite
build through the aseprite-mcp server (this also writes the `.aseprite` sources
to `assets/source/`), from the project folder:

    uv run art/badminton_game_assets.py mcp --mcp-dir ~/aseprite-mcp --game .

With `preview` instead of `mcp --mcp-dir ~/aseprite-mcp` the same drawing calls
run through Pillow, no Aseprite needed (that is how the shipped PNGs were made).
Then reopen the project so Godot re-imports the PNGs. The sponsor names are
`SPONSORS` near the top of that script (up to 8 characters each); the crowd's
seats and colours are next to them.

## Files

| Path | What it is |
|---|---|
| `ARCHITECTURE.md` | how the code fits together, with diagrams |
| `project.godot`, `main.tscn` | project settings (192×108, pixel-perfect scaling) and the one scene |
| `scripts/main.gd` | game flow, input, drawing, HUD, self-test mode |
| `scripts/rally.gd` | rules of a rally: swings, contacts, the call |
| `scripts/physics.gd` | shuttle flight (gravity + air drag), shot solver, reach rules |
| `scripts/player.gd`, `cpu.gd` | player movement and animation; the computer player |
| `scripts/config.gd` | all tunable numbers: shots, speeds, CPU levels |
| `scripts/score.gd`, `sheet.gd`, `pixel_font.gd`, `sfx.gd` | scoring, Aseprite sheet loader, 3×5 font, synthesized sounds (crowd included) |
| `assets/` | sprite sheets + Aseprite JSON (players, shuttle, crowd), court layers, `rig.json` (racket contact points, where the crowd goes) |
| `art/` | the drawing scripts (Python, through aseprite-mcp or Pillow) |
| `export_presets.cfg` | build settings for the web, Linux and Windows versions |
| `.github/workflows/pages.yml` | builds the web version and publishes it on GitHub Pages and itch.io |
| `tools/export.sh` | builds and zips all three versions (see below) |
| `tools/sim.py` | Python model of the same rules and CPU, used to tune `config.gd` |

## Sharing the game: browser, Linux, Windows

**GitHub Pages (automatic).** Every push to `master` builds the web version on
GitHub Actions with Godot 4.7.2 (`.github/workflows/pages.yml`) and publishes it
at https://totopoloco.github.io/badminton-game/ about a minute later; the run is
under the repository's *Actions* tab. One-time setup on GitHub: *Settings →
Pages → Build and deployment → Source: GitHub Actions*.

**By hand.** `tools/export.sh` builds three versions and zips each one in the
`dist` folder next to the project folder (`../dist`):

| Zip | What's inside |
|---|---|
| `badminton-web.zip` | the browser version (WebAssembly + WebGL 2): upload it to itch.io or any web host |
| `badminton-linux.zip` | `badminton.x86_64`, a single file |
| `badminton-windows.zip` | `Badminton.exe`, a single file (built on Linux, no Windows needed) |

Once, install Godot's export templates (about 1.3 GB): in the editor
*Editor → Manage Export Templates → Download and Install*, or
`bash tools/export.sh templates`. Then:

    bash tools/export.sh               # all three (or name them: web linux windows)
    bash tools/export.sh serve         # play the web build at http://localhost:8000

The script uses `~/Downloads/Godot/Godot_v4.7.2-stable_linux.x86_64`; set
`GODOT=/path/to/godot` for another binary. The same presets are under
*Project → Export* in the editor.

**In the browser.** The web build is single-threaded (Godot's default since 4.3),
so it needs no special server headers and works on any static host: itch.io,
GitHub Pages, Netlify. Players need a desktop browser and a keyboard or gamepad
(there are no touch controls), and they click the game once so it has the
keyboard.
Opening `index.html` straight from disk doesn't work; it has to be served,
which is what `serve` does. F11 is the browser's own key there; on itch.io use
the page's fullscreen button.

**On itch.io (automatic after a one-time setup).** The workflow's *itch* job
uploads every web build to an itch.io page with butler, itch.io's upload tool,
on the channel `html5`:

1. On itch.io, *Dashboard → Create new project*: title *Badminton*, *Kind of
   project: HTML*, and under *Embed options* a viewport of 960 × 540 with
   *Fullscreen button* on and *Mobile friendly* off. Save it as a draft; it
   needs no upload.
2. On GitHub, *Settings → Secrets and variables → Actions*: a repository secret
   `ITCH_IO_SECRET` holding an itch.io API key (*itch.io → Settings → API
   keys*), and on the *Variables* tab a variable `ITCH_GAME` with the page's
   `user/project`, for example `yourname/badminton`.
3. Push. When the *itch* job has finished, open *Edit game* on itch.io, tick
   *This file will be played in the browser* for the `html5` upload, save, and
   make the page public when you like. Later pushes replace that upload.

Without `ITCH_GAME` the job is skipped. The Linux and Windows zips can go on
the same page as downloads; Windows shows a SmartScreen warning for unsigned
games (*More info → Run anyway*).

**Godot's license.** Godot is MIT licensed, free also for commercial games; it
asks that its notice ships with the game. Exported builds print it at startup
(the browser console counts) and every zip has `GODOT_LICENSES.txt`, the
notice plus Godot's third-party components, written by
`-- --licenses=FILE`. Everything else in the game (art, sounds, font) was made
for it.

## License

MIT, see `LICENSE`. Godot Engine is MIT licensed too (see *Godot's license* above).
