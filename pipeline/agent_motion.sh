#!/bin/bash
# 動く絵（Kling 2.6・0クレジット）。絵ができたカットから順に頼み、上限で落ちたら3分待って頼み直す（agent.yml）
#   bash pipeline/agent_motion.sh <作業フォルダ> <id,id,...> [場面の欄 image か image_en] [待つ秒。既定 5400]
cd "$1" || exit 1
IDS="${2//,/ }"; FIELD="${3:-image}"
END=$(( $(date +%s) + ${4:-5400} ))
while [ "$(date +%s)" -lt "$END" ]; do
  todo=""; left=0
  for i in $IDS; do
    [ -f "images/$i.mp4" ] && continue
    left=$((left+1))
    [ -f "images/$i.png" ] && todo="$todo,$i"
  done
  [ "$left" = 0 ] && break
  if [ -n "$todo" ]; then
    echo "== $(date '+%H:%M:%S') 頼む ${todo#,}（残り $left）"
    python -X utf8 -u "$GITHUB_WORKSPACE/agent_shared/tools/lovart_motion_v2.py" . --project-id 2o6natm73im8 --ids "${todo#,}" --field "$FIELD" --workers 1 --max-credits 0
  fi
  sleep 180
done
for i in $IDS; do [ -f "images/$i.mp4" ] && echo "$i ok" || echo "$i なし"; done
