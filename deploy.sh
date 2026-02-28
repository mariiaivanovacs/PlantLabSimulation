#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh  –  Deploy PlantLabSimulation to Google Cloud Run
#
# Requirements:
#   gcloud CLI authenticated      →  gcloud auth login
#   Cloud Build API enabled       →  gcloud services enable cloudbuild.googleapis.com
#   Cloud Run API enabled         →  gcloud services enable run.googleapis.com
#
# Usage:
#   bash deploy.sh               # build (via Cloud Build) and deploy
#   bash deploy.sh --validate    # validate .env only, don't deploy
#   GEMINI_API_KEY="..." bash deploy.sh   # override GEMINI_API_KEY from env
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# ── Helpers ───────────────────────────────────────────────────────────────────
# Read a variable from .env, stripping inline comments and whitespace.
get_env() {
  # Return empty if file/var missing
  if [[ ! -f "$ENV_FILE" ]]; then
    return 0
  fi
  grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 \
    | cut -d'=' -f2- \
    | sed 's/[[:space:]]*#.*//' \
    | xargs || true
}

# Escape single quotes for safe single-quoted shell usage:
# e.g. O'Reilly  ->  'O'\''Reilly'
esc_for_single_quote() {
  # usage: esc_for_single_quote "string"
  local s="$1"
  # replace each ' with '\'' (POSIX-safe)
  printf "%s" "$s" | sed "s/'/'\\\\''/g"
}

# Join array by comma
join_by_comma() {
  local IFS=,
  echo "$*"
}

# Mask secret for logs (show first 4 chars only)
mask_secret() {
  local v="$1"
  if [[ -z "$v" ]]; then
    echo "<not set>"
  else
    local prefix="${v:0:4}"
    echo "${prefix}****"
  fi
}

# ── Validate .env exists (unless user only set env vars) ───────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  echo "❗ .env not found at $ENV_FILE — continuing if you set required vars via environment variables."
fi

# ── Load vars from .env, allowing environment overrides ──────────────────────
# Environment variables exported before running the script take precedence.
FIREBASE_PROJECT_ID="${FIREBASE_PROJECT_ID:-$(get_env FIREBASE_PROJECT_ID)}"
GEMINI_API_KEY="${GEMINI_API_KEY:-$(get_env GEMINI_API_KEY)}"
APP_URL="${APP_URL:-$(get_env APP_URL)}"
STRIPE_SECRET_KEY="${STRIPE_SECRET_KEY:-$(get_env STRIPE_SECRET_KEY)}"
STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-$(get_env STRIPE_WEBHOOK_SECRET)}"
LOG_LEVEL="${LOG_LEVEL:-$(get_env LOG_LEVEL)}"
CORS_ORIGINS="${CORS_ORIGINS:-$(get_env CORS_ORIGINS)}"

# Cloud Run deployment config (can override via env before running this script)
PROJECT_ID="${FIREBASE_PROJECT_ID:?FIREBASE_PROJECT_ID not set in .env or env}"
REGION="${CLOUD_RUN_REGION:-us-central1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-plantlab-simulator}"

# ── Validate required vars ────────────────────────────────────────────────────
missing=()
[[ -z "$GEMINI_API_KEY" ]]      && missing+=("GEMINI_API_KEY")
[[ -z "$FIREBASE_PROJECT_ID" ]] && missing+=("FIREBASE_PROJECT_ID")

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "❌  Required vars missing: ${missing[*]}"
  echo "    Either put them in $ENV_FILE or export them in your shell before running this script."
  echo "    Example: export GEMINI_API_KEY=\"your_key\" && bash deploy.sh"
  exit 1
fi

echo "✅ .env validated (or overridden by environment variables)"
echo "   Project:  $PROJECT_ID"
echo "   Region:   $REGION"
echo "   Service:  $SERVICE_NAME"
echo "   APP_URL:  ${APP_URL:-<not set>}"
echo "   GEMINI_API_KEY: $(mask_secret "$GEMINI_API_KEY")"

if [[ "${1:-}" == "--validate" ]]; then
  echo ""
  echo "Validation only — skipping deploy."
  exit 0
fi

# ── Build Cloud Run env-vars pairs, using safe single-quote escaping ────────
declare -a env_pairs

append_env_pair() {
  local key="$1"
  local val="$2"
  if [[ -z "$val" ]]; then
    return 0
  fi
  # escape single quotes for safe single-quoted value
  local esc_val
  esc_val="$(esc_for_single_quote "$val")"
  # add as KEY='VALUE' to preserve any spaces/commas
  env_pairs+=("${key}=${esc_val}")
}

append_env_pair "FLASK_ENV" "production"
append_env_pair "FLASK_DEBUG" "False"
append_env_pair "FIREBASE_PROJECT_ID" "$FIREBASE_PROJECT_ID"
append_env_pair "GEMINI_API_KEY" "$GEMINI_API_KEY"

append_env_pair "APP_URL" "$APP_URL"
# Add API_BASE_URL only if APP_URL set
if [[ -n "${APP_URL:-}" ]]; then
  # ensure no trailing slash
  api_base="${APP_URL%/}/api"
  append_env_pair "API_BASE_URL" "$api_base"
fi

append_env_pair "STRIPE_SECRET_KEY" "$STRIPE_SECRET_KEY"
append_env_pair "STRIPE_WEBHOOK_SECRET" "$STRIPE_WEBHOOK_SECRET"
append_env_pair "LOG_LEVEL" "$LOG_LEVEL"
append_env_pair "CORS_ORIGINS" "$CORS_ORIGINS"

# join into single CSV string for --set-env-vars
ENV_VARS="$(join_by_comma "${env_pairs[@]}")"

# ── Build Flutter web app ─────────────────────────────────────────────────────
# API_BASE_URL is baked into the Flutter JS at build time (String.fromEnvironment).
# It MUST be rebuilt every time .env changes — just changing .env has no effect.
if [[ "${1:-}" != "--skip-flutter" ]] && [[ "${SKIP_FLUTTER:-}" != "1" ]]; then
  if command -v flutter &>/dev/null; then
    _dart_url="$( [[ -n "${APP_URL:-}" ]] && echo "${APP_URL%/}/api" || echo "/api" )"
    echo "🔨 Building Flutter web app (API_BASE_URL=$_dart_url)…"
    bash "$SCRIPT_DIR/build_web.sh"
    echo ""
  else
    echo "⚠️  Flutter not found in PATH — skipping web build."
    echo "   The app/templates/ directory must contain a freshly built Flutter app."
    echo "   Run 'bash build_web.sh' first if you haven't since the last .env change."
    echo "   Or pass SKIP_FLUTTER=1 bash deploy.sh to suppress this warning."
    echo ""
  fi
fi

# ── Deploy ────────────────────────────────────────────────────────────────────
echo ""
echo "🚀 Deploying to Cloud Run…"
echo "   (Cloud Build will build the Docker image — no local Docker needed)"
echo ""

gcloud run deploy "$SERVICE_NAME" \
  --source "$SCRIPT_DIR" \
  --platform managed \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --set-env-vars "$ENV_VARS" \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 3 \
  --allow-unauthenticated

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format "value(status.url)")

echo ""
echo "✅ Deployed successfully!"
echo "   URL:    $SERVICE_URL"
echo "   Health: ${SERVICE_URL%/}/health"