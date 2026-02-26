# Build Flutter web app and deploy to Flask templates.
# Firebase config and APP_URL are read from .env (never hardcoded in source).
#
# Usage:
#   .\build_web.ps1           # production release build
#   .\build_web.ps1 --debug   # debug build

param([string]$Mode = "")

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ScriptDir ".env"

# ── Load .env ──────────────────────────────────────────────────────────────────
if (-not (Test-Path $EnvFile)) {
    Write-Error "❌  .env not found at $EnvFile`n    Copy .env.example to .env and fill in your credentials."
    exit 1
}

$envVars = @{}
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
        $envVars[$matches[1].Trim()] = $matches[2].Trim()
    }
}

# ── Validate required Firebase vars ───────────────────────────────────────────
$required = @(
    "FIREBASE_API_KEY", "FIREBASE_APP_ID", "FIREBASE_MESSAGING_SENDER_ID",
    "FIREBASE_PROJECT_ID", "FIREBASE_AUTH_DOMAIN", "FIREBASE_STORAGE_BUCKET"
)
$missing = $required | Where-Object { -not $envVars[$_] }
if ($missing) {
    Write-Error "❌  Missing required vars in .env: $($missing -join ', ')"
    exit 1
}

# ── Resolve API base URL ───────────────────────────────────────────────────────
# Use APP_URL from .env; if absent, fall back to same-origin /api
# (works because Flask serves the Flutter build from the same host)
$appUrl = $envVars["APP_URL"]
$apiBaseUrl = if ($appUrl) { "$appUrl/api" } else { "/api" }

# ── Build Flutter web ──────────────────────────────────────────────────────────
Set-Location (Join-Path $ScriptDir "plant_lab_simulator")

$buildFlags = if ($Mode -eq "--debug") { @() } else { @("--release") }

flutter build web @buildFlags `
    "--dart-define=FIREBASE_API_KEY=$($envVars['FIREBASE_API_KEY'])" `
    "--dart-define=FIREBASE_APP_ID=$($envVars['FIREBASE_APP_ID'])" `
    "--dart-define=FIREBASE_MESSAGING_SENDER_ID=$($envVars['FIREBASE_MESSAGING_SENDER_ID'])" `
    "--dart-define=FIREBASE_PROJECT_ID=$($envVars['FIREBASE_PROJECT_ID'])" `
    "--dart-define=FIREBASE_AUTH_DOMAIN=$($envVars['FIREBASE_AUTH_DOMAIN'])" `
    "--dart-define=FIREBASE_STORAGE_BUCKET=$($envVars['FIREBASE_STORAGE_BUCKET'])" `
    "--dart-define=API_BASE_URL=$apiBaseUrl"

# ── Deploy to Flask ────────────────────────────────────────────────────────────
$dest = Join-Path $ScriptDir "app\templates"
Remove-Item -Path "$dest\*" -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item -Path "build\web\*" -Destination $dest -Recurse -Force

Write-Host "✅ Flutter app built and deployed to Flask" -ForegroundColor Green
