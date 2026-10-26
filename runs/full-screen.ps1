# full-screen.ps1 -Launcher PID [-After SECONDS] [-X N -Y N]: the window of the game a test's launcher started goes
# to full screen, by the window's own command (WM_COMMAND 41004, "full screen and back": what its strip's button and
# F11 send; no key, no mouse, and the window is not brought to the front). mixed-run.sh's FULL calls this. Waits up
# to a minute for the game's window, moves it to X,Y first when given (the monitor that point is on is the one
# taken), waits SECONDS (30) from the window's coming, sends the command once, and says what it did and where the
# window is. It starts and ends nothing.
param([int]$Launcher, [int]$After = 30, [int]$X = -99999, [int]$Y = 0)
Add-Type @"
using System; using System.Collections.Generic; using System.Runtime.InteropServices;
public static class FullScreen {
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
  delegate bool Each(IntPtr window, IntPtr more);
  [DllImport("user32.dll")] static extern bool EnumWindows(Each each, IntPtr more);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
  [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr window, uint which);
  [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr window, out Rect rect);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr window, uint message, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int width, int height, uint flags);
  [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
  public static void SeeRealPixels() { SetThreadDpiAwarenessContext((IntPtr)(-4)); }
  public static string Place(IntPtr window) {
    Rect r; GetWindowRect(window, out r);
    return string.Format("{0} x {1} at {2},{3}", r.Right - r.Left, r.Bottom - r.Top, r.Left, r.Top);
  }
  // The process's first visible top-level window that no other window owns.
  public static IntPtr Top(uint process) {
    IntPtr found = IntPtr.Zero;
    EnumWindows(delegate(IntPtr window, IntPtr more) {
      uint of; GetWindowThreadProcessId(window, out of);
      if (found == IntPtr.Zero && of == process && IsWindowVisible(window) && GetWindow(window, 4) == IntPtr.Zero) found = window;
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@
[FullScreen]::SeeRealPixels()
$window = [IntPtr]::Zero; $game = 0
for ($i = 0; $i -lt 200 -and $window -eq [IntPtr]::Zero; $i++) {
  foreach ($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$Launcher and Name='moderngekko-run.exe'")) {
    $its = [FullScreen]::Top($child.ProcessId)
    if ($its -ne [IntPtr]::Zero) { $window = $its; $game = $child.ProcessId }
  }
  if ($window -eq [IntPtr]::Zero) { Start-Sleep -Milliseconds 300 }
}
if ($window -eq [IntPtr]::Zero) { "full screen: no game window of launcher $Launcher came in a minute: nothing sent"; exit 1 }
"full screen: the game's window (process $game) is there: $([FullScreen]::Place($window))"
if ($X -ne -99999) {
  # (moved, not sized, not brought forward: 0x0015 is no size, no order, no activation)
  [FullScreen]::SetWindowPos($window, [IntPtr]::Zero, $X, $Y, 0, 0, 0x0015) | Out-Null
  Start-Sleep -Milliseconds 500
  "full screen: moved: $([FullScreen]::Place($window))"
}
Start-Sleep -Seconds $After
if (-not (Get-Process -Id $game -ErrorAction SilentlyContinue)) { "full screen: the game had gone after $After s: nothing sent"; exit 1 }
[FullScreen]::PostMessage($window, 0x0111, [IntPtr]41004, [IntPtr]::Zero) | Out-Null
Start-Sleep -Seconds 3
"full screen: the command was sent after $After s; the window is now $([FullScreen]::Place($window))"
