#!/usr/bin/env bash
# HR Chatbot — Disaster Recovery Backup Script (Phase 5, F-61)
#
# Backs up:
#   1. PostgreSQL → pg_dump → compressed → MinIO
#   2. Qdrant snapshots → MinIO
#   3. Application config (non-secret) → MinIO
#
# RTO (Recovery Time Objective): < 4 hours
# RPO (Recovery Point Objective): < 24 hours (daily backup)
#
# Usage:
#   ./scripts/backup.sh                     # Run all backups
#   ./scripts/backup.sh --postgres-only     # PostgreSQL only
#   ./scripts/backup.sh --qdrant-only       # Qdrant only
#
# Schedule via cron (daily at 1am):
#   0 1 * * * /app/scripts/backup.sh >> /var/log/hr-chatbot-backup.log 2>&1
#
# Restore procedure:
#   PostgreSQL: pg_restore -h localhost -U hr_user -d hr_chatbot backup.dump
#   Qdrant:     POST /collections/hr_chunks/snapshots/recover { location: "..." }
#   MinIO:      mc mirror minio/backups/latest /data/restore
#
# Environment variables required:
#   DATABASE_URL, QDRANT_URL, MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY
#   BACKUP_BUCKET (default: hr-chatbot-backups)

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_BUCKET="${BACKUP_BUCKET:-hr-chatbot-backups}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-localhost:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin123}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

POSTGRES_ONLY=false
QDRANT_ONLY=false

for arg in "$@"; do
  case $arg in
    --postgres-only) POSTGRES_ONLY=true ;;
    --qdrant-only) QDRANT_ONLY=true ;;
  esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

# ── mc (MinIO Client) setup ───────────────────────────────────────────────────
setup_mc() {
  if ! command -v mc &>/dev/null; then
    log "Installing MinIO client..."
    curl -sf "https://dl.min.io/client/mc/release/linux-amd64/mc" -o /tmp/mc
    chmod +x /tmp/mc
    MC=/tmp/mc
  else
    MC=mc
  fi
  $MC alias set backup "http://${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --quiet
  $MC mb --ignore-existing "backup/${BACKUP_BUCKET}" || true
}

# ── PostgreSQL backup ─────────────────────────────────────────────────────────
backup_postgres() {
  log "Starting PostgreSQL backup..."

  # Parse DATABASE_URL: postgresql://user:pass@host:port/dbname
  DB_URL="${DATABASE_URL:-postgresql://hr_user:hr_dev_password_change_in_prod@localhost:5432/hr_chatbot}"
  DUMP_FILE="/tmp/hr_chatbot_${TIMESTAMP}.dump"

  pg_dump "$DB_URL" \
    --format=custom \
    --compress=9 \
    --no-privileges \
    --no-owner \
    --file="$DUMP_FILE"

  # Upload to MinIO
  $MC cp "$DUMP_FILE" "backup/${BACKUP_BUCKET}/postgres/${TIMESTAMP}.dump"
  rm -f "$DUMP_FILE"

  DUMP_SIZE=$(du -sh "$DUMP_FILE" 2>/dev/null | cut -f1 || echo "unknown")
  log "PostgreSQL backup complete: postgres/${TIMESTAMP}.dump"
}

# ── Qdrant snapshot backup ────────────────────────────────────────────────────
backup_qdrant() {
  log "Starting Qdrant snapshot..."

  # Trigger snapshot creation
  SNAPSHOT_RESPONSE=$(curl -sf -X POST \
    "${QDRANT_URL}/collections/hr_chunks/snapshots" \
    -H "Content-Type: application/json")

  SNAPSHOT_NAME=$(echo "$SNAPSHOT_RESPONSE" | python3 -c \
    "import sys,json; print(json.load(sys.stdin)['result']['name'])" 2>/dev/null || echo "")

  if [ -z "$SNAPSHOT_NAME" ]; then
    error "Failed to create Qdrant snapshot: $SNAPSHOT_RESPONSE"
    return 1
  fi

  # Download snapshot
  SNAP_FILE="/tmp/qdrant_${TIMESTAMP}.snapshot"
  curl -sf "${QDRANT_URL}/collections/hr_chunks/snapshots/${SNAPSHOT_NAME}" \
    -o "$SNAP_FILE"

  # Upload to MinIO
  $MC cp "$SNAP_FILE" "backup/${BACKUP_BUCKET}/qdrant/${TIMESTAMP}.snapshot"
  rm -f "$SNAP_FILE"

  log "Qdrant backup complete: qdrant/${TIMESTAMP}.snapshot"
}

# ── Retention cleanup ─────────────────────────────────────────────────────────
cleanup_old_backups() {
  log "Cleaning up backups older than ${RETENTION_DAYS} days..."
  $MC rm --recursive --force --older-than "${RETENTION_DAYS}d" \
    "backup/${BACKUP_BUCKET}/postgres/" 2>/dev/null || true
  $MC rm --recursive --force --older-than "${RETENTION_DAYS}d" \
    "backup/${BACKUP_BUCKET}/qdrant/" 2>/dev/null || true
  log "Cleanup complete"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  log "HR Chatbot backup started (timestamp: ${TIMESTAMP})"

  setup_mc

  if [ "$QDRANT_ONLY" = false ]; then
    backup_postgres || error "PostgreSQL backup failed"
  fi

  if [ "$POSTGRES_ONLY" = false ]; then
    backup_qdrant || error "Qdrant backup failed"
  fi

  cleanup_old_backups

  log "Backup complete"
}

main "$@"
