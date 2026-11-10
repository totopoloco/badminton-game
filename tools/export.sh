#!/usr/bin/env bash
# Builds Badminton for the browser, Linux and Windows and zips each build in
# ~/badminton/dist (next to the project folder):
#
#   badminton-web.zip      the browser version: upload it to itch.io as an HTML game
#   badminton-linux.zip    badminton.x86_64, one file
#   badminton-windows.zip  Badminton.exe, one file
#
# Usage:
#   tools/export.sh                 build all three
#   tools/export.sh web linux       build only the ones named (web, linux, windows)
#   tools/export.sh serve           play the web build at http://localhost:8000
#   tools/export.sh templates       download Godot's export templates (about 1.3 GB, once)
#
# Uses ~/Downloads/Godot/Godot_v4.7.2-stable_linux.x86_64; set GODOT=/path/to/godot
# to use another Godot binary.
set -euo pipefail

game="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dist="$(dirname "$game")/dist"
godot="${GODOT:-$HOME/Downloads/Godot/Godot_v4.7.2-stable_linux.x86_64}"
port=8000

die() { echo "export.sh: $*" >&2; exit 1; }

serve() {
	[ -f "$dist/web/index.html" ] || die "there is no web build yet; run: bash $0 web"
	echo "Play at http://localhost:$port  (Ctrl+C stops the server)"
	python3 - "$dist/web" "$port" <<'EOF'
import functools, http.server, sys
handler = http.server.SimpleHTTPRequestHandler
handler.extensions_map[".wasm"] = "application/wasm"   # older Pythons don't know it
http.server.test(functools.partial(handler, directory=sys.argv[1]), port=int(sys.argv[2]), bind="127.0.0.1")
EOF
}

[ "${1:-}" = serve ] && { serve; exit; }

[ -x "$godot" ] || die "no Godot binary at $godot (set GODOT=/path/to/godot)"
# "4.7.2.stable.official.abc1234" -> "4.7.2.stable", the name of the templates folder
version="$("$godot" --version | sed -nE '1s/^([0-9]+(\.[0-9]+)+\.[a-z]+[0-9]*)\..*$/\1/p')"
[ -n "$version" ] || die "could not read the version of $godot"
templates="${XDG_DATA_HOME:-$HOME/.local/share}/godot/export_templates/$version"

install_templates() {
	local tag="${version%.*}-${version##*.}"                  # 4.7.2.stable -> 4.7.2-stable
	local url="https://github.com/godotengine/godot/releases/download/$tag/Godot_v${tag}_export_templates.tpz"
	local tmp
	mkdir -p "$(dirname "$templates")"
	tmp="$(mktemp -d "$(dirname "$templates")/.download.XXXXXX")"   # same disk: no big copy
	# shellcheck disable=SC2064  # expand now: tmp is local to this function
	trap "rm -rf '$tmp'" EXIT
	echo "Downloading $url (about 1.3 GB)"
	curl -fL --progress-bar -o "$tmp/templates.tpz" "$url" || wget -O "$tmp/templates.tpz" "$url"
	python3 -m zipfile -e "$tmp/templates.tpz" "$tmp"
	rm -rf "$templates"
	mv "$tmp/templates" "$templates"
	echo "Export templates installed in $templates"
}

[ "${1:-}" = templates ] && { install_templates; exit; }

targets=("$@")
[ ${#targets[@]} -gt 0 ] || targets=(web linux windows)
for t in "${targets[@]}"; do
	case "$t" in
		web | linux | windows) ;;
		*) die "unknown build '$t' (use web, linux, windows, serve or templates)" ;;
	esac
done

[ -f "$templates/version.txt" ] || die "Godot's export templates for $version are not installed.
  Install them once, either in the editor (Editor > Manage Export Templates >
  Download and Install) or with: bash $0 templates"

mkdir -p "$dist"
# Godot's license and its third-party notices, shipped in every zip
"$godot" --headless --path "$game" -- --licenses="$dist/GODOT_LICENSES.txt"
[ -s "$dist/GODOT_LICENSES.txt" ] || die "could not write $dist/GODOT_LICENSES.txt"

build() {    # preset name, output file, zip name
	local folder
	folder="$(dirname "$2")"
	rm -rf "$folder"
	mkdir -p "$folder"
	echo "== $1 -> $2"
	"$godot" --headless --path "$game" --export-release "$1" "$2"
	[ -s "$2" ] || die "the $1 export failed (see Godot's messages above)"
	rm -f "$dist/$3"
	python3 -m zipfile -c "$dist/$3" "$folder/." "$dist/GODOT_LICENSES.txt"
	echo "   $dist/$3"
}

for t in "${targets[@]}"; do
	case "$t" in
		web) build "Web" "$dist/web/index.html" badminton-web.zip ;;
		linux) build "Linux" "$dist/linux/badminton.x86_64" badminton-linux.zip ;;
		windows) build "Windows Desktop" "$dist/windows/Badminton.exe" badminton-windows.zip ;;
	esac
done
echo "Done. Try the web build with: bash $0 serve"
