#!/usr/bin/env bash
# ============================================================
#  deploy.sh — Deploy LearnPath Agent to Google Cloud Run
#
#  Usage:
#    chmod +x deploy.sh
#    ./deploy.sh
#
#  Prerequisites:
#    - gcloud CLI installed and authenticated (gcloud auth login)
#    - .env file with GCP_PROJECT_ID, GCP_REGION, GOOGLE_API_KEY, YOUTUBE_API_KEY
#    - Docker running (used by Cloud Build)
# ============================================================

set -euo pipefail

# ── Load .env ────────────────────────────────────────────────
if [ ! -f .env ]; then
  echo "❌  .env file not found. Copy .env.example → .env and fill in your values."
  exit 1
fi

# shellcheck disable=SC2046
export $(grep -v '^#' .env | grep -v '^\s*$' | xargs)

# ── Validate required vars ───────────────────────────────────
: "${GCP_PROJECT_ID:?GCP_PROJECT_ID is required in .env}"
: "${GCP_REGION:?GCP_REGION is required in .env}"
: "${GOOGLE_API_KEY:?GOOGLE_API_KEY is required in .env}"

SERVICE_NAME="learnpath-agent"
IMAGE="gcr.io/${GCP_PROJECT_ID}/${SERVICE_NAME}"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║      LearnPath Agent — Cloud Run Deploy  ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Project : ${GCP_PROJECT_ID}"
echo "  Region  : ${GCP_REGION}"
echo "  Service : ${SERVICE_NAME}"
echo "  Image   : ${IMAGE}"
echo ""

# ── Step 1: Set gcloud project ───────────────────────────────
echo "▶  Setting active project…"
gcloud config set project "${GCP_PROJECT_ID}"

# ── Step 2: Enable required APIs ────────────────────────────
echo "▶  Enabling Cloud APIs (first run may take ~30s)…"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  containerregistry.googleapis.com \
  --quiet

# ── Step 3: Store secrets in Secret Manager ──────────────────
echo "▶  Storing secrets in Secret Manager…"

store_secret() {
  local name="$1"
  local value="$2"
  if gcloud secrets describe "${name}" --project="${GCP_PROJECT_ID}" &>/dev/null; then
    echo "     ${name} already exists — adding new version."
    echo -n "${value}" | gcloud secrets versions add "${name}" \
      --data-file=- --project="${GCP_PROJECT_ID}"
  else
    echo "     Creating secret: ${name}"
    echo -n "${value}" | gcloud secrets create "${name}" \
      --data-file=- --project="${GCP_PROJECT_ID}"
  fi
}

store_secret "GOOGLE_API_KEY"   "${GOOGLE_API_KEY}"
store_secret "YOUTUBE_API_KEY"  "${YOUTUBE_API_KEY:-mock}"

# ── Step 4: Build & push container ───────────────────────────
echo "▶  Building and pushing container image…"
gcloud builds submit --tag "${IMAGE}" --quiet

# ── Step 5: Deploy to Cloud Run ──────────────────────────────
echo "▶  Deploying to Cloud Run…"
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${GCP_REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 120 \
  --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,YOUTUBE_API_KEY=YOUTUBE_API_KEY:latest" \
  --quiet

# ── Done ─────────────────────────────────────────────────────
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${GCP_REGION}" --format="value(status.url)")

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║              ✅  DEPLOYED                ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Service URL : ${SERVICE_URL}"
echo ""
echo "  Test it:"
echo "  curl -X POST ${SERVICE_URL}/run \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"message\": \"I want to learn Python for data science in 4 weeks\"}'"
echo ""
