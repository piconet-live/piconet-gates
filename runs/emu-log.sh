# emu-log.sh (sourced): a test game writes the emulator's own log to a file, with the game's own report lines and
# the video backend's. The game prints "GP WAIT Timeout... (sending object a/b)" when its one-second wait for the
# graphics processor runs out (the reset of the port-recomp notes 5.19): the line says how far the graphics side
# got, and was lost while the log was off.
#   emu_log_on DATA     writes DATA/recomp-user/Config/Logger.ini (the game's user folder, before the game starts)
#   emu_log_keep DATA RUN   copies DATA/recomp-user/Logs/dolphin.log to RUN/dolphin.log (after the game)
# EMU_LOG=0: neither (the emulator's default: no log file).
emu_log_on() {
  [ "${EMU_LOG:-1}" != 0 ] || return 0
  mkdir -p "$1/recomp-user/Config"; rm -f "$1/recomp-user/Logs/dolphin.log"
  printf '[Logs]\nVideo = True\nOSREPORT = True\nOSREPORT_HLE = True\n[Options]\nVerbosity = 3\nWriteToFile = True\nWriteToConsole = False\nWriteToWindow = False\n' \
    > "$1/recomp-user/Config/Logger.ini"
}
emu_log_keep() { [ "${EMU_LOG:-1}" = 0 ] || cp "$1/recomp-user/Logs/dolphin.log" "$2/dolphin.log" 2> /dev/null || true; }
