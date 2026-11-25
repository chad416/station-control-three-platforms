<#
  Run a CODESYS script without the CODESYS window (Windows PowerShell 5.1).
  Usage: powershell -ExecutionPolicy Bypass -File codesys\scripts\run_codesys.ps1 [-Script build_and_run.py]
#>
param(
    [string]$Script = "build_and_run.py",
    [string]$Exe = "C:\Program Files\CODESYS 3.5.22.10\CODESYS\Common\CODESYS.exe",
    [string]$Profile = "CODESYS V3.5 SP22 Patch 1"
)
$path = Join-Path $PSScriptRoot $Script
$build = Join-Path (Split-Path -Parent $PSScriptRoot) "build"
New-Item -ItemType Directory -Force $build | Out-Null
$p = Start-Process -FilePath $Exe -ArgumentList "--profile=`"$Profile`"", "--noUI", "--runscript=`"$path`"" `
    -WindowStyle Hidden -PassThru -Wait `
    -RedirectStandardOutput (Join-Path $build "codesys_stdout.txt") -RedirectStandardError (Join-Path $build "codesys_stderr.txt")
"CODESYS exit code $($p.ExitCode)"
Get-Content (Join-Path $build "codesys_stdout.txt") -Tail 20
