#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-"$ROOT/dist/folio.zip"}"

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"

cd "$ROOT"

MANIFEST="$(mktemp)"
FILTERED_MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST" "$FILTERED_MANIFEST"' EXIT

git ls-files > "$MANIFEST"
awk '
  /^\.font-libs\// { next }
  /^assets\/fonts\/LXGWWenKai-(Regular|Medium)\.ttf$/ { next }
  /^assets\/demos\// { next }
  /^assets\/examples\// { next }
  /^assets\/illustrations\// { next }
  /^dist\// { next }
  /^\.vercel\// { next }
  /(^|\/)__pycache__\// { next }
  /\.pyc$/ { next }
  /(^|\/)\.DS_Store$/ { next }
  { print }
' "$MANIFEST" > "$FILTERED_MANIFEST"

zip -q "$OUT" -@ < "$FILTERED_MANIFEST"

if zipinfo -1 "$OUT" | grep -qE 'assets/fonts/LXGWWenKai-(Regular|Medium)\.ttf$'; then
  echo "ERROR: bundled LXGWWenKai TTF found in $OUT" >&2
  exit 1
fi

if zipinfo -1 "$OUT" | grep -qE '^\.font-libs/'; then
  echo "ERROR: bundled .font-libs found in $OUT" >&2
  exit 1
fi

MAX_BYTES=$((5 * 1024 * 1024))
SIZE_BYTES="$(stat -f%z "$OUT")"
if [ "$SIZE_BYTES" -ge "$MAX_BYTES" ]; then
  echo "ERROR: $OUT exceeds 5MB (${SIZE_BYTES} bytes)" >&2
  exit 1
fi

echo "OK: wrote $OUT"
