# 書類メーカー 配布版のインストール（Windows PowerShell）
#   使い方: このフォルダで  powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$Src  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dest = if ($env:PAPER_MAKER_APP_DIR) { $env:PAPER_MAKER_APP_DIR } else { Join-Path $HOME ".paper-maker\app" }
$Bin  = Join-Path $HOME ".paper-maker\bin"

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Host "python が見つかりません。https://www.python.org/downloads/ から 3.9 以上を入れて、Add to PATH にチェックしてください"; exit 1 }
$ver = & python -c "import sys;print('%d.%d'%sys.version_info[:2])"
if ([version]$ver -lt [version]"3.9") { Write-Host "Python 3.9 以上が必要です（今は $ver）"; exit 1 }

New-Item -ItemType Directory -Force -Path $Dest, $Bin | Out-Null
if ($Src -ne $Dest) {
  robocopy $Src $Dest /MIR /XD .git __pycache__ dist /NFL /NDL /NJH /NJS | Out-Null
}
$cmd = "@echo off`r`ncd /d `"$Dest`"`r`npython -m paper_maker %*`r`n"
Set-Content -Path (Join-Path $Bin "paper-maker.cmd") -Value $cmd -Encoding ASCII

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$Bin*") {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$Bin", "User")
  Write-Host "PATH に $Bin を足しました（新しいターミナルから有効）"
}
Push-Location $Dest
$desk = & python -m paper_maker desktop 2>&1 | Select-Object -First 1
Pop-Location

Write-Host "入れました: $Dest"
Write-Host $desk
Write-Host ""
Write-Host "デスクトップの「書類メーカー」を押してください。画面が開いて、そこから全部入れられます。"
Write-Host "ターミナル派の人は: paper-maker init / paper-maker doctor"
