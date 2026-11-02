#!/usr/bin/env bash
# Claude のアカウントを選ぶ（2026-11-02 本人「4日の12時を過ぎたらもどして。そのうえでもできなかったら新しいアカウントのほうでやって」）
# ・結果は CLAUDE_PICK（main か sub）として次の手順に渡す。鍵そのものは渡さない（各手順の env が CLAUDE_PICK を見て鍵を選ぶ）
# ・Variables の CLAUDE_ACCOUNT
#     main（か空）… いつも元のアカウント（CLAUDE_CODE_OAUTH_TOKEN）
#     sub        … CLAUDE_SUB_UNTIL（UTC の日時。例 2026-11-04T03:00:00Z）より前は新しいアカウント（CLAUDE_CODE_OAUTH_TOKEN_SUB）。
#                  過ぎたら、毎回まず元のアカウントで短く試し（Haiku に1行答えさせるだけ）、通れば元、通らなければ新しい方
#                  CLAUDE_SUB_UNTIL が空なら、すぐ「試して通れば元」になる
# ・新しいアカウントの鍵が無い時は、いつも元
# ・この手順は落ちない（選べなかった時は元を使う）
set -u
mode="${CLAUDE_ACCOUNT:-main}"
pick=main
why="CLAUDE_ACCOUNT=$mode"
if [ "${HAS_SUB:-false}" != "true" ]; then
  why="新しいアカウントの鍵が無い"
elif [ "$mode" = "sub" ]; then
  now=$(date -u +%s)
  until=0
  [ -n "${CLAUDE_SUB_UNTIL:-}" ] && until=$(date -u -d "$CLAUDE_SUB_UNTIL" +%s 2>/dev/null || echo 0)
  if [ "$now" -lt "$until" ]; then
    pick=sub
    why="$CLAUDE_SUB_UNTIL までは新しいアカウント"
  else
    out=$(CLAUDE_CODE_OAUTH_TOKEN="${MAIN_TOKEN:-}" timeout 180 claude -p "1 とだけ答えて" --model haiku 2>&1)
    rc=$?
    if [ $rc -eq 0 ] && ! printf '%s' "$out" | grep -qiE "limit|hit your|invalid|unauthori|401|403|credit|error"; then
      pick=main
      why="元のアカウントで試して通った"
    else
      pick=sub
      kind="その他"
      printf '%s' "$out" | grep -qiE "limit|hit your|credit" && kind="使用量の上限"
      printf '%s' "$out" | grep -qiE "invalid|unauthori|401|403" && kind="鍵が通らない"
      why="元のアカウントが使えない（終了コード $rc・$kind）"
    fi
  fi
fi
echo "CLAUDE_PICK=$pick" >> "${GITHUB_ENV:-/dev/null}"
echo "Claude のアカウント：$pick（$why）"
exit 0
