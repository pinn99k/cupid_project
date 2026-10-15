# run.ps1 — 네이티브 단위테스트 빌드+실행 (Windows / PowerShell)
# 요구: g++ (MinGW 또는 MSYS2). 없으면 "건너뜀" 안내.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $here "test_sia_distance.cpp"
$exe = Join-Path $here "test_sia_distance.exe"

$gpp = (Get-Command g++ -ErrorAction SilentlyContinue)
if ($null -eq $gpp) {
    Write-Host "g++ 없음 → 네이티브 테스트 건너뜀 (MinGW/MSYS2 설치 시 실행 가능)" -ForegroundColor Yellow
    exit 0
}

& g++ -std=c++11 -Wall -Wextra -O2 -o $exe $src
if ($LASTEXITCODE -ne 0) { Write-Host "컴파일 실패" -ForegroundColor Red; exit 1 }

& $exe
exit $LASTEXITCODE
