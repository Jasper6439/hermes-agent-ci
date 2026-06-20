#!/bin/bash
# hermes-139yun-backup.sh — 每日自动备份关键数据到 139yun
# 通过 AList API 上传（WebDAV 只读）

set -euo pipefail

BASE="http://localhost:5244"
BACKUP_DIR="/139yun/hermes-backup"

# Login
TOKEN=$(curl -s -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"17110415"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('token',''))")

if [ -z "$TOKEN" ]; then
  echo "[$(date)] ❌ AList login failed"
  exit 1
fi

upload() {
  local src="$1"
  local dst="$2"
  if [ ! -f "$src" ]; then return; fi
  local encoded_path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$dst', safe='/'))")
  curl -s -X PUT "$BASE/api/fs/put" \
    -H "Authorization: $TOKEN" \
    -H "Content-Type: application/octet-stream" \
    -H "File-Path: $encoded_path" \
    --data-binary @"$src" > /dev/null 2>&1
}

echo "[$(date)] 开始备份..."

# Critical files
upload ~/.hermes/.env "$BACKUP_DIR/.env"
upload ~/.hermes/config.yaml "$BACKUP_DIR/config.yaml"
upload ~/.hermes/state.db "$BACKUP_DIR/databases/state.db"
upload ~/.hermes/fusion_facts.db "$BACKUP_DIR/databases/fusion_facts.db"
upload ~/.hermes/cron/jobs.json "$BACKUP_DIR/cron/jobs.json"

echo "[$(date)] ✅ 备份完成"
