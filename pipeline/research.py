# 競合リサーチ（毎日 01:17 JST。research.yml）：競合の伸びている動画を YouTube から読み、Claude が「競合メモ」にまとめる
#   python -X utf8 pipeline\research.py job [--no-claude]
# ・読むだけ（YouTube に書かない・お金なし）。使う回数は1日 約650（検索6回×100＋ほか）。1日の上限 10,000 のうち、制作と見張りの残りで足りる
# ・見るのは channels\<ch>\competitors.json のチャンネル（最近の15本）と、検索の言葉（直近14日・再生の多い順25本ずつ）
# ・「伸びている」＝8分以上・公開30日以内で、そのチャンネルのふだんの再生（最近の回の真ん中の値）の2倍以上。
#   ふだんの再生が分からない検索の回は、再生が登録者の数以上。並びは1日あたりの再生の多い順。前の日の記録があれば24時間の増えも出す
# ・集めた物は history\<ch>\competitors\<日付>.json（題・数字・概要欄の頭とチャプターの行）。サムネは _research\（公開しない）に置き、Claude が見るだけ
# ・検索の上位に3日出たチャンネルは、次の日から見るチャンネルに足す（history\<ch>\competitors\auto_channels.json）
# ・まとめは Claude（claude -p）。鍵は渡さない（write_script.py と同じ分け方）。書くのは history\<ch>\competitors\競合メモ.md と、その日付の写し
#   台本の書き手（write_script.py）と週報（weekly.py）がこのメモを読む。借りるのは題材・ネタ・骨格（章の並び・つかみと題の型）。文・絵・サムネ・図は写さない
#   2026-11-12 本人「題材やネタや台本の骨格は、オリジナリティを出さず、競合や伸びているのをTTPする」：メモは伸びた回の形をそのまま出し、独自の切り口の提案を足さない
# ・金運おきぬ（okinu）は 2026-11-13 に専用の文を足した（それまで job の文＝仕事・年収・公的な統計で書かせていた）
# ・心理学ch（psy。2026-10-27）は、題材の決まりを心理学の4つの area に替え、ネタの候補を ネタ候補.json にも書かせる。
#   ネタ帳の使っていない行が15行を切ったら、候補から1日5行まで channels\psy\ネタ帳.json に足す（ネタ帳が尽きて毎日の制作が止まらないように）
# ・金運おきぬ（okinu。2026-11-17）も、ショートのネタの候補を ネタ候補.json に書かせ、ショートの使っていない行が8行を切ったら1日5行まで
#   channels\okinu\ネタ帳.json の rows に足す（本人「なんで俺がやるんだよ」：ネタ帳の補充を人に頼まない）。job は refill_job_neta.py が統計から足す
# ・spi は 2026-11-11 から翠仙（白蛇弁財天の金運祈祷）。手順書がまだ無いので、決まりは SPI_RULES に書く。competitors.json の own（うちのチャンネル）は見るチャンネルに足さない
# ・2026-11-17 本人「Gemini でパワーアップ」：伸びた回の中身を Gemini（無料キー GEMINI_API_KEY_FREE）に URL のまま見せ、
#   冒頭の拍・章・締め・画面を history\<ch>\competitors\見た\<動画id>.json に置く（watch()）。1チャンネル1日 WATCH_N 本まで・見た回は見直さない。
#   それまでは題・概要欄・サムネしか見られず、チャプターの無い回の並びは分からなかった。リポジトリが公開なので、語りの文は写させず役割と要約だけ書かせる。
#   鍵が無い・1日の上限・見られない回は飛ばして、競合メモはいつもどおり書く
# ・--no-claude：集めるだけ（まとめない。Gemini で見るのはやる）
import argparse, datetime, json, os, re, shutil, statistics, subprocess, sys, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import jload, now, issue
from run_daily import jsave
from upload_job import api, API
from write_script import SECRET_ENV, doc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_SEC, MAX_DAYS, HOT_X, HOT_N, THUMB_N = 480, 30, 2.0, 30, 12
PSY_AREAS = ("人づきあい", "ひとりの時間", "眠りと夜", "幸せの心理")
SPI_RULES = """翠仙（白蛇弁財天の金運祈祷）の決まり（手順書がまだ無いので、これが正本）
- 題は受け取り型（「見れた」「表示された」「届く」「選ばれた」など）と前兆。白蛇・弁財天・金運・開運日（巳の日・一粒万倍日・寅の日など）
- 長さは12〜20分。出口は LINE の無料鑑定
- 競合で伸びている型をそのまま使う。変わった切り口や隙間を足さない
- 収入や効果を約束しない・言い切らない。恐怖で煽らない。他の宗教や人を悪く言わない"""
NETA_LOW, NETA_ADD = 15, 5  # 心理学ch：ネタ帳の使っていない行がこれを切ったら、1日にこの行数まで足す
WATCH_N, WATCH_MAX_SEC = 2, 40 * 60  # Gemini に見せる伸びた回：1チャンネル1日2本まで・40分以下（無料枠の1日の上限に収める）
WATCH_Q = """添付の YouTube 動画を最初から最後まで見て（聞いて）、構成の骨格を取り出してください。章の並びとつかみの型を知るためです。
- 語りの文をそのまま書き写さない（このメモは公開の場所に置く）。何をしているかを短い言葉に要約する
- 冒頭の拍：最初の90秒で、何秒に何の役割（例：結論の先出し・自己紹介・問いかけ・掛け合い・予告・体験談）をしているか
- 章：始まりの秒・役割・中身（1行）。概要欄にチャプターが無くても、話の切れ目で分ける
- 締め：最後の60秒で何を促しているか（登録・コメント・LINE・商品など）
- 語りの形：1人語り／掛け合い／読み上げソフト など。画面：どんな絵・字幕・動きで見せているか（2〜3行）"""
WATCH_SCH = {"type": "object", "properties": {
    "語りの形": {"type": "string"},
    "冒頭の拍": {"type": "array", "items": {"type": "object", "properties": {
        "秒": {"type": "number"}, "役割": {"type": "string"}, "中身": {"type": "string"}}, "required": ["秒", "役割", "中身"]}},
    "章": {"type": "array", "items": {"type": "object", "properties": {
        "秒": {"type": "number"}, "役割": {"type": "string"}, "中身": {"type": "string"}}, "required": ["秒", "役割", "中身"]}},
    "締め": {"type": "string"}, "画面": {"type": "string"}},
    "required": ["語りの形", "冒頭の拍", "章", "締め", "画面"]}
OKINU_LOW, OKINU_ADD = 8, 5  # 金運おきぬ：ショートの使っていない行がこれを切ったら、1日にこの行数まで足す


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
        try:
            r = get(ch, "playlistItems", part="contentDetails", maxResults=15, playlistId=it["contentDetails"]["relatedPlaylists"]["uploads"])
        except Exception as e:  # 動画を全部消したチャンネルは 404 になる（2026-11-13：1つのチャンネルで spi のリサーチ全体が落ちた）
            print(f"  {c.get('name') or c['id']}：最近の動画を読めないので飛ばします（{type(e).__name__} {e}）")
            continue
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


def watch(ch, hot, d):
    """伸びた回の中身を Gemini（無料キー）に URL のまま見せ、骨格を 見た\\<id>.json に置く。今日の hot で見終わっている物の場所を返す。
    見るのは「見ているチャンネル」の回を先に、1日あたりの再生の多い順。止まっても競合メモは書く（鍵が無い・上限なら残りを飛ばす）"""
    import gemini
    out = os.path.join(d, "見た")
    os.makedirs(out, exist_ok=True)
    got, new = [], 0
    for r in sorted((r for r in hot if r["sec"] <= WATCH_MAX_SEC), key=lambda r: (r["from"] != "見ているチャンネル", -r["per_day"])):
        p = os.path.join(out, r["id"] + ".json")
        if os.path.exists(p):
            got.append(p)
            continue
        if new >= WATCH_N:
            continue
        try:
            # 長さを書かないと、26分の回で章の秒が42分まで伸びた（2026-11-17 の試し）。長さを伝え、超えた時は「秒は不確か」と印を付ける
            q = WATCH_Q + f"\n\nこの動画の長さは {r['sec'] // 60}分{r['sec'] % 60}秒（{r['sec']}秒）です。秒はこの長さの中で、実際に見た位置を書く。"
            t, u = gemini.ask_media(q, youtube=["https://www.youtube.com/watch?v=" + r["id"]], schema=WATCH_SCH, low_res=True)
            j = json.loads(t)
            top = max([x["秒"] for x in j["章"] + j["冒頭の拍"]] or [0])
            jsave(p, {"id": r["id"], "channel": r["channel"], "sec": r["sec"], "見た日": now().date().isoformat(),
                      "トークン": u.get("totalTokenCount")}
                  | ({"秒は不確か": f"答えの秒が動画の長さを超えた（最大 {top}秒・長さ {r['sec']}秒）。章の順番と中身だけを使う"}
                     if top > r["sec"] * 1.05 else {}) | j)
            got.append(p)
            new += 1
            print(f"  Gemini で見ました：{r['id']}（{r['sec'] // 60}分・{u.get('totalTokenCount')}トークン）")
        except SystemExit as e:
            print(f"  Gemini で見られませんでした：{r['id']}（{e}）")
            if e.code == gemini.QUOTA_DAY or "見つかりません" in str(e):  # 1日の上限・鍵が無い：残りも通らない
                break
        except (ValueError, KeyError, OSError) as e:  # 答えが JSON でない・通信が切れた：この回だけ飛ばす
            print(f"  Gemini で見られませんでした：{r['id']}（{type(e).__name__}）")
    return got


def prompt(ch, path, imgs, memo, seen=()):
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
    elif ch == "nihongi":  # 2026-11-04：それまで job の文（仕事・年収）で書かせていた
        ex = "例「もしも江戸の〇〇に生まれたら」「戦国の〇〇の謎」「〇〇を今のお金に直すと」"
        neta = """伸びている回と同じ題材・同じ見せ方で、史実の土台を史料や通説で確かめられる題だけ（独自の切り口を足さない）。根拠の動画 id と、
   手順書 §2 のずらし方（反転・見える化＋1人だけ異常値・制限・翻訳・時代ワープ・極端化・心を持たせる）のどれに当たるか
   （当たる物を先に並べる。当たらない物は外さず「当たらない」と書いて後ろに置く）と、時代（手順書 §2 の時代配分：江戸5〜6割・戦国2〜3割・幕末1〜2割）と、
   確かめに使えそうな史料・本の名前（推測なら「推測」と書く）"""
        off = """- 日本史と関係のない回（外国の歴史・宗教・今の国の話・流行りの物など）は、2 の題材から外し、3〜6 の型の参考だけにする
- 手順書 §4 の使わない題材（昭和の戦争の死者・被害を笑いにする物、実在の人の性・病気・民族を笑いの種にする物、今も遺族や関係者がいる近現代の事件）と、
  今の国や実在の集団を扱う「もしも」は、伸びていても「うちは使わない」と書く"""
    elif ch == "spi":  # 2026-11-11：千年こよみ（星占い）から翠仙へ。それまで job の文（仕事・年収）で書かせていた
        ex = "例「白蛇が夢に出る前兆」「この動画が表示された方へ」「巳の日の金運」"
        neta = """白蛇・弁財天・金運・開運日（巳の日・一粒万倍日・寅の日など）の、受け取り型か前兆型の題だけ。
   型（受け取り型・前兆型・開運日・祈祷）と、根拠の動画 id。うちの記録にある題と同じ物は出さない"""
        off = """- 金運・白蛇・弁財天・開運と関係のない回（星座ごとの運勢・恋愛だけ・政治・流行りの物など）は、2 の題材から外し、3〜6 の型の参考だけにする
- 顔を出して1人が語る型、収入や効果を約束・断定する題、恐怖で煽る題、他の宗教や人を攻撃する題は、伸びていても「うちは使わない」と書く"""
    elif ch == "okinu":  # 2026-11-13：それまで job の文（仕事・年収・公的な統計）で書かせていた
        ex = "例「玄関に置くとお金が逃げる物」「財布に入れてはいけない物」「トイレの NG」"
        neta = f"""伸びている回と同じ場所・同じ物の NG を先に出す（独自の切り口を足さない）。場所か小物（財布・玄関・台所・トイレ・寝室・かばん など）と、
   手順書 §8 の題の型（A〜F）のどれに当たるかと、根拠の動画 id。お金のかからない・手元の物で直せる話だけ。
   うちの記録にある場所と NG の組み合わせと同じ物は出さない。
   ほかに、ショートにできる候補を {rel(os.path.join(os.path.dirname(memo), 'ネタ候補.json'))} にも書く（全部を書き直す。JSON の配列。8つまで。
   型1 を4つ以上、型2 を2つ以上）。先に channels/okinu/ネタ帳.json を全部読み（_説明・_行の項目・rows・手で作った回）、
   rows の小物・題・items と、手で作った回の小物と、うちの記録の題と同じ物・言い換えただけの物は出さない。1つの形：
   型1（NG3つの数え下げ）{{"id": "s1_英小文字と_", "kind": "short", "型": 1, "題": "〇〇に置くとお金が逃げる物3選 の形", "items": ["NG1", "NG2", "NG3"],
   "小物": "題と同じ文字", "悩み": "〜しているのに、お金が残らない の形の1文", "年": 60〜69 の数, "ok_q": "〇〇を、〇〇していいか", "competitor": "根拠の動画 id と再生"}}
   型2（1つだけ禁止）{{"id": "s2_英小文字と_", "kind": "short", "型": 2, "小物": "小物か行為1つ", "悩み": "同じ形の1文", "年": 60〜69 の数,
   "ok_q": "〇〇を、〇〇していいか", "competitor": "根拠の動画 id と再生"}}"""
        off = """- 金運・開運・暮らしの言い伝えと関係のない回（政治・海外の反応・投資や節約の助言・流行りの物など）は、2 の題材から外し、3〜6 の型の参考だけにする
- 手順書 §1 の使わない語（宝くじ・億・借金・一発逆転・N秒以内に）に寄る題材、高い商品を前提にする題材、暮らしへの脅しは、伸びていても「うちは使わない」と書く"""
    else:
        ex = "例「45歳以上のリストラ」「〇〇を辞める人が多い理由」"
        neta = """伸びている回と同じ題材で、公的な統計で確かめられる題だけ（独自の切り口を足さない）。根拠の動画 id と、
   手順書の型（A〜D）のどれに当たるか（当たる物を先に並べる。当たらない物は外さず「当たらない」と書いて後ろに置く）と、
   確かめに使えそうな統計の名前（推測なら「推測」と書く）"""
        off = """- うちの題材（仕事・年収・職場・働き方）に関係のない回（政治・海外の反応・流行りの物など）は、2 の題材から外し、3〜6 の型の参考だけにする
- 男女の対立・特定の国や人への攻撃・炎上をねらう題材は、伸びていても「うちは使わない」と書く"""
    rules = SPI_RULES if ch == "spi" else f"{doc(ch, '手順書.md')}（このチャンネルの決まりの正本。事実確認・使わない題材・禁止表現・安全の決まりは必ず守る。題材・ネタ・章の並び・つかみと題の型は、伸びた回の形を曲げずにそのまま書き、手順書の自作の型と食い違う所は 9 に書く）"
    sec6 = "上の翠仙の決まり" if ch == "spi" else "うちの手順書 §6 の決まり"
    return f"""あなたは YouTube チャンネルの競合リサーチの担当です。今日集めた競合の動画から、うちのタイトル・サムネ・概要欄・台本を良くする材料を「競合メモ」にまとめてください。
読むのは、このチャンネルの台本の書き手（AI）と週報です。日本語で、短い文で書きます。

## 先に全部読むファイル（部分読み禁止）
1. {rules}
2. {rel(path)}（今日集めた物。hot が伸びている回。数字はプログラムが YouTube から取った値。ここにない数字は書かない）
3. {rel(memo) if os.path.exists(memo) else '（前の競合メモは無い。今日が初回）'}（前の日までの競合メモ。続いている傾向は残し、消えた傾向は消す）
4. うちの記録：{'、'.join(own) or '（まだ無い）'}（うちの回のタイトルと数字。競合と比べる）
5. 伸びている回のサムネ（{len(imgs)}枚。ファイル名が動画の id）：{'、'.join(rel(p) for p in imgs) or '（取れなかった）'}
6. Gemini が動画を実際に見て取った、伸びた回の骨格（{len(seen)}本。ファイル名が動画の id。冒頭の拍・章・締め・画面）：{'、'.join(rel(p) for p in seen) or '（今日は無い）'}

## 書く物：{rel(memo)}（全部を書き直す。150行まで。見出しは ## で、この順）
1. 今日の母数：見たチャンネルの数・動画の数・伸びている回の数（{rel(path)} の 母数 の値）と、日付
2. 伸びている題材：題材を一般化した言葉で（{ex}）。1行に1つ、根拠の動画 id と、再生・1日あたりの再生・ふだんの何倍か。うちが同じ題材でやれるか（やれる／決まりで使えない）も1語で。5つまで
3. タイトルの部品：効いている部品を型にして書く（例「数字を頭に」「〇〇した結果…で結末を伏せる」「なぜ〇〇なのか」）。競合のタイトルの文はこのメモに写さない（動画 id で指す）。{sec6}とぶつかる部品は「使えない」と書く
4. サムネの傾向：サムネの画像を見て、構図・文字の数・色・人物の有無・数字の有無。何枚中何枚かで書く
5. 概要欄の傾向：頭の文の型、チャプターの数と名前の付け方、リンクの置き方（desc_head と chapters から。何本中何本か）
6. 台本と構成の傾向：長さ（分）、チャプターの並び方（つかみ→…→結末）、章の数。何本中何本か。
   チャプターがあるか Gemini が見た伸びた回は、1日あたりの再生の多い順に3本まで、動画 id と章の並びを1本ずつ書く（章ごとの役割が分かる言葉で、順番と数は変えない。うちの書き手がこの並びをそのまま借りる）。
   Gemini が見た回は、冒頭90秒の拍（何秒に何の役割）と締めも1行ずつ添え、「Gemini が見た」と書く。
   チャプターが無く Gemini も見ていない回の並びは推測で作らない（「チャプターなし」と書く）
7. うちの次の回で試すこと（3つまで）：タイトル・サムネの文字・概要欄・台本のどれを、{"決まり" if ch == "spi" else "手順書の決まり（事実確認・使わない題材・禁止表現・点検）"}の中で、伸びた回の形にどう寄せるか。新しい工夫を考えず、伸びた回が実際にやっている形から選ぶ。1つずつ、根拠（動画 id と数字）と、{"どの決まり" if ch == "spi" else "手順書のどの決まり"}の中でやるかを書く。前のメモの提案で、うちの回が作られて数字が出た物は「結果」を1行足す
8. ネタの候補（5つまで。2 の伸びている題材と同じ題材を、うちの決まりの中でやる候補。新しい切り口・誰もやっていない隙間ねらいを足さない）：{neta}
9. {"決まりを変える案・手順書に入れる案" if ch == "spi" else "手順書を変える案"}（あれば。自動では変えない。週報で持ち主が決める）

## 決まり
- 借りるのは題材・ネタ・骨格（章の並び・つかみの型・題の型）。伸びた回が実際にやっている形をそのまま出し、独自の切り口・隙間ねらいの提案を足さない（2026-11-12 本人）
- 競合の文・言い回し・絵・サムネ・図は写さない。実在の会社の名前は題材の例に使わない
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
    own = jload(os.path.join(ROOT, "channels", a.ch, "competitors.json"), {}).get("own")
    added = auto_add(d, hot, info, watched | ({own} if own else set()))  # うちのチャンネルは競合に足さない
    path = os.path.join(d, now().date().isoformat() + ".json")
    jsave(path, {"日付": now().isoformat(timespec="minutes"),
                 "母数": {"チャンネル": len(watched), "動画": len(rows), "伸びている回": len(hot)},
                 "使った回数": units, "足したチャンネル": added,
                 "線": f"{MIN_SEC // 60}分以上・公開{MAX_DAYS}日以内・ふだんの{HOT_X}倍以上（ふだんが分からない回は再生が登録者の数以上）",
                 "hot": hot, "videos": [{k: r[k] for k in ("id", "channel", "title", "views", "days", "sec")} for r in rows]})
    print(f"{a.ch}：動画 {len(rows)}本・伸びている回 {len(hot)}本・使った回数 {units}" + (f"・見るチャンネルに足した {added}" if added else ""))
    for r in hot[:5]:
        print(f"  {r['per_day']:>7,}/日 ×{r['x_usual'] or '?'} {r['channel']}：{r['title'][:40]}")
    seen = watch(a.ch, hot, d)
    if a.no_claude:
        return
    imgs = thumbs(a.ch, hot)
    memo = os.path.join(d, "競合メモ.md")
    before = os.path.getmtime(memo) if os.path.exists(memo) else 0
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_RESEARCH_MODEL", "opus"),
           "--allowedTools", "Read", "Write", "Glob", "Grep", "--permission-mode", "acceptEdits", "--output-format", "json"]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(a.ch, path, imgs, memo, seen), capture_output=True, text=True,
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
    elif a.ch == "okinu":
        add_neta_okinu(d)


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


def add_neta_okinu(d):
    """金運おきぬ：ショートの使っていない行が OKINU_LOW を切ったら、ネタ候補.json から OKINU_ADD 行まで rows に足す（形の合わない候補・重なる候補は捨てる）。
    使った行の数え方は pick_neta_okinu.py に合わせる（作った回・作る予定の回・作業フォルダ・used_by・hold・手で作った回の小物）"""
    hp = lambda n: os.path.join(ROOT, "history", "okinu", n)
    bp = os.path.join(ROOT, "channels", "okinu", "ネタ帳.json")
    book = jload(bp, {})
    rows = book.get("rows", [])
    hand = " ".join(book.get("手で作った回", {}).values())
    used = {x.get("neta_id") or x.get("id") for x in jload(hp("produced.json"), []) if isinstance(x, dict)}
    used |= {v.get("neta_id") for v in jload(hp("pub_plan.json"), {}).values() if isinstance(v, dict)}
    vdir = os.path.join(ROOT, "channels", "okinu", "videos")
    for w in os.listdir(vdir) if os.path.isdir(vdir) else []:
        x = jload(os.path.join(vdir, w, "neta.json"), {})
        used |= {x.get("neta_id"), x.get("id")}
    free = [r for r in rows if r.get("kind") == "short" and not r.get("hold") and not r.get("used_by")
            and r["id"] not in used and r.get("小物", "") not in hand]
    if len(free) >= OKINU_LOW:
        print(f"okinu のネタ帳：ショートの残り {len(free)}行（{OKINU_LOW}行以上あるので足さない）")
        return
    ids = {r["id"] for r in rows}
    seen = {r.get(k) for r in rows for k in ("小物", "題") if r.get(k)} | {i for r in rows for i in r.get("items", [])}
    s = lambda v: isinstance(v, str) and v.strip()
    new = []
    for c in jload(os.path.join(d, "ネタ候補.json"), []):
        if len(new) >= OKINU_ADD or not isinstance(c, dict):
            continue
        t = c.get("型")
        ok = t in (1, 2) and c.get("kind") == "short" and re.fullmatch(rf"s{t}_[a-z0-9_]{{3,40}}", str(c.get("id"))) \
            and all(s(c.get(k)) for k in ("小物", "悩み", "ok_q")) and isinstance(c.get("年"), int) and 55 <= c["年"] <= 75
        if ok and t == 1:
            ok = s(c.get("題")) and isinstance(c.get("items"), list) and len(c["items"]) == 3 and all(s(i) for i in c["items"])
        if not ok or c["id"] in ids or c["小物"] in seen or c["小物"] in hand or (t == 1 and (c["題"] in seen or any(i in seen for i in c["items"]))):
            continue
        keys = ("id", "kind", "型", "題", "items", "小物", "悩み", "年", "ok_q", "competitor") if t == 1 else ("id", "kind", "型", "小物", "悩み", "年", "ok_q", "competitor")
        new.append({k: c[k] for k in keys if k in c} | {"added": now().date().isoformat(), "from": "競合リサーチ"})
        ids.add(c["id"]); seen |= {c["小物"], c.get("題")} | set(c.get("items", []))
    if new:
        book["rows"] = rows + new
        jsave(bp, book)
    print(f"okinu のネタ帳：ショートの残り {len(free)}行 → 競合リサーチの候補から {len(new)}行足しました：{[x['小物'] for x in new]}")


if __name__ == "__main__":
    main()
