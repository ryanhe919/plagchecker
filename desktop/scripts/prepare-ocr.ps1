param([string]$Destination = (Join-Path $PSScriptRoot '..\.cache\tesseract'))
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-VerifiedFile([string]$Url, [string]$File, [string]$Sha256) {
    Invoke-WebRequest -Uri $Url -OutFile $File -TimeoutSec 180
    if ((Get-FileHash -Path $File -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256) {
        throw "SHA256 mismatch: $Url"
    }
}

$Destination = [IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$Installer = Join-Path ([IO.Path]::GetTempPath()) ('biaoheng-tesseract-' + [guid]::NewGuid() + '.exe')
$Extracted = Join-Path ([IO.Path]::GetTempPath()) ('biaoheng-ocr-' + [guid]::NewGuid())
try {
    Get-VerifiedFile `
        'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe' `
        $Installer 'bee9e3434bd94fd65387d9be28cd467a41f61b1275383b55b0f59a1331270ae4'
    # Extract only; do not run the installer or its unpinned model downloads.
    $SevenZip = (Get-Command 7z -ErrorAction Stop).Source
    & $SevenZip x $Installer "-o$Extracted" -y | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to extract the OCR runtime' }
    $Runtime = Get-ChildItem $Extracted -Recurse -Filter tesseract.exe | Select-Object -First 1
    if ($null -eq $Runtime) { throw 'Tesseract is not present in the archive' }
    Get-ChildItem $Runtime.Directory.FullName -File | Copy-Item -Destination $Destination -Force
    foreach ($Folder in @('tessdata', 'doc', 'licenses')) {
        $Source = Join-Path $Runtime.Directory.FullName $Folder
        if (Test-Path $Source) { Copy-Item $Source $Destination -Recurse -Force }
    }
    $Models = Join-Path $Destination 'tessdata'
    New-Item -ItemType Directory -Force -Path $Models | Out-Null
    $ModelCommit = '87416418657359cb625c412a48b6e1d6d41c29bd'
    Get-VerifiedFile "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$ModelCommit/eng.traineddata" `
        (Join-Path $Models 'eng.traineddata') '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'
    Get-VerifiedFile "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$ModelCommit/chi_sim.traineddata" `
        (Join-Path $Models 'chi_sim.traineddata') 'a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730'
    $Binary = Join-Path $Destination 'tesseract.exe'
    if (!(Test-Path $Binary)) { throw 'Tesseract executable is missing' }
    & $Binary --version
    if ($LASTEXITCODE -ne 0) { throw 'Tesseract runtime failed' }
    $env:TESSDATA_PREFIX = $Models
    $Languages = & $Binary --list-langs
    if ($LASTEXITCODE -ne 0 -or $Languages -notcontains 'chi_sim' -or $Languages -notcontains 'eng') {
        throw 'Required OCR languages are missing'
    }
    # Keep runtime DLLs and upstream licenses; installer/uninstaller are not shipped.
    Get-ChildItem $Destination -Filter '*uninstall*.exe' | Remove-Item -Force
    @"
Tesseract OCR 5.5.3 Windows runtime: https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.3
Tesseract and tessdata_fast models: Apache-2.0
Models commit: $ModelCommit
Sources and licenses: https://github.com/tesseract-ocr/tesseract and https://github.com/tesseract-ocr/tessdata_fast
This directory contains the complete upstream runtime, including its third-party DLLs and notices.
"@ | Set-Content -Path (Join-Path $Destination 'BUNDLED-OCR-NOTICE.txt') -Encoding utf8
} finally {
    Remove-Item -Path $Installer -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $Extracted -Recurse -Force -ErrorAction SilentlyContinue
}
