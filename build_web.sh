#!/bin/bash
# Build Flutter web app and deploy to Flask templates.
# Firebase config is read from .env (never hardcoded in source).
#
# Usage:
#   bash build_web.sh               # production release build
#   bash build_web.sh --debug       # debug build (faster, no tree-shaking)

set -e

SCRIPT_DIR="$(cd "$(dirname "${0}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# ── Load .env ──────────────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  echo "❌  .env not found at $ENV_FILE"
  echo "    Copy .env.example to .env and fill in your Firebase web credentials."
  exit 1
fi

# Read FIREBASE_* vars from .env into the current shell
eval "$(grep -E '^FIREBASE_[A-Z_]+=' "$ENV_FILE" | grep -v '^#')"

# ── Validate required web vars ─────────────────────────────────────────────────
required_vars=(
  FIREBASE_API_KEY
  FIREBASE_APP_ID
  FIREBASE_MESSAGING_SENDER_ID
  FIREBASE_PROJECT_ID
  FIREBASE_AUTH_DOMAIN
  FIREBASE_STORAGE_BUCKET
)

missing=()
for var in "${required_vars[@]}"; do
  val="${!var}"
  if [ -z "$val" ]; then
    missing+=("$var")
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  echo "❌  Missing required Firebase vars in .env:"
  for m in "${missing[@]}"; do echo "    $m"; done
  echo "    See .env.example for the full list."
  exit 1
fi

# ── Build Flutter web ──────────────────────────────────────────────────────────
cd "$SCRIPT_DIR/plant_lab_simulator"

BUILD_FLAGS="--release"
if [ "$1" = "--debug" ]; then
  BUILD_FLAGS=""
fi

flutter build web $BUILD_FLAGS \
  --dart-define="FIREBASE_API_KEY=$FIREBASE_API_KEY" \
  --dart-define="FIREBASE_APP_ID=$FIREBASE_APP_ID" \
  --dart-define="FIREBASE_MESSAGING_SENDER_ID=$FIREBASE_MESSAGING_SENDER_ID" \
  --dart-define="FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID" \
  --dart-define="FIREBASE_AUTH_DOMAIN=$FIREBASE_AUTH_DOMAIN" \
  --dart-define="FIREBASE_STORAGE_BUCKET=$FIREBASE_STORAGE_BUCKET"

# ── Deploy to Flask ────────────────────────────────────────────────────────────
cp -r build/web/* "$SCRIPT_DIR/app/templates/"

echo "✅ Flutter app built and deployed to Flask"
