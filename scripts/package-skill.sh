#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-"$ROOT/dist/folio.zip"}"

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"

cd "$ROOT"

MANIFEST="$(mktemp)"
FILTERED_MANIFEST="$(mktemp)"
ZIP_MANIFEST="$(mktemp)"
MISSING_MANIFEST="$(mktemp)"
EXTRA_MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST" "$FILTERED_MANIFEST" "$ZIP_MANIFEST" "$MISSING_MANIFEST" "$EXTRA_MANIFEST"' EXIT

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

zipinfo -1 "$OUT" | sort > "$ZIP_MANIFEST"
sort "$FILTERED_MANIFEST" -o "$FILTERED_MANIFEST"
comm -23 "$FILTERED_MANIFEST" "$ZIP_MANIFEST" > "$MISSING_MANIFEST"
comm -13 "$FILTERED_MANIFEST" "$ZIP_MANIFEST" > "$EXTRA_MANIFEST"

if [ -s "$MISSING_MANIFEST" ]; then
  echo "ERROR: package missing tracked source file(s):" >&2
  sed 's/^/  /' "$MISSING_MANIFEST" >&2
  exit 1
fi

if [ -s "$EXTRA_MANIFEST" ]; then
  echo "ERROR: package contains unexpected file(s):" >&2
  sed 's/^/  /' "$EXTRA_MANIFEST" >&2
  exit 1
fi

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
