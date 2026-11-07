"""Block / restore internet for BlueStacks only — like pulling the network
cable just for the emulator, without touching the rest of the machine's
connection (your browser, Claude, etc. keep working).

Why Windows Firewall and not ADB: on this BlueStacks image (Android Pie, single
``eth0`` user-mode/slirp NAT, no root) the in-guest ADB tricks don't cut the
game's traffic — ``airplane-mode`` flips the flag but ``eth0`` stays up,
``svc wifi/data`` is irrelevant (there is no ``wlan0`` / mobile), and
``ip link set eth0 down`` needs root AND kills the ADB transport itself. A
per-process firewall Block rule on the BlueStacks executables *does* cut the
guest's real TCP (verified) while leaving the host online and ADB (loopback)
alive. Note: ICMP ``ping`` from the guest still answers under slirp even when
blocked, so it's a misleading test — the game's TCP is what actually drops.

  * "block"   -> add outbound+inbound *Block* rules for every BlueStacks
                 executable we can find (running processes + install dirs);
  * "unblock" -> remove those rules again.

All rules share one firewall Group so we can wipe them in a single call. The
operations require administrator rights:

  * if the GUI already runs elevated, the command runs silently;
  * otherwise we relaunch it elevated through a UAC prompt (one per toggle).
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile

# Single firewall group so every rule we create can be removed at once.
_RULE_GROUP = "MMBotBlueStacks"

# PowerShell that discovers the BlueStacks executables and adds block rules.
# {group} is filled in by block_bluestacks().
_BLOCK_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$names = @('HD-Player','BlueStacks','BlueStacksX','HD-Agent','BstkSVC',
           'HD-MultiInstanceManager','BstkVMU')
$paths = New-Object System.Collections.Generic.List[string]
# Paths of the currently running BlueStacks processes (HD-Player carries the
# guest's NAT traffic, so it is the one that matters most).
foreach ($p in Get-Process -ErrorAction SilentlyContinue) {
  if ($names -contains $p.Name) {
    try { if ($p.Path) { $paths.Add($p.Path) } } catch {}
  }
}
# Plus the well-known install locations, so it works even before launch.
$dirs = @("$env:ProgramFiles\BlueStacks_nxt", "$env:ProgramFiles\BlueStacks",
          "${env:ProgramFiles(x86)}\BlueStacks_nxt",
          "${env:ProgramFiles(x86)}\BlueStacks")
foreach ($d in $dirs) {
  if ($d -and (Test-Path $d)) {
    foreach ($n in @('HD-Player.exe','BlueStacks.exe','HD-Agent.exe','BstkSVC.exe')) {
      $exe = Join-Path $d $n
      if (Test-Path $exe) { $paths.Add($exe) }
    }
  }
}
$paths = $paths | Sort-Object -Unique
if ($paths.Count -eq 0) {
  Write-Error 'BlueStacks nije pronadjen (nije instaliran ili nije pokrenut).'
  exit 1
}
# Start clean so we never stack duplicate rules.
Remove-NetFirewallRule -Group '{group}' -ErrorAction SilentlyContinue
foreach ($path in $paths) {
  New-NetFirewallRule -DisplayName 'MM Bot blok BlueStacks (out)' -Group '{group}' `
    -Direction Outbound -Program $path -Action Block -Profile Any | Out-Null
  New-NetFirewallRule -DisplayName 'MM Bot blok BlueStacks (in)' -Group '{group}' `
    -Direction Inbound -Program $path -Action Block -Profile Any | Out-Null
}
Write-Output ('Blokirano: ' + ($paths -join '; '))
"""

# PowerShell that removes every rule we created.
_UNBLOCK_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Remove-NetFirewallRule -Group '{group}' -ErrorAction SilentlyContinue
Write-Output 'Odblokirano'
"""


def is_admin() -> bool:
    """True if the current process has administrator rights."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _write_temp_script(script: str) -> str:
    """Write the PowerShell script to a fixed temp file and return its path.

    A fixed name (overwritten each call) avoids piling up temp files; passing a
    ``-File`` path also sidesteps all the quoting pain of inlining a multi-line
    script into a ``-Command`` / ShellExecute argument string.
    """
    path = os.path.join(tempfile.gettempdir(), "mm_bot_bluestacks_net.ps1")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(script)
    return path


def _run_direct(script_path: str) -> tuple[bool, str]:
    """Run the script in-process (we already have admin rights)."""
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-File", script_path,
            ],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, (proc.stdout or "").strip()
    return False, (proc.stderr or proc.stdout or "nepoznata greska").strip()


def _run_elevated(script_path: str) -> tuple[bool, str]:
    """Relaunch the script elevated via a UAC prompt (we are not admin).

    ShellExecuteW returns immediately (does not wait); a value > 32 means the
    elevated process started, so we can't read its real exit status here.
    """
    params = (
        '-NoProfile -NonInteractive -WindowStyle Hidden '
        '-ExecutionPolicy Bypass -File "{}"'.format(script_path)
    )
    try:
        rc = int(
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "powershell", params, None, 0
            )
        )
    except Exception as exc:
        return False, str(exc)
    if rc > 32:
        return True, ""
    if rc == 5:  # SE_ERR_ACCESSDENIED — user declined the UAC prompt
        return False, "UAC dozvola odbijena"
    return False, "ShellExecute greska ({})".format(rc)


def block_bluestacks(blocked: bool) -> tuple[bool, str]:
    """Block (True) or restore (False) internet for BlueStacks only.

    Returns ``(success, message)``. ``message`` carries the affected paths on a
    successful block, or a short error string on failure. On non-Windows
    platforms this is a no-op failure so the caller can show a clear message.
    """
    if not sys.platform.startswith("win"):
        return False, "Podrzano samo na Windows-u"
    script = (_BLOCK_SCRIPT if blocked else _UNBLOCK_SCRIPT).replace(
        "{group}", _RULE_GROUP
    )
    script_path = _write_temp_script(script)
    if is_admin():
        return _run_direct(script_path)
    return _run_elevated(script_path)
