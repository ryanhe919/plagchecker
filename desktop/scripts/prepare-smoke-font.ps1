$ErrorActionPreference = 'Stop'
$Destination = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\.cache\NotoSansCJKsc-Regular.otf'))
New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
$Commit = 'f8d157532fbfaeda587e826d4cd5b21a49186f7c'
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/notofonts/noto-cjk/$Commit/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf" -OutFile $Destination -TimeoutSec 180
if ((Get-FileHash -Path $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne '2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b') {
    throw 'Smoke font SHA256 mismatch'
}
# Used only to render CI fixtures; it is not included in the desktop package.
