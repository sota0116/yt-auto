# 競合リサーチ（毎日 01:17 JST。research.yml）：競合の伸びている動画を YouTube から読み、Claude が「競合メモ」にまとめる
#   python -X utf8 pipeline\research.py job [--no-claude]
# ・読むだけ（YouTube に書かない・お金なし）。使う回数は1日 約650（検索6回×100＋ほか）。1日の上限 10,000 のうち、制作と見張りの残りで足りる
# ・見るのは channels\<ch>\competitors.json のチャンネル（最近の15本）と、検索の言葉（直近14日・再生の多い順25本ずつ）
# ・「伸びている」＝8分以上・公開30日以内で、そのチャンネルのふだんの再生（最近の回の真ん中の値）の2倍以上。
#   ふだんの再生が分からない検索の回は、再生が登録者の数以上。並びは1日あたりの再生の多い順。前の日の記録があれば24時間の増えも出す
# ・集めた物は history\<ch>\competitors\<日付>.json（題・数字・概要欄の頭とチャプターの行）。サムネは _research\（公開しない）に置き、Claude が見るだけ
# ・検索の上位に3日出たチャンネルは、次の日から見るチャンネルに足す（history\<ch>\competitors\auto_channels.json）
# ・まとめは Claude（claude -p）。鍵は渡さない（write_script.py と同じ分け方）。書くのは history\<ch>\competitors\競合メモ.md と、その日付の写し
#   台本の書き手（write_script.py）と週報（weekly.py）がこのメモを読む。借りるのは題材の傾向と型だけ。文・絵・サムネ・図は写さない
# ・心理学ch（psy。2026-10-27）は、題材の決まりを心理学の4つの area に替え、ネタの候補を ネタ候補.json にも書かせる。
#   ネタ帳の使っていない行が15行を切ったら、候補から1日5行まで channels\psy\ネタ帳.json に足す（ネタ帳が尽きて毎日の制作が止まらないように）
# ・--no-claude：集めるだけ（まとめない）
import argparse, datetime, json, os, re, shutil, statistics, subprocess, sys, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import jload, now, issue
from run_daily import jsave
from upload_job import api, API
from write_script import SECRET_ENV, doc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_SEC, MAX_DAYS, HOT_X, HOT_N, THUMB_N = 480, 30, 2.0, 30, 12
PSY_AREAS = ("人づきあい", "ひとりの時間", "眠りと夜", "幸せの心理")
NETA_LOW, NETA_ADD = 15, 5  # 心理学ch：ネタ帳の使っていない行がこれを切ったら、1日にこの行数まで足す


def get(ch, path, **q):
    return json.load(api(ch, "GET", f"{API}/{path}?" + urllib.parse.urlencode(q), timeout=60))


def seconds(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    d, h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0, 0)
    return d * 86400 + h * 3600 + mi * 60 + s


def chapters(desc):
    """概要欄のチャプターの行（0:00 つかみ のような行）だけ"""
    return [x.strip() for x in desc.splitlines() if re.match(r"\s*\(?\d{1,2}:\d{2}(:\d{2})?\)?\s", x)][:30]


def channel_list(ch, d):
    cfg = jload(os.path.join(ROOT, "channels", ch, "competitors.json"), {})
    auto = jload(os.path.join(d, "auto_channels.json"), [])
    cache_p = os.path.join(d, "channel_ids.json")
    cache = jload(cache_p, {})
    out, units = [], 0
    for c in cfg.get("channels", []) + cfg.get("auto", []) + auto:
        cid = c.get("id") or cache.get(c.get("handle"))
        if not cid and c.get("handle"):
            r = get(ch, "channels", part="id", forHandle=c["handle"])
            units += 1
            cid = (r.get("items") or [{}])[0].get("id")
            if cid:
                cache[c["handle"]] = cid
        if cid and cid not in {x["id"] for x in out}:
            out.append({"id": cid, "name": c.get("name"), "group": c.get("group")})
    jsave(cache_p, cache)
    return out, cfg.get("queries", []), units


def collect(ch, d):
    chans, queries, units = channel_list(ch, d)
    info = {}
    for i in range(0, len(chans), 50):
        r = get(ch, "channels", part="snippet,statistics,contentDetails", id=",".join(c["id"] for c in chans[i:i + 50]))
        units += 1
        for it in r.get("items", []):
            info[it["id"]] = it
    vids, src = [], {}
    for c in chans:
        it = info.get(c["id"])
        if not it:
            continue
        r = get(ch, "playlistItems", part="contentDetails", maxResults=15, playlistId=it["contentDetails"]["relatedPlaylists"]["uploads"])
        units += 1
        for x in r.get("items", []):
            vids.append(x["contentDetails"]["videoId"])
            src[x["contentDetails"]["videoId"]] = "見ているチャンネル"
    after = (now() - datetime.timedelta(days=14)).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for q in queries:
        r = get(ch, "search", part="id", type="video", q=q, regionCode="JP", relevanceLanguage="ja",
                publishedAfter=after, order="viewCount", maxResults=25)
        units += 100
        for x in r.get("items", []):
            v = x["id"]["videoId"]
            vids.append(v)
            src.setdefault(v, f"検索「{q}」")
    vids = list(dict.fromkeys(vids))
    rows = []
    for i in range(0, len(vids), 50):
        r = get(ch, "videos", part="snippet,statistics,contentDetails", id=",".join(vids[i:i + 50]))
        units += 1
        for it in r.get("items", []):
            sn, stt = it["snippet"], it.get("statistics", {})
            pub = datetime.datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            rows.append({"id": it["id"], "title": sn["title"], "channel_id": sn["channelId"], "channel": sn["channelTitle"],
                         "published": pub.astimezone(now().tzinfo).isoformat(timespec="minutes"),
                         "days": round(max((now() - pub).total_seconds() / 86400, 0.25), 2),
                         "sec": seconds(it["contentDetails"].get("duration")), "views": int(stt.get("viewCount", 0)),
                         "likes": int(stt.get("likeCount", 0)), "comments": int(stt.get("commentCount", 0)),
                         "desc_head": sn.get("description", "")[:300], "chapters": chapters(sn.get("description", "")),
                         "tags": sn.get("tags", [])[:15], "from": src.get(it["id"]),
                         "thumb": (sn.get("thumbnails", {}).get("medium") or {}).get("url")})
    others = {r["channel_id"] for r in rows} - set(info)
    others = list(others)
    for i in range(0, len(others), 50):
        r = get(ch, "channels", part="snippet,statistics", id=",".join(others[i:i + 50]))
        units += 1
        for it in r.get("items", []):
            info[it["id"]] = it
    return rows, info, units


def score(rows, info, d):
    """ふだんの再生（そのチャンネルの、公開3日より前の長い回の真ん中の値）と比べた倍率・1日あたりの再生・24時間の増え"""
    base = {}
    for r in rows:
        if r["sec"] >= MIN_SEC and r["days"] >= 3:
            base.setdefault(r["channel_id"], []).append(r["views"])
    prev = {}
    for f in sorted(x for x in os.listdir(d) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", x) and x[:10] != now().date().isoformat())[-1:]:
        prev = {v["id"]: v["views"] for v in jload(os.path.join(d, f), {}).get("videos", [])}
    for r in rows:
        b = base.get(r["channel_id"], [])
        r["usual"] = int(statistics.median(b)) if len(b) >= 4 else None
        r["x_usual"] = round(r["views"] / r["usual"], 1) if r["usual"] else None
        subs = int(info.get(r["channel_id"], {}).get("statistics", {}).get("subscriberCount", 0) or 0)
        r["subs"] = subs
        r["x_subs"] = round(r["views"] / subs, 2) if subs else None
        r["per_day"] = int(r["views"] / r["days"])
        r["gain_24h"] = r["views"] - prev[r["id"]] if r["id"] in prev else None
    hot = [r for r in rows if r["sec"] >= MIN_SEC and r["days"] <= MAX_DAYS and
           ((r["x_usual"] or 0) >= HOT_X or (r["x_usual"] is None and (r["x_subs"] or 0) >= 1))]
    hot.sort(key=lambda r: -r["per_day"])
    return hot[:HOT_N]


def auto_add(d, hot, info, watched):
    """検索で見つけたチャンネルが、伸びている回の一覧に3日出たら、次から見るチャンネルに足す"""
    seen_p, auto_p = os.path.join(d, "seen_channels.json"), os.path.join(d, "auto_channels.json")
    seen, auto = jload(seen_p, {}), jload(auto_p, [])
    today = now().date().isoformat()
    added = []
    for r in hot:
        c = r["channel_id"]
        if c in watched:
            continue
        days = seen.setdefault(c, [])
        if today not in days:
            days.append(today)
        if len(days) >= 3 and c not in {a["id"] for a in auto}:
            auto.append({"id": c, "name": r["channel"], "group": "自動で足した（検索の上位に3日）", "added": today})
            added.append(r["channel"])
    jsave(seen_p, seen)
    jsave(auto_p, auto)
    return added


def thumbs(ch, hot):
    out = os.path.join(ROOT, "_research", ch, now().date().isoformat())
    os.makedirs(out, exist_ok=True)
    got = []
    for r in hot[:THUMB_N]:
        if not r.get("thumb"):
            continue
        p = os.path.join(out, r["id"] + ".jpg")
        try:
            open(p, "wb").write(urllib.request.urlopen(r["thumb"], timeout=30).read())
            got.append(p)
        except Exception as e:
            print(f"  サムネを取れませんでした：{r['id']}（{type(e).__name__}）")
    return got


def prompt(ch, path, imgs, memo):
    rel = lambda p: os.path.relpath(p, ROOT).replace("\\", "/")
    own = [rel(os.path.join(ROOT, "history", ch, n)) for n in ("uploaded.json", "metrics.json", "produced.json")
           if os.path.exists(os.path.join(ROOT, "history", ch, n))]
    if ch == "psy":
        ex = "例「年を重ねて友だちが減る」「夜中の同じ時間に目が覚める」"
        neta = f"""手順書 §1 の area（{'・'.join(PSY_AREAS)}）のどれかに当てはまり、査読のある心理学の研究で説明できそうな題だけ。
   area と、手がかりになりそうな研究（著者・年。推測なら「推測」と書く）。うちのネタ帳 channels/psy/ネタ帳.json と、うちの記録にある題と同じ物は出さない。
   同じ候補を {rel(os.path.join(os.path.dirname(memo), 'ネタ候補.json'))} にも書く（全部を書き直す。JSON の配列。1つの形はネタ帳と同じ：
   {{"id": "p_英小文字と_", "area": "{PSY_AREAS[0]}", "title": "毎日の場面＋わけ（30字まで）", "scene": "60代の女性の毎日の1場面（1文）",
   "angle": "研究で言える切り口（1文）", "hint": "研究の手がかり", "competitor": "根拠の動画 id と再生"}}）"""
        off = """- 心理学と関係のない回（占い・スピ・政治・海外の反応・流行りの物など）は、2 の題材から外し、3〜6 の型の参考だけにする
- 心の病気の診断・治し方・薬・病院、発達の見分け方、効果の約束に寄る題材は、伸びていても「うちは使わない」と書く（手順書 §1）"""
    else:
        ex = "例「45歳以上のリストラ」「〇〇を辞める人が多い理由」"
        neta = "手順書の型（A〜D）に当てはまり、公的な統計で確かめられる題だけ。型と、確かめに使えそうな統計の名前（推測なら「推測」と書く）"
        off = """- うちの題材（仕事・年収・職場・働き方）に関係のない回（政治・海外の反応・流行りの物など）は、2 の題材から外し、3〜6 の型の参考だけにする
- 男女の対立・特定の国や人への攻撃・炎上をねらう題材は、伸びていても「うちは使わない」と書く"""
    return f"""あなたは YouTube チャンネルの競合リサーチの担当です。今日集めた競合の動画から、うちのタイトル・サムネ・概要欄・台本を良くする材料を「競合メモ」にまとめてください。
読むのは、このチャンネルの台本の書き手（AI）と週報です。日本語で、短い文で書きます。

## 先に全部読むファイル（部分読み禁止）
1. {doc(ch, '手順書.md')}（このチャンネルの決まりの正本。メモの提案は全部この決まりの中に収める）
2. {rel(path)}（今日集めた物。hot が伸びている回。数字はプログラムが YouTube から取った値。ここにない数字は書かない）
3. {rel(memo) if os.path.exists(memo) else '（前の競合メモは無い。今日が初回）'}（前の日までの競合メモ。続いている傾向は残し、消えた傾向は消す）
4. うちの記録：{'、'.join(own) or '（まだ無い）'}（うちの回のタイトルと数字。競合と比べる）
5. 伸びている回のサムネ（{len(imgs)}枚。ファイル名が動画の id）：{'、'.join(rel(p) for p in imgs) or '（取れなかった）'}

## 書く物：{rel(memo)}（全部を書き直す。150行まで。見出しは ## で、この順）
1. 今日の母数：見たチャンネルの数・動画の数・伸びている回の数（{rel(path)} の 母数 の値）と、日付
2. 伸びている題材：題材を一般化した言葉で（{ex}）。1行に1つ、根拠の動画 id と、再生・1日あたりの再生・ふだんの何倍か。5つまで
3. タイトルの部品：効いている部品を型にして書く（例「数字を頭に」「〇〇した結果…で結末を伏せる」「なぜ〇〇なのか」）。競合のタイトルの文はこのメモに写さない（動画 id で指す）。うちの手順書 §6 の決まりとぶつかる部品は「使えない」と書く
4. サムネの傾向：サムネの画像を見て、構図・文字の数・色・人物の有無・数字の有無。何枚中何枚かで書く
5. 概要欄の傾向：頭の文の型、チャプターの数と名前の付け方、リンクの置き方（desc_head と chapters から。何本中何本か）
6. 台本と構成の傾向：長さ（分）、チャプターの並び方（つかみ→…→結末）、章の数。何本中何本か
7. うちの次の回で試すこと（3つまで）：タイトル・サムネの文字・概要欄・台本のどれを、手順書の決まりの中でどう変えるか。1つずつ、根拠（動画 id と数字）と、手順書のどの決まりの中でやるかを書く。前のメモの提案で、うちの回が作られて数字が出た物は「結果」を1行足す
8. ネタの候補（5つまで）：{neta}
9. 手順書を変える案（あれば。自動では変えない。週報で持ち主が決める）

## 決まり
- 借りるのは題材の傾向と型だけ。競合の文・言い回し・絵・サムネ・図は写さない。実在の会社の名前は題材の例に使わない
- 数字は {rel(path)} の値だけ。割り算をした時は「計算」と書く。母数（何本中何本）を必ず添える。1本だけの傾向は「1本だけ」と書く
{off}
- 結果を約束しない。「伸びる」と言い切らず「〇本で伸びていた」と書く
- 水平線（--- など）は使わない。「—」「→」の多用もしない
- 最後に、書いた物と同じ全文を {rel(memo[:-3] + '_' + now().date().isoformat() + '.md')} にも保存して終える
"""


def main():
    a = argparse.ArgumentParser()
    a.add_argument("ch", choices=["job", "spi", "psy", "nihongi", "okinu"])
    a.add_argument("--no-claude", action="store_true")
    a = a.parse_args()
    os.environ["TZ"] = "Asia/Tokyo"
    d = os.path.join(ROOT, "history", a.ch, "competitors")
    os.makedirs(d, exist_ok=True)
    try:
        rows, info, units = collect(a.ch, d)
    except SystemExit as e:  # ログインが切れた（yt_auth.py が止めた）
        issue(f"【止まりました】{a.ch}：競合リサーチで YouTube のログインが切れた", str(e))
        raise
    hot = score(rows, info, d)
    watched = {c["id"] for c in channel_list(a.ch, d)[0]}
    added = auto_add(d, hot, info, watched)
    path = os.path.join(d, now().date().isoformat() + ".json")
    jsave(path, {"日付": now().isoformat(timespec="minutes"),
                 "母数": {"チャンネル": len(watched), "動画": len(rows), "伸びている回": len(hot)},
                 "使った回数": units, "足したチャンネル": added,
                 "線": f"{MIN_SEC // 60}分以上・公開{MAX_DAYS}日以内・ふだんの{HOT_X}倍以上（ふだんが分からない回は再生が登録者の数以上）",
                 "hot": hot, "videos": [{k: r[k] for k in ("id", "channel", "title", "views", "days", "sec")} for r in rows]})
    print(f"{a.ch}：動画 {len(rows)}本・伸びている回 {len(hot)}本・使った回数 {units}" + (f"・見るチャンネルに足した {added}" if added else ""))
    for r in hot[:5]:
        print(f"  {r['per_day']:>7,}/日 ×{r['x_usual'] or '?'} {r['channel']}：{r['title'][:40]}")
    if a.no_claude:
        return
    imgs = thumbs(a.ch, hot)
    memo = os.path.join(d, "競合メモ.md")
    before = os.path.getmtime(memo) if os.path.exists(memo) else 0
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_RESEARCH_MODEL", "opus"),
           "--allowedTools", "Read", "Write", "Glob", "Grep", "--permission-mode", "acceptEdits", "--output-format", "json"]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(a.ch, path, imgs, memo), capture_output=True, text=True,
                       encoding="utf-8", timeout=1800)
    open(os.path.join(ROOT, "_research", a.ch, "_claude.log"), "a", encoding="utf-8").write(r.stdout + "\n" + r.stderr + "\n")
    if r.returncode != 0 or not os.path.exists(memo) or os.path.getmtime(memo) <= before:
        issue(f"【止まりました】{a.ch}：競合メモを書けませんでした", f"{now():%m/%d %H:%M} 集めた物は {os.path.relpath(path, ROOT)} にあります。台本は前の競合メモで書きます")
        sys.exit(1)
    try:
        out = json.loads(r.stdout)
        print(f"競合メモを書きました（Claude：{out.get('num_turns')}手・{out.get('duration_ms', 0) / 60000:.1f}分）")
    except json.JSONDecodeError:
        print("競合メモを書きました")
    if a.ch == "psy":
        add_neta(a.ch, d)


def add_neta(ch, d):
    """心理学ch：ネタ帳の使っていない行が NETA_LOW を切ったら、競合メモのネタ候補から NETA_ADD 行まで足す（形の合わない候補は捨てる）"""
    bp = os.path.join(ROOT, "channels", ch, "ネタ帳.json")
    board = jload(bp, [])
    used = {p.get("neta_id") for p in jload(os.path.join(ROOT, "history", ch, "produced.json"), [])}
    free = sum(1 for r in board if r["id"] not in used)
    if free >= NETA_LOW:
        print(f"ネタ帳の残り {free}行（{NETA_LOW}行以上あるので足さない）")
        return
    ids, titles = {r["id"] for r in board}, {r["title"] for r in board}
    new = []
    for c in jload(os.path.join(d, "ネタ候補.json"), []):
        ok = isinstance(c, dict) and re.fullmatch(r"p_[a-z0-9_]{3,40}", str(c.get("id"))) and c.get("area") in PSY_AREAS \
            and all(isinstance(c.get(k), str) and c[k].strip() for k in ("title", "scene", "angle", "hint"))
        if ok and c["id"] not in ids and c["title"] not in titles and len(new) < NETA_ADD:
            new.append({k: c.get(k, "") for k in ("id", "area", "title", "scene", "angle", "hint", "competitor")}
                       | {"added": now().date().isoformat(), "from": "競合リサーチ"})
            ids.add(c["id"]); titles.add(c["title"])
    if new:
        jsave(bp, board + new)
    print(f"ネタ帳の残り {free}行 → 競合リサーチの候補から {len(new)}行足しました：{[x['title'] for x in new]}")


if __name__ == "__main__":
    main()
