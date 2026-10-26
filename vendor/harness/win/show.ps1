# show.ps1 -Id PID [-Label TEXT] [-Title TEXT]: restore, maximize and raise the runner's render window (the one whose
# title holds -Title) and keep -Label at the front of its title, so a visible run always says what it is.
# Lifted from the first project's show.ps1; the title text is a parameter.
param([int]$Id, [string]$Label = "", [string]$Title = "ModernGekko")
Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices; using System.Collections.Generic;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern bool SetWindowText(IntPtr h, string s);
  public static List<IntPtr> Find(uint want, string title) {
    var r = new List<IntPtr>();
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p);
      if (p == want) { var sb = new StringBuilder(256); GetWindowText(h, sb, 256);
        if (sb.ToString().Contains(title)) r.Add(h); } return true; }, IntPtr.Zero);
    return r; } }
"@
for ($i = 0; $i -lt 60; $i++) {
  $hs = [W]::Find([uint32]$Id, $Title)
  if ($hs.Count -gt 0) {
    foreach ($h in $hs) { [W]::ShowWindow($h, 9) | Out-Null; [W]::ShowWindow($h, 3) | Out-Null; [W]::SetForegroundWindow($h) | Out-Null }
    "shown $($hs.Count)"
    if ($Label) {
      # keep the label in front of whatever the runner writes (it updates the title with the FPS)
      while (Get-Process -Id $Id -ErrorAction SilentlyContinue) {
        foreach ($h in [W]::Find([uint32]$Id, $Title)) {
          $sb = New-Object System.Text.StringBuilder 256; [W]::GetWindowText($h, $sb, 256) | Out-Null
          $t = $sb.ToString(); if (-not $t.StartsWith($Label)) { [W]::SetWindowText($h, "$Label  " + $t.Substring([Math]::Max(0, $t.IndexOf($Title)))) | Out-Null }
        }
        Start-Sleep -Milliseconds 1000
      }
    }
    exit 0 }
  Start-Sleep -Milliseconds 500
}
"not found"
