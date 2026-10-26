#!/usr/bin/env bash
# room-for-games.sh GAMES: has Windows the memory left to start GAMES games now? Asked by every script that starts
# a game for a test, right before the start, so that a run is refused with a plain sentence instead of taking the
# PC down.
#   why=$(port/gates/room-for-games.sh 3) || { echo "RUN: not started: $why"; exit 3; }
# Status 0 and no word: there is room. Status 1 and one sentence on standard output: there is not, or Windows did
# not say (no game is started blind). On a PC without powershell.exe (not Windows): status 0, nothing to ask.
#
# What is read is Windows' free commit: the memory it can still promise to programs (Win32_OperatingSystem's
# FreeVirtualMemory, in KB; about 0.6 s). It is not the free RAM. Without a page file the whole of it is the PC's
# RAM, and WSL's machine holds up to its cap of it, page cache included, and gives it back slowly. When it runs
# out, Windows ends whatever asks next: on 2026-10-11, with WSL at its 32 GB and under 7 GB left, the graphics
# driver failed and a game crashed (15:01), after five warnings that day.
#
# The figures: a game commits about 1.5 GB, and 2.5 GB stays free once the games are up:
#   wanted = GAMES x 1.5 GB + 2.5 GB      (one game 4 GB, two 5.5 GB, a set of three 7 GB)
# What this cannot see: memory WSL takes after the games have started (a build or a check that fills its page
# cache). The figures hold a start off; they do not make a later squeeze impossible.
set -u
games=${1:-}
case "$games" in ''|*[!0-9]*|0) echo "room-for-games: usage: room-for-games.sh GAMES (a count: 1, 2, 3)" >&2; exit 2;; esac
command -v powershell.exe > /dev/null 2>&1 || exit 0
GAME_KB=$((1536 * 1024)); KEPT_KB=$((2560 * 1024))
free=$(timeout 20 powershell.exe -NoProfile -Command '(Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory' < /dev/null 2> /dev/null | tr -d '\r\n ')
case "$free" in ''|*[!0-9]*)
  echo "Windows did not say how much memory it has left (powershell.exe, FreeVirtualMemory, answered \"$(printf %s "$free" | cut -c1-40)\"), and no game is started blind: start again"
  exit 1;;
esac
want=$((games * GAME_KB + KEPT_KB))
[ "$free" -lt "$want" ] || exit 0
gb() { local t=$(($1 * 10 / 1048576)); echo "$((t / 10)).$((t % 10))"; }   # rounded down: 6.99 is not "7.0 of 7.0"
[ "$games" = 1 ] && n="one game needs" || n="$games games need"
echo "Windows has $(gb "$free") GB of memory left to hand out, and $n $(gb "$want") GB (1.5 GB a game, and 2.5 GB that stays free; port/gates/room-for-games.sh): close something, or wait until WSL has given memory back, and start again"
exit 1
