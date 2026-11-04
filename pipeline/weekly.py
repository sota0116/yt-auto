# 週報（設計書 §2「週1回（日曜の夜）」・§7 判定会・付録A）：日曜 21:07 JST
#   python -X utf8 pipeline\weekly.py job [spi] [--no-issue]
# ・数字を集めるのはプログラム（history\ の uploaded・metrics・watch・cost・produced・last_run と heartbeat）。
#   集めた物は history\weekly\<日付>.json に置く
# ・週報の文は Claude（claude -p）が、集めた物と手順書・設計書の線（付録A）から書く。鍵は渡さない（write_script.py と同じ分け方）
# ・週報の上から：①今週あなたがやること（最大3行）②判定会の結論1行（続ける／変える／止める）③仕組みの健康状態1行。細かい数字はその下
# ・できた週報は Issue「週報 <日付>」にする（手元で gh が無い時は history\weekly\<日付>.md に置くだけ）
# ・Claude のトークン（CLAUDE_TOKEN_ISSUED から1年）と Lovart の無料の期間は、切れる1か月前から「今週やること」に出す
# ・まだ無いもの：UTAGE の流入経路づくり・LINE の声の取り込み・特典の作り直し・ネタ帳の補充（作れるネタは facts を作るプログラムの数で決まるので、
#   週報には「データ待ちで飛ばしているネタ帳の行」を出す）
# ・心理学ch（psy。2026-10-27）：型の代わりに area（人づきあい・ひとりの時間・眠りと夜・幸せの心理）で比べる。ショートの数字（shorts_watch.py）も集める。
#   数字から分かったことを history\psy\学び.md に書かせる。毎日の台本の書き手（write_script_psy.py）がこれを読む（手順書は変えない。手順書を変える案は週報に出して持ち主が決める）
# ・千年こよみ（spi。2026-10-28 本人「どんどん作ってどんどん数値分析してどんどんPDCA回していけるように」）：psy と同じく
#   history\spi\学び.md を書かせる。台本を書く時（Claude Code が手で作る。手順書 §14）に必ず読む。
#   ショートは種類（kind：teaser 予告・after 切り出し・solo 単独）ごとと、枠の時刻（11:15・19:15）ごとに比べる
# ・公開の時間帯と間隔（2026-11-04 本人「同じチャンネルで動画と動画の間は時間を空けて。毎週アナリティクスの数字を取って分析して仮説を立てて修正して」）：
#   weekly.yml が鍵を置いて slot_stats.py を回し（history\<ch>\slot_stats.json）、鍵を消してから、ここが週報を書かせる。
#   Claude は 8 で、時刻・間隔・その日の本数ごとの数字から仮説を history\weekly\枠の仮説.md に足し、枠の案を history\weekly\<日付>_枠の案.json に書く。
#   案は slot_apply.py が決まり（ショートの枠だけ・本数そのまま・3時間あける・数字3本以上・1チャンネル週1件・14日あける）に合う物だけ
#   history\slot_plan.json に書く（day_slots.py が読む）。結果は週報の最後に足す
# ・kakure・shimei・nihongi・okinu は 3（健康）・4（数字）・8（時間帯）だけ書かせる（1〜7 の全部は job・psy・spi）
import argparse, datetime, json, os, re, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import jload, now, ping
from run_daily import jsave, verify_checksums
import day_slots as ds
from slot_apply import apply as slot_apply
from write_script import DOCS, SECRET_ENV, doc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOVART_FREE_END = {"Nano Banana 2": "2027-02-28", "Nano Banana Pro": "2027-01-19"}  # 2026-10-24 時点の残り127日・87日（設計書 §7）


FULL = ("job", "psy", "spi")  # 週報の 1〜7 の全部を書くチャンネル。ほかは 3・4・8 だけ


def h(ch, name, d):
    return jload(os.path.join(ROOT, "history", ch, name), d)


def per_type(metrics):
    """型ごとの平均（7日後の数字がある回。無ければ72時間後）。判定に使うのは表示1,000回以上の回（設計書 §2）"""
    out = {}
    for w, m in metrics.items():
        row = m.get("d7") if m.get("d7", {}).get("views") is not None else m.get("h72")
        if not row or row.get("views") is None:
            continue
        t = out.setdefault(m.get("type") or "?", {"本数": 0, "表示1000以上": 0, "rows": []})  # 心理学chの type は area
        t["本数"] += 1
        t["表示1000以上"] += 1 if (row.get("impressions") or 0) >= 1000 else 0
        t["rows"].append(row)
    for t in out.values():
        rows = t.pop("rows")
        avg = lambda k: round(sum(r.get(k) or 0 for r in rows) / len(rows), 2)
        t.update(平均再生=avg("views"), 平均視聴率=avg("averageViewPercentage"), クリック率=avg("ctr"),
                 登録_1万回あたり=round(sum(r.get("subscribersGained") or 0 for r in rows) / max(1, sum(r.get("views") or 0 for r in rows)) * 1e4, 1))
    return out


def gather(chs):
    hb = jload(os.path.join(ROOT, "history", "heartbeat.json"), {})
    today = now().date()
    d = {"日付": today.isoformat(), "最後の実行": hb, "固定データの照合": verify_checksums() or "一致",
         "MONTHLY_CAP_YEN": os.environ.get("MONTHLY_CAP_YEN"), "STOCK_PHASE": os.environ.get("STOCK_PHASE") or "pre",
         "期限": {}, "チャンネル": {}}
    iss = os.environ.get("CLAUDE_TOKEN_ISSUED")
    if iss:
        end = datetime.date.fromisoformat(iss) + datetime.timedelta(days=365)
        d["期限"]["Claude のトークン"] = {"切れる日": end.isoformat(), "1か月以内": (end - today).days <= 31}
    for k, v in LOVART_FREE_END.items():
        end = datetime.date.fromisoformat(v)
        d["期限"][f"Lovart の無料（{k}）"] = {"切れる日": v, "1か月以内": (end - today).days <= 31}
    week_ago = (today - datetime.timedelta(days=7)).isoformat()
    for ch in chs:
        up, metrics, w = h(ch, "uploaded.json", []) or h(ch, "long_uploaded.json", []), h(ch, "metrics.json", {}), h(ch, "watch.json", {})  # kakure・shimei の横は long_uploaded.json
        if isinstance(up, dict):
            up = list(up.values())
        for e in up:  # long_uploaded.json には published が無いので、公開の時刻を過ぎた物は公開済みとして数える
            t = ds._ts(e.get("publish_at")) if isinstance(e, dict) and not e.get("published") else None
            if t and t <= now():
                e["published"] = True
        if not isinstance(metrics, dict):  # 日本紀・おきぬは一覧の形（stats_<ch>.py）。見張りの数字は metrics_auto.json（watch.py）
            metrics = h(ch, "metrics_auto.json", {})
        prod, cost, last = h(ch, "produced.json", []), h(ch, "cost.json", {}), h(ch, "last_run.json", {})
        nxt = [(today + datetime.timedelta(days=i)).isoformat() for i in range(1, 8)]
        booked = {(e.get("publish_at") or "")[:10] for e in up if not e.get("missing")}
        board = jload(os.path.join(ROOT, "channels", ch, "ネタ帳.json"), [])
        used = {p.get("neta_id") for p in prod}
        if ch == "spi":  # 手で作る。ネタ帳は手順書 §2 の行事・暦の日付から選ぶ
            sm = h(ch, "shorts_metrics.json", {})
            su = h(ch, "shorts_uploaded.json", [])
            by_kind = per_type({k: {**v, "type": v.get("kind") or "after"} for k, v in sm.items()})
            by_slot = per_type({k: {**v, "type": v.get("publish_slot") or "?"} for k, v in sm.items()})
            extra = {"ショート": {"上げた本数": sum(1 for x in su if not x.get("retired") and not x.get("missing")),
                                "来週の枠（11:15・19:15）で空いている数": 14 - sum(1 for x in su if not x.get("missing") and not x.get("retired")
                                                                   and (x.get("publish_at") or "")[:10] in nxt),
                                "種類ごと": by_kind, "時刻ごと": by_slot, "回ごとの数字": sm}}
        elif ch == "psy":  # 研究は書く段が調べるので「データ待ち」は無い。ネタ帳は競合リサーチが足す
            sm = h(ch, "shorts_metrics.json", {})
            extra = {"ネタ帳": {"残り": sum(1 for r in board if r["id"] not in used and not r.get("hold")),
                               "競合リサーチが足した行": [r["title"] for r in board if r.get("from") == "競合リサーチ" and r["id"] not in used]},
                     "ショート": {"上げた本数": len(h(ch, "shorts_uploaded.json", [])), "area ごと": per_type(sm), "回ごとの数字": sm,
                                "作れなかった回": [p["work"] for p in prod if p.get("short_video_id") == "上げられなかった"]}}
        elif ch not in FULL:  # kakure・shimei・nihongi・okinu はネタ帳の形がちがい、週報も 3・4・8 だけなので数えない
            extra = {}
        else:
            extra = {"ネタ帳": {"残り": sum(1 for r in board if r["id"] not in used and not r.get("hold")),
                               "データ待ち（facts_cmd が無い）": [r["id"] for r in board if r["id"] not in used and not r.get("facts_cmd")]}}
            if ch == "job":  # 手順書 §12：伸びたショートは同じ題の長尺と関連動画につなぐ案を出す。音と画の直しの前後もここで見る
                sl = h(ch, "shorts_learn.json", {})
                extra["ショート"] = {k: sl.get(k) for k in ("編集の版ごと", "伸びた回")}
                # 手順書 §12 の投稿：作るのは Chrome の画面からなので、予約が切れる前に足せるよう残りを出す
                posts = h(ch, "posts.json", [])
                left = [p for p in posts if p["日"] > now().strftime("%Y-%m-%d")]
                lp = max((p["日"] for p in left), default=None)  # last（最後の毎日の実行）と名前を分ける（2026-11-04 まで上書きしていて週報が落ちた）
                extra["投稿"] = {"予約の残り": len(left), "最後の予約": lp, "足す時期": lp is None or lp <= (now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")}
        st = h(ch, "slot_stats.json", {})
        ov = jload(ds.OVERRIDE_PATH, {})
        slots = {"枠（いま）": ds.PLAN.get(ch), "枠（day_slots.py に書いたまま）": ds.BASE.get(ch),
                 "週次が直した記録": [x for x in ov.get("_log", []) if x.get("ch") == ch],
                 "数字の状態": st.get("状態") or "まだ取っていない", "数字の更新": st.get("更新"), "確定待ち": st.get("確定待ち"),
                 "まとめ（確定した分）": st.get("まとめ") or {},
                 "1本ごと（確定した分）": {v.get("work") or k: {x: v.get(x) for x in ("時刻", "曜日", "その日の本数", "前との間隔", "後との間隔", "横", "数字")}
                                       for k, v in (st.get("videos") or {}).items() if v.get("確定")}}
        d["チャンネル"][ch] = {
            "在庫": sum(1 for e in up if not e.get("published") and not e.get("missing")),
            "来週の予約が無い日": [x for x in nxt if x not in booked],
            "今月の制作費_円": cost.get(now().strftime("%Y-%m"), 0),
            "今週作った回": [{k: p.get(k) for k in ("work", "type", "frame", "title", "回した理由", "competitor_note", "learn_note", "台本ゲートの点")} for p in prod if str(p.get("made", "")) >= week_ago],
            "最後の毎日の実行": {k: last.get(k) for k in ("started", "made", "stopped", "飛ばした回")},
            "型ごと": per_type(metrics),
            "回ごとの数字": metrics,
            "差し替え": {e["work"]: e["swaps"] for e in up if e.get("swaps")},
            "見張り": {k: w.get(k) for k in ("ctr_api", "comments_off", "comment_gone", "明後日の予約", "AIの申告がオフ", "type_hold", "予約")},
            "時間帯": slots,
            **extra,
        }
    return d


def design_doc():
    """設計書の正本は OneDrive の「設計」フォルダの一番新しい版。手元では repo の docs/設計書.md へ写す（クラウドは写しを読む）"""
    src_dir, dst = os.path.join(DOCS, "設計"), os.path.join(ROOT, "docs", "設計書.md")
    if os.path.isdir(src_dir):
        vs = sorted((f for f in os.listdir(src_dir) if f.startswith("クラウド自動制作_設計書_v") and f.endswith(".md")),
                    key=lambda f: [int(x) for x in re.findall(r"v([\d.]+)_", f)[0].split(".")])
        if vs:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(src_dir, vs[-1]), dst)
    return dst


def prompt(path, chs):
    rel = lambda p: os.path.relpath(p, ROOT)
    light = [c for c in chs if c not in FULL]
    plan_p = os.path.join(ROOT, "history", "weekly", os.path.basename(path)[:-5] + "_枠の案.json")
    hypo = os.path.join(ROOT, "history", "weekly", "枠の仮説.md")
    design = design_doc()
    docs = "\n".join(f"- {doc(ch, '手順書.md')}（{ch} の手順書。全部読む）" for ch in chs if ch in FULL)
    memos = "\n".join(f"- {rel(m)}（{ch} の競合メモ。research.py が毎日書く。§7〜9 の提案を 6 の改善案の材料にする）"
                      for ch in chs if ch in FULL for m in [os.path.join(ROOT, "history", ch, "competitors", "競合メモ.md")] if os.path.exists(m))
    if "job" in chs and os.path.exists(os.path.join(ROOT, "history", "job", "学び.md")):  # learn_job.py が毎日書く。6 の改善案は「続ける」になった試しを手順書に移す案にしてよい
        memos += f"\n- {rel(os.path.join(ROOT, 'history', 'job', '学び.md'))}（job の毎日の学び。learn_job.py が書く。「続ける」になった試しを手順書に移す案を 6 の材料にする）"
    learn = os.path.join(ROOT, "history", "psy", "学び.md")
    learn_spi = os.path.join(ROOT, "history", "spi", "学び.md")
    spi = "" if "spi" not in chs else f"""
## 千年こよみ（spi）について
- 本編は手で作る（週3〜4本。月・水・金・日 18:00）。判定会（2）は spi を別の1行で書く。型D と「早い見直し」は job だけ。
- 4 の表のあとに、ショートの種類ごと（teaser 予告・after 切り出し・solo 単独）と時刻ごと（11:15・19:15）の数字（本数・平均再生・平均視聴率・登録）を書く。
  つかみの文（hook）と上の帯の字（band）ごとの違いも書く（2本以上ある時だけ比べる）。来週の枠の空きが多い時は「今週あなたがやること」ではなく 7 に書く（作るのは Claude）。
- 最後に {rel(learn_spi)} を書き直す（30行まで。Claude Code が千年こよみの台本・ショートを書く前に毎回読む。手順書は変えない）：
  ・うちの回の数字から分かったことだけ。1行に1つ、根拠（回の名前と数字・何本中何本か）をつける。1本だけの傾向は書かない
  ・長尺（つかみ・章の引き・題とサムネの言葉）とショート（種類・時刻・つかみの文・帯の字）に分ける
  ・最後に「次の1週間で試すこと」を1つだけ書く（1度に変えるのは1つ。何を比べ、何本で判定するか）
  ・数字がまだ2本に満たない時は、前の {rel(learn_spi)} の行を残し、無ければ「まだ数字が足りない（{now().date().isoformat()}）」の1行だけにする
"""
    psy = "" if "psy" not in chs else f"""
## 心理学ch（psy）について
- 型の代わりに area（人づきあい・ひとりの時間・眠りと夜・幸せの心理）で比べる（数字の「型ごと」の名前が area）。型D と付録A の「早い見直し」は job だけ。
  判定会（2）は psy を別の1行で書く。公開から4週・8週・12週の線は付録A を当てはめてよい。
- 4 の表のあとに、ショートの area ごとの数字（本数・平均再生・平均視聴率・登録）と、つかみの文（hook）・上の帯の字（band）ごとの数字の違いを書く（2本以上ある時だけ比べる）。
- 最後に {rel(learn)} を書き直す（30行まで。これは毎日の台本の書き手が毎回読む。手順書は変えない）：
  ・うちの回の数字から分かったことだけ。1行に1つ、根拠（回の名前と数字・何本中何本か）をつける。1本だけの傾向は書かない
  ・長尺（つかみ・章の引き・タイトルとサムネの言葉の型・area）とショート（つかみの文・帯の字）に分ける
  ・手順書の決まりの中で守れることだけ（手順書とぶつかる事は書かず、6 の改善案に回す）
  ・数字がまだ2本に満たない時は、前の {rel(learn)} の行を残し、無ければ「まだ数字が足りない（{now().date().isoformat()}）」の1行だけにする
"""
    light_note = "" if not light else f"""
## {"・".join(light)} について
- このチャンネルは 3（健康）・4（数字）・8（時間帯）だけを書く。1・2・5・6・7 は job・psy・spi の分だけ書く（「今週あなたがやること」に入れるのは、止まり・予約の無い日だけ）。
"""
    return f"""あなたは YouTube の自動チャンネルの週報の書き手です。読む人はこの仕組みの持ち主で、専門用語が苦手です。日本語で、短い文で書きます。

## 先に全部読むファイル
- {rel(path)}（今週の数字。プログラムが集めた物。ここにない数字は書かない。あなたは割り算などの計算を最小限にし、した時はそう書く）
{docs}
- {rel(design) if os.path.exists(design) else '（設計書の写しは無い。下の線だけ使う）'}（§2 の週の流れ・§7 判定会・付録A の線）
{memos}

## 書く順（この順。見出しは ## で）
1. 今週あなたがやること（最大3行）：期限の「1か月以内」が true の物、来週の予約が無い日（審査前＝STOCK_PHASE が pre の時）、AIの申告がオフの回、
   クリック率が API で取れない時の「テストと比較」、固定データの照合の不一致、見張りや毎日の実行の止まり。無ければ「なし」。
   台本1本の冒頭（つかみと前置き、約240〜420字。手順書 §4）を直す作業も1行入れる（今週作った回から1本選び、channels/<ch>/videos/<work>/script.json の最初の数カットの text を貼る）。
2. 判定会の結論を1行：続ける／変える／止める のどれか。公開から4週・8週・12週の時は付録A の線に当てはめる。数字がまだ無い時は「判定は○週目から（今は数字の集まり待ち）」。
   型D の2本目の公開から14日目以降なら、付録A の「早い見直し」を当てはめる（型D とほかの型がそれぞれ2本以上公開されていない時は持ち越すと書く）。
3. 仕組みの健康状態を1行：毎日の実行と見張りの最後の実行時刻、在庫の本数、来週分の予約、今月の制作費（上限の何%か）。
4. 型ごとの数字（表）：本数・表示1,000回以上の本数・平均再生・クリック率・平均視聴率・1万回あたりの登録。
5. 伸びた回と伸びなかった回を、1文ずつ比べた違い（数字が2本以上ある時だけ）。
6. 改善案を1つ（手順書のどこを、どう書き換えるか。差し替えで勝った文言があれば「勝ちパターン」に足す案。競合メモの「手順書を変える案」と、
   今週作った回の competitor_note（競合メモから取り入れた物）の回の数字も材料にする。取り入れた回とそうでない回の差は、2本以上ずつある時だけ比べる）。「採用」か「見送り」をコメントで返すよう書き添える。
7. 細かいこと：差し替えた回、データ待ちで飛ばしているネタ帳の行、回した理由、コメントの状態、型の後回し。
8. 公開の時間帯と間隔（全チャンネル。数字の「時間帯」を使う）：
   ・チャンネルごとに、横・縦それぞれの表を出す（時刻ごと・その日の本数ごと・前後の間隔ごと。本数・再生の中央値・平均視聴率・1万回あたりの登録）。
     確定した数字（公開から6日後まで）だけを使う。「数字の状態」が「アナリティクス不可」のチャンネルはそう書いて、表は出さない。
   ・先に {rel(hypo)} を全部読み（無ければ新しく作る）、前の週に立てた仮説を今週の数字で確かめ、その行の後ろに「→ 確かめた日付：当たり／外れ／まだ分からない（根拠の数字）」を足す。
   ・今週の仮説を1チャンネル1つまで、{rel(hypo)} の最後に足す（「日付｜ch｜仮説｜比べる物｜何本で判定するか」の1行）。
     比べる群がそれぞれ3本以上ある時だけ仮説にする。足りない時は「数字待ち（あと何本）」と書くだけにする。中央値で比べ、平均だけが高い時（1本だけ跳ねた）は仮説にしない。
   ・数字が仮説を支える時だけ、枠の案を {rel(plan_p)} に JSON の一覧で書く（無ければ書かない）。形：
     [{{"ch": "psy", "key": "off", "to": ["07:10", "12:10", "21:10"], "根拠": "20:10 の縦4本の中央値 800 回、21:08 の縦3本の中央値 1,500 回", "比べた本数": "4本と3本"}}]
     key は on（横の日のショート）・off（横の無い日のショート）・extra_on・extra_off（在庫が多い日の足し）だけ。いまの枠は「枠（いま）」を見る。
     本数は今と同じにする。どの2本も3時間以上あけ、2本なら昼と夜、3本なら朝・昼・夜（朝は10時前・昼は16時前・夜はそれ以降）。横の時刻と予告（late）は案にせず、6 に書く。
     1チャンネル1件まで。「週次が直した記録」に14日以内の物があるチャンネルは、その結果を確かめるだけで案は出さない。
     案はプログラムが決まりを確かめてから枠に入れる（合わない案は見送られる）。入れた結果は週報の最後に足される。
{psy}{spi}{light_note}
## 決まり
- 水平線（--- など）は使わない。「—」「→」の多用もしない。
- 結果を約束しない。数字が少ない時は「まだ判定できない」と書く。
- 最後に、書いた週報の全文を history/weekly/{os.path.basename(path)[:-5]}.md に保存して終える。
"""


def main():
    a = argparse.ArgumentParser()
    a.add_argument("chs", nargs="+", choices=["job", "spi", "psy", "nihongi", "okinu", "kakure", "shimei"])
    a.add_argument("--no-issue", action="store_true")
    a = a.parse_args()
    os.environ["TZ"] = "Asia/Tokyo"
    wd = os.path.join(ROOT, "history", "weekly")
    os.makedirs(wd, exist_ok=True)
    path = os.path.join(wd, now().date().isoformat() + ".json")
    jsave(path, gather(a.chs))
    md = path[:-5] + ".md"
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_WRITER_MODEL", "opus"),
           "--allowedTools", "Read", "Write", "Glob", "Grep", "--permission-mode", "acceptEdits", "--output-format", "json"]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(path, a.chs), capture_output=True, text=True, encoding="utf-8", timeout=2700)
    ok = r.returncode == 0 and os.path.exists(md)
    if not ok:  # Claude が書けなかった週も、集めた数字だけで週報を出す（週報が8日ないの誤報を出さない）
        open(md, "w", encoding="utf-8").write("## 週報を Claude が書けませんでした\n今週の数字だけ置きます。PC で Claude Code にこの Issue を貼って「このIssueを直して」と言ってください。\n\n```json\n"
                                              + open(path, encoding="utf-8").read()[:60000] + "\n```\n")
    body = open(md, encoding="utf-8").read()
    try:  # Claude の枠の案を、決まりに合う物だけ枠に入れる（slot_apply.py）
        lines = slot_apply(path[:-5] + "_枠の案.json")
    except Exception as e:
        lines = [f"枠の自動の直しが止まりました：{e}"]
    body += "\n\n## 枠の自動の直し（slot_apply.py）\n" + "\n".join(f"- {x}" for x in lines) + \
            "\n- 効くのは次に予約する分から。戻す時は history/slot_plan.json のそのチャンネルの行を消す\n"
    open(md, "w", encoding="utf-8").write(body)
    title = f"週報 {now().date().isoformat()}"
    if a.no_issue or not shutil.which("gh") or not os.environ.get("GH_TOKEN"):
        print(f"（Issue にせず、{md} に置きました）")
    else:
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", body[:65000]])
    hp = os.path.join(ROOT, "history", "heartbeat.json")
    hb = jload(hp, {})
    hb["weekly"] = now().isoformat(timespec="seconds")
    jsave(hp, hb)
    ping("HC_WEEKLY", "" if ok else "/fail")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
