#!/bin/bash
# release.sh NAME [--from STEP] [--list]: a release of the launcher, from the build to the installer and its update
# feed on GitHub (release/README.md). NAME is the build's name, letters and digits (v050): the runner's build keeps
# every part under it in the work folder (bundle-NAME, game-NAME, runner-NAME, mod-cg-NAME), and <work>/release/NAME
# holds every step's log, the record of the run, the player copy, the installer's folder and Velopack's releases.
#   STACK=A|B          the server stack the release is for: its address is read from the service's
#                      deploy/fly/stacks.py (a checkout beside the runner's, the runner's pins.tsv REPO_SERVICE) and
#                      built into the launcher as its official server. Named, never assumed
#   KIND=public        the players' build (default); KIND=test makes a test build (its launcher says TEST BUILD)
#   CHANNEL=beta       Velopack's channel (default beta, the owner's for 0.5.0): the feed is releases.CHANNEL.json
#   PROFILE, VCRT, PORT_PYTHON, PORT_AGENT   as the runner's port/build/build.sh and package.sh take them (PORT_PYTHON:
#                      a Windows python.exe with keystone, for the image: the build is the runner's CMake superbuild)
#   FIRST_RELEASE=1    there is no earlier release on GitHub to make deltas from: the step "previous" downloads nothing
#   SIGN=azure         sign the launcher's programs and Setup.exe while packing (Azure Artifact Signing): OFF by default,
#                      and refused until the placeholders below are filled in (the owner, 2026-10-25: signing comes
#                      with the company). Without it nothing is signed, and Windows' SmartScreen warns at Setup
#   RELEASE=1          really upload to GitHub. Without it the step "upload" only prints what it would run. Never set
#                      it in an agent's run: the owner publishes
#   --from STEP        go on at a step (its id, as --list prints them) after a run that stopped
#   --list             the steps and nothing else
# It refuses to start when the trees are not what it builds: the runner's or the launcher's checkout with changes
# not committed, a NAME begun at other commits, a NAME begun and no --from. Before each step it looks again. It stops
# at the first step that fails, with its log and the command that goes on.
# The installer is made from the player copy package.sh checked (no game data, no name, no link, the stack built in):
# the launcher's folder becomes the installed folder's top, recomp/ and source/ beside it, and the copy's marker is
# replaced by the installed one (Launcher.Core Install.cs: an installed launcher keeps its data in the player's own
# folder, as Velopack replaces the program's folder whole at every update).
# Packing for Windows from WSL uses vpk's cross-packing directive, "[win]".
set -uo pipefail
gates=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO_URL=https://github.com/piconet-live/piconet-launcher
TOKEN_FILE=$HOME/.config/fzgx/github-token
PACK_ID=Piconet.Launcher                 # the install folder %LOCALAPPDATA%\Piconet.Launcher; Branding.AppId, the taskbar's id
MAIN_EXE=Launcher.App.exe                # the launcher's own host file, at the installed folder's top
CHANNEL=${CHANNEL:-beta}
KIND=${KIND:-public}

# ---- signing: OFF unless SIGN=azure, and refused until these are filled in (release/README.md, "Signing") --------
# Azure Artifact Signing (formerly Trusted Signing), through the .NET Foundation's `sign` tool, which runs on Linux:
#   dotnet tool install -g sign --prerelease
# vpk runs SIGN_TEMPLATE once for a batch of files, with {{file}} replaced by their paths. The account, the
# certificate profile and the endpoint come from the Azure portal once the company's identity is validated; the
# login is the Azure CLI's (az login) or a service principal's environment (AZURE_TENANT_ID, AZURE_CLIENT_ID,
# AZURE_CLIENT_SECRET). Check the `sign` tool's current subcommand name before the first signed release.
AZURE_SIGN_ENDPOINT=${AZURE_SIGN_ENDPOINT:-PLACEHOLDER-https://REGION.codesigning.azure.net}
AZURE_SIGN_ACCOUNT=${AZURE_SIGN_ACCOUNT:-PLACEHOLDER-account-name}
AZURE_SIGN_PROFILE=${AZURE_SIGN_PROFILE:-PLACEHOLDER-certificate-profile}
SIGN_TEMPLATE=${SIGN_TEMPLATE:-sign code artifact-signing --artifact-signing-endpoint $AZURE_SIGN_ENDPOINT --artifact-signing-account $AZURE_SIGN_ACCOUNT --artifact-signing-certificate-profile $AZURE_SIGN_PROFILE --timestamp-url http://timestamp.acs.microsoft.com {{file}}}
# -------------------------------------------------------------------------------------------------------------------

STEPS='build|The game build (runner build.sh)
package|Player copy, made for the stack
installer|Installer folder
previous|Previous release, for deltas
pack|Velopack pack
upload|Upload to GitHub (RELEASE=1 only)'

NAME=""; FROM=""; LIST=""
while [ $# -gt 0 ]; do case "$1" in
  --from) FROM=${2:?--from STEP}; shift;; --list) LIST=1;; -*) echo "release: unknown option $1" >&2; exit 2;; *) NAME=$1;; esac; shift; done
IDS=(); declare -A TITLE
while IFS='|' read -r id title; do IDS+=("$id"); TITLE[$id]=$title; done <<< "$STEPS"
m=${#IDS[@]}
if [ -n "$LIST" ]; then n=0; for id in "${IDS[@]}"; do n=$((n + 1)); printf '%2d  %-10s %s\n' $n "$id" "${TITLE[$id]}"; done; exit 0; fi
[ -n "$NAME" ] || { sed -n 2,30p "$0"; exit 2; }
# the runner these gates are checked out in (their pins.tsv REPO_RUNNER), with its lib.sh: root, the work folder
. "$gates/runner.sh" || exit 1
W=${PORT_WORK:-$PORT_WORK_DEFAULT}
pin() { awk -F'\t' -v n="$1" '$1 == n { print $2; f = 1 } END { exit !f }' "$root/port/setup/pins.tsv"; }
service=$(cd "$root/$(pin REPO_SERVICE)" 2> /dev/null && pwd) || { echo "release: no service checkout at the runner's REPO_SERVICE ($(pin REPO_SERVICE))" >&2; exit 1; }
launcher=$(cd "$root/$(pin REPO_LAUNCHER)" 2> /dev/null && pwd) || { echo "release: no launcher checkout at the runner's REPO_LAUNCHER ($(pin REPO_LAUNCHER))" >&2; exit 1; }

[[ $NAME =~ ^[A-Za-z0-9]+$ ]] || { echo "release: NAME is letters and digits" >&2; exit 2; }
[ -z "$FROM" ] || [[ " ${IDS[*]} " == *" $FROM "* ]] || { echo "release: no step $FROM (the steps: ${IDS[*]})" >&2; exit 2; }
refuse() { echo "release: REFUSED: $1" >&2; exit 1; }
: "${STACK:?release: name the server stack the release is for, STACK=A or STACK=B (deploy/fly/OPERATIONS.md in piconet-service)}"
[[ $KIND =~ ^(test|public)$ ]] || refuse "KIND is test or public"
[[ $CHANNEL =~ ^[a-z0-9-]+$ ]] || refuse "CHANNEL is lower-case letters, digits and '-'"
case "${SIGN:-}" in ""|azure) ;; *) refuse "SIGN is azure or unset (unsigned)";; esac
[ "${RELEASE:-}" != 1 ] || [ "$KIND" = public ] || refuse "RELEASE=1 with KIND=$KIND: the feed is the players' own; a test build is never uploaded to it"
if [ "${SIGN:-}" = azure ] && [[ "$SIGN_TEMPLATE" == *PLACEHOLDER* ]]; then
  refuse "SIGN=azure with placeholders: set AZURE_SIGN_ENDPOINT, AZURE_SIGN_ACCOUNT and AZURE_SIGN_PROFILE (or SIGN_TEMPLATE) first (release/README.md, \"Signing\")"
fi
STACK_ADDRESS=$(python3 "$service/deploy/fly/stacks.py" address "$STACK") || refuse "no server stack $STACK ($service/deploy/fly/stacks.tsv)"
# vpk is a global .NET tool: in a shell that names neither its folder nor DOTNET_ROOT (WSL's non-interactive
# shells, an agent's) it is not found, or found and unable to start ("You must install .NET to run this
# application", status 131): both from the dotnet on PATH, as `dotnet tool install -g` put them
command -v vpk > /dev/null || [ ! -x "$HOME/.dotnet/tools/vpk" ] || PATH=$PATH:$HOME/.dotnet/tools
[ -n "${DOTNET_ROOT:-}" ] || ! command -v dotnet > /dev/null || export DOTNET_ROOT=$(dirname "$(readlink -f "$(command -v dotnet)")")
command -v vpk > /dev/null || refuse "no vpk on PATH: dotnet tool install -g vpk --version $(sed -n 's/.*Include="Velopack" Version="\([^"]*\)".*/\1/p' "$launcher/net/Directory.Packages.props")"
want=$(sed -n 's/.*Include="Velopack" Version="\([^"]*\)".*/\1/p' "$launcher/net/Directory.Packages.props")
have=$(dotnet tool list -g 2> /dev/null | awk '$1 == "vpk" { print $2 }')
[ -z "$have" ] || [ "$have" = "$want" ] || refuse "vpk $have, and the launcher uses Velopack $want: dotnet tool update -g vpk --version $want"

# ---- the trees are what the run builds
tree() {   # DIR: its commit, or why it is not one commit's files
  local changed; changed=$(git -C "$1" status --porcelain | head -1)
  [ -z "$changed" ] || { echo "$1 has changes that are not committed (${changed:3}): a release is one commit's"; return 1; }
  git -C "$1" rev-parse HEAD
}
runner_commit=$(tree "$root") || refuse "$runner_commit"
launcher_commit=$(tree "$launcher") || refuse "$launcher_commit"
commits="runner $runner_commit launcher $launcher_commit stack $STACK $KIND channel $CHANNEL"
OUT=$W/release/$NAME
if [ -f "$OUT/commits" ]; then
  [ "$(cat "$OUT/commits")" = "$commits" ] || refuse "release $NAME was begun as \"$(cat "$OUT/commits")\" and this is \"$commits\": check those out, or take another name"
  [ -n "$FROM" ] || refuse "release $NAME was begun already ($OUT): go on with --from STEP, or take another name"
  for id in "${IDS[@]}"; do
    [ "$id" != "$FROM" ] || break
    [ "$(awk -F'\t' -v s="$id" '$1 == s && $2 != "began" { r = $2 } END { print r }' "$OUT/steps.tsv" 2> /dev/null)" = 0 ] ||
      refuse "step $id of release $NAME has not ended well, so the run cannot go on after it: --from $id"
  done
elif [ -n "$FROM" ]; then refuse "release $NAME was never begun (no $OUT/commits): start it without --from"; fi
mkdir -p "$OUT/logs" && echo "$commits" > "$OUT/commits" || refuse "cannot write $OUT"

# ---- the steps (each runs in a shell of its own, from the runner's root, with set -euo pipefail)
export PORT_WORK=$W PORT_AGENT=${PORT_AGENT:-release}
COPIES=$OUT/copy; PACK=$OUT/installer; FEED=$OUT/releases
copy_folder() {   # the player copy's folder package.sh made: the one folder in COPIES/dist
  local found; found=$(find "$COPIES/dist" -mindepth 1 -maxdepth 1 -type d 2> /dev/null)
  [ -n "$found" ] && [ "$(wc -l <<< "$found")" = 1 ] || { echo "release: $COPIES/dist holds no one copy's folder" >&2; return 1; }
  echo "$found"
}
said() { sed -n "s/.*const string $1 = \"\([^\"]*\)\".*/\1/p" "$launcher/net/src/Launcher.Core/Files/Install.cs"; }
version() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$PACK/source/package-manifest.json"; }

step_build() { port/build/build.sh "$NAME"; }
step_package() {
  STACK=$STACK STACK_ADDRESS=$STACK_ADDRESS KIND=$KIND RUNNER=$W/port/runner-$NAME/moderngekko-run.exe RUNNER_COMMIT=${runner_commit:0:12} \
    MODULE=cg-$NAME BUNDLE=$W/port/bundle-$NAME SYS=$W/ModernGekko/build/Sys SYS_SOURCE=$W/ModernGekko/vendor/dolphin \
    VCRT=${VCRT:-/mnt/c/Windows/System32} COPIES=$COPIES REPLACE=1 port/build/package.sh
}
step_installer() {   # the checked copy, laid out as the installed folder: app/* at the top, recomp/ and source/ beside
  local copy folder marker installed; copy=$(copy_folder)
  folder=$(said ProgramFolder); marker=$(said MarkerName); installed=$(said InstalledMarkerName)
  [ -n "$folder" ] && [ -n "$marker" ] && [ -n "$installed" ] || { echo "release: Install.cs names no ProgramFolder, MarkerName or InstalledMarkerName" >&2; return 1; }
  [ -f "$copy/$folder/$MAIN_EXE" ] && [ -f "$copy/$folder/$marker" ] && [ -d "$copy/recomp" ] && [ -f "$copy/source/package-manifest.json" ] ||
    { echo "release: $copy is not a player copy of this layout ($folder/$MAIN_EXE, $folder/$marker, recomp/, source/)" >&2; return 1; }
  [ ! -e "$copy/data" ] || { echo "release: $copy has a data folder: a copy that was run is no release" >&2; return 1; }
  rm -rf "$PACK"; mkdir -p "$PACK"
  cp -a "$copy/$folder/." "$PACK/"
  for part in recomp source; do [ ! -e "$PACK/$part" ] || { echo "release: the launcher's folder has a $part of its own" >&2; return 1; }; cp -a "$copy/$part" "$PACK/$part"; done
  rm "$PACK/$marker"
  printf 'This file marks the folder as an installed launcher: it keeps its data in your own folder (%%LOCALAPPDATA%%\\fzgx-launcher),\r\nas every update replaces this folder. Leave the file here.\r\n' > "$PACK/$installed"
  [ -z "$(find "$PACK" -type l | head -1)" ] || { echo "release: a link in $PACK" >&2; return 1; }
  echo "installer folder: $PACK (version $(version), $(find "$PACK" -type f | wc -l) files)"
}
step_previous() {   # the newest release's full package, so that vpk pack makes a delta from it
  mkdir -p "$FEED"
  local token=(); [ ! -f "$TOKEN_FILE" ] || token=(--token "$(cat "$TOKEN_FILE")")
  if [ -n "${FIRST_RELEASE:-}" ]; then echo "previous: FIRST_RELEASE=1: no earlier release, no delta"; return 0; fi
  vpk "[win]" download github --repoUrl "$REPO_URL" --channel "$CHANNEL" --outputDir "$FEED" "${token[@]}"
}
step_pack() {
  local sign=(); [ "${SIGN:-}" != azure ] || sign=(--signTemplate "$SIGN_TEMPLATE")
  [ "${SIGN:-}" = azure ] || echo "pack: unsigned (SIGN=azure signs; release/README.md, \"Signing\")"
  vpk "[win]" pack --packId "$PACK_ID" --packVersion "$(version)" --packDir "$PACK" --mainExe "$MAIN_EXE" \
    --packTitle "Piconet Launcher" --packAuthors "Piconet" --icon "$launcher/net/src/Launcher.App/Assets/Icon/app.ico" \
    --splashImage "$gates/release/splash.png" \
    --channel "$CHANNEL" --aumid "$PACK_ID" --noPortable --outputDir "$FEED" "${sign[@]}"
  ls -la "$FEED"
}
step_upload() {   # a published release, not a draft and NOT a pre-release: the launcher reads the "latest release"
  # download link (Branding.UpdateFeed), which GitHub gives only for the newest release that is neither
  local v; v=$(version)
  local plan=(vpk "[win]" upload github --repoUrl "$REPO_URL" --channel "$CHANNEL" --outputDir "$FEED" --publish
              --releaseName "Piconet $v" --tag "v$v" --targetCommitish "$launcher_commit")
  if [ "${RELEASE:-}" != 1 ]; then
    echo "upload: NOT run (RELEASE=1 runs it). It would run, with the token from $TOKEN_FILE:"
    printf '  %q' "${plan[@]}" --token '<token>'; echo
    return 0
  fi
  [ -f "$TOKEN_FILE" ] || { echo "release: no token at $TOKEN_FILE" >&2; return 1; }
  "${plan[@]}" --token "$(cat "$TOKEN_FILE")"
}

# ---- the run
echo "release $NAME: runner ${runner_commit:0:8}, launcher ${launcher_commit:0:8}, stack $STACK ($KIND, $STACK_ADDRESS), channel $CHANNEL; logs in $OUT/logs"
started=""; [ -n "$FROM" ] || started=1
n=0
for id in "${IDS[@]}"; do
  n=$((n + 1))
  [ "$id" != "$FROM" ] || started=1
  if [ -z "$started" ]; then echo "== step $n of $m: ${TITLE[$id]}: done earlier"; continue; fi
  log=$OUT/logs/$(printf %02d $n)-$id.log
  for t in "$root" "$launcher"; do now=$(tree "$t") || { echo "release: STOPPED before step $n, ${TITLE[$id]}: $now" | tee "$log" >&2; exit 1; }; done
  [ "$(tree "$root")" = "$runner_commit" ] && [ "$(tree "$launcher")" = "$launcher_commit" ] ||
    { echo "release: STOPPED before step $n, ${TITLE[$id]}: a checkout moved since the run began" | tee "$log" >&2; exit 1; }
  echo "== $(date +%T) step $n of $m: ${TITLE[$id]}; log $log"
  printf '%s\tbegan\t\t%s\n' "$id" "$(date +%FT%T%z)" >> "$OUT/steps.tsv"
  t0=$(date +%s)
  # (the step is a plain command of its subshell: in a list of && the shell would not stop at a failing line)
  ( cd "$root" || exit 1; set -euo pipefail; "step_$id" ) > "$log" 2>&1 < /dev/null; status=$?
  printf '%s\t%s\t%s\t%s\n' "$id" "$status" "$(( $(date +%s) - t0 ))" "$(date +%FT%T%z)" >> "$OUT/steps.tsv"
  if [ $status != 0 ]; then
    echo "release: STOPPED at step $n of $m, ${TITLE[$id]} (status $status). Its log: $log" >&2
    tail -5 "$log" | cut -c1-240 | sed 's/^/    /' >&2
    echo "release: again from there: STACK=$STACK${KIND:+ KIND=$KIND} CHANNEL=$CHANNEL $0 $NAME --from $id" >&2
    exit $status
  fi
  [ "$id" != upload ] || cat "$log"
done
echo "release $NAME: done. The installer and the feed: $FEED (the installer is the *-Setup.exe there)"
[ "${RELEASE:-}" = 1 ] || echo "release $NAME: nothing was uploaded (RELEASE=1 does it, on the owner's word)"
