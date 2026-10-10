param(
    [Parameter(Mandatory)][string]$Executable,
    [Parameter(Mandatory)][string]$Fixtures,
    [Parameter(Mandatory)][string]$DataDirectory,
    [Parameter(Mandatory)][string]$Report,
    [int]$ExpectedRestoredReports = 0
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Executable = [IO.Path]::GetFullPath($Executable)
$Fixtures = [IO.Path]::GetFullPath($Fixtures)
$DataDirectory = [IO.Path]::GetFullPath($DataDirectory)
$Report = [IO.Path]::GetFullPath($Report)
New-Item -ItemType Directory -Force -Path (Split-Path $Report) | Out-Null
Remove-Item $Report -Force -ErrorAction SilentlyContinue
$OriginalPath = $env:PATH
$OriginalPythonHome = $env:PYTHONHOME
$OriginalPythonPath = $env:PYTHONPATH
$OriginalTessdata = $env:TESSDATA_PREFIX
$OriginalTesseract = $env:TESSERACT_CMD
$Process = $null
try {
    # The application may only find Windows itself, never build-machine Python/Node/OCR.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Remove-Item Env:PYTHONHOME, Env:PYTHONPATH, Env:TESSDATA_PREFIX, Env:TESSERACT_CMD -ErrorAction SilentlyContinue
    $Arguments = @("`"--smoke-test=$Report`"", "`"--smoke-fixtures=$Fixtures`"", "`"--data-dir=$DataDirectory`"")
    $Process = Start-Process -FilePath $Executable -ArgumentList $Arguments -PassThru
    if (!$Process.WaitForExit(300000)) { throw 'Packaged application smoke test timed out' }
    if ($Process.ExitCode -ne 0) { throw "Packaged application exited with $($Process.ExitCode)" }
    if (!(Test-Path $Report)) { throw 'Application did not produce a smoke report' }
    $Result = Get-Content -Raw -Path $Report | ConvertFrom-Json
    if (!$Result.ok) { throw "Application smoke failed: $($Result.error)" }
    if ($Result.restoredReports -lt $ExpectedRestoredReports) { throw 'History was not restored after restart' }
    foreach ($BackendPid in $Result.backendPids) {
        if (Get-Process -Id $BackendPid -ErrorAction SilentlyContinue) { throw "Backend process $BackendPid survived application exit" }
    }
    if (Test-Path (Join-Path $DataDirectory 'backend-ready.json')) { throw 'Backend was not stopped on application exit' }
    Get-Content -Raw -Path $Report
} finally {
    if ($null -ne $Process -and !$Process.HasExited) {
        & "$env:SystemRoot\System32\taskkill.exe" /PID $Process.Id /T /F | Out-Null
    }
    $env:PATH = $OriginalPath
    $env:PYTHONHOME = $OriginalPythonHome
    $env:PYTHONPATH = $OriginalPythonPath
    $env:TESSDATA_PREFIX = $OriginalTessdata
    $env:TESSERACT_CMD = $OriginalTesseract
}
