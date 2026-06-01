#!/usr/bin/env bash
# run.sh — 네이티브 단위테스트 빌드+실행 (Linux/macOS/WSL)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v g++ >/dev/null 2>&1; then
    echo "g++ 없음 → 네이티브 테스트 건너뜀"
    exit 0
fi

g++ -std=c++11 -Wall -Wextra -O2 -o "$here/test_sia_distance" \
    "$here/test_sia_distance.cpp"
"$here/test_sia_distance"
