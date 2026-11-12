# ①ネタ（アナザー日本紀・2026-10-29 新設。千年こよみ pick_neta_spi.py と同じ形：作業フォルダを作り、最後の行にそのパスを出す）
#   python -X utf8 pipeline/pick_neta_nihongi.py nihongi --kind short|long [--dry]
# ・ショート（short）：channels/nihongi/ネタ帳.json の rows と history/nihongi/ネタ補充.json（この道具が claude -p で足す）の使っていない行から1つ選ぶ。
#   選び方（制作ルール §2）：①前のショートと同じずらし方は選ばない（2本続けない） ②『へえ』の主役の史実を過去に使った回と同じにしない
#   ③時代の配分（江戸5〜6割・戦国2〜3割・幕末1〜2割）に直近10本がいちばん足りない時代の行を先に ④直近4本で使っていないずらし方を先に
#   使っていない行が3つ以下になったら、先に claude -p（WebSearch で史実を確かめる）で10行を足す
# ・2026-11-07（手順書 v2.5 §2）：ずらし方の主力を「見える化＋1人だけ異常値」「時代ワープ」の2つにした。①②の次に、主力を先に選ぶ（主力以外は直近7本に1本まで。
#   主力の行が無ければ主力以外でも選ぶ）。前のショートと違う主力の行が切れていたら、その行を多めに補充する。③④はその次
# ・横動画（long）：2026-11-12（手順書 v2.6 §7）から2つの出どころ。直近2本の横動画が両方『分かれ道』でなければ『分かれ道』（ネタ帳.json の long_rows →
#   history/nihongi/ネタ補充_横.json の使っていない行を上から。2行以下になったら claude -p で6行足す）。両方『分かれ道』なら伸びたショートから。選んだ方が無ければもう一方。
#   伸びたショートから：公開済み（または予約済み）のショートのうち、まだ横動画にしていない1本を選ぶ（再生が多い順。数字がまだ無ければ番号の若い順）。
#   手で作った S001〜S005 は L001・L002 に入っているので選ばない（ネタ帳.json の long_done_from）。企画・ずらし方・時代・史実は元のショートと同じ
# ・2026-11-12（手順書 v2.7。本人「昭和も扱っていこう」）：昭和を時代に入れた。昭和の『分かれ道』は横動画の直近4本に1本まで（直近3本に昭和があれば
#   昭和でない行を選ぶ。昭和でない行が無ければ伸びたショートへ回す）。ショートでは戦争そのものをずらしの種にしない（戦争ではない昭和はよい）
# ・番号：毎日の制作が作る回は S101・L101 から（手で作った S001〜S010・L001〜L002 と衝突しない）。作業フォルダは channels/nihongi/videos/S101_<ネタの id>
# ・neta.json（kind・no・企画・distort・era・fact_main・from_short など）を作業フォルダに置く。run_daily.py の record() が履歴に写す
import argparse, datetime as dt, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nihongi_common import (ROOT, CH, CDIR, HIST, VDIR, jload, jsave, book, refill_rows, past_works, number_key, claude_env)  # noqa: E402
import ustore  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))
REFILL_AT = 3  # 使っていない行がこの数以下なら、先に補充する
# 主力のずらし方（2026-11-07 手順書 v2.5 §2。本人「わかりづらくなってる」。S110 寿司＝時代ワープ 6911回・S001 裏切り確率＝見える化 3201回）。
# 残りの5つは、直近7本のショートに1本まで（7本の中に既にあれば後回し。主力の行が無い時は選んでよい＝止めない）
MAIN = ("見える化＋1人だけ異常値", "時代ワープ")
# 横動画の『分かれ道』（2026-11-12 手順書 v2.6 §7。本人「変えることはしっかり変えて」）。史実の1つの出来事・決断を逆にする『もしも』は検索される量が多い
#（本能寺の変がなかったら・関ヶ原で西軍が勝っていたら など）。横動画の3本のうち2本をこれにし、残り1本は今までどおり伸びたショートから作る
LONG_IF = "分かれ道"
LONG_REFILL_AT = 2  # 使っていない『分かれ道』の行がこの数以下なら、先に補充する
SHOWA = "昭和"
SHOWA_EVERY = 4  # 昭和の『分かれ道』は横動画の直近4本に1本まで（2026-11-12 手順書 v2.7 §7。本人「昭和も扱っていこう」）
# 2026-11-12 本人「題材やネタや台本の骨格は、オリジナリティを出さず、競合や伸びているのをTTPする」：ネタの補充は、競合メモの伸びた題材を先に行にする。
# ずらし方の配分・主力の上限・昭和の上限・史実の検品（下のコード）は変えていない
TTP_NETA = ("次に history/nihongi/competitors/競合メモ.md を最後の行まで読み、「伸びている題材」「ネタの候補」と同じ題材・同じ出来事を先に行にしてください。"
            "独自の切り口・誰もやっていない隙間ねらいは足さない（競合の文と題の言葉は写さない）。史実の確かめ・手順書 §4 の使わない題材・下の決まりが先です。"
            if os.path.exists(os.path.join(HIST, "competitors", "競合メモ.md"))
            else "（競合メモがまだ無いので、手順書と下の決まりだけで作る。競合の伸びた題材を推測で作らない）")


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def used_facts(past):
    return [x.get("fact_main") for x in past if x.get("fact_main")]


def same_fact(a, b):
    """『へえ』の主役の史実が同じか。語の並びが大きく重なるか、片方がもう片方を含む"""
    if not a or not b:
        return False
    A, B = re.sub(r"\s", "", a), re.sub(r"\s", "", b)
    if A in B or B in A:
        return True
    tri = lambda t: {t[i:i + 3] for i in range(len(t) - 2)}
    ta, tb = tri(A), tri(B)
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.5


def is_main(distort):
    return any(m in (distort or "") for m in MAIN)


def refill(rows, past, n=10, need=""):
    """claude -p で新しい行を足す（使っていない行が少なくなった時・主力のずらし方の行が切れた時）。WebSearch で史実を確かめさせる。足せなかったら何もしない"""
    book_ = book()
    p = f"""あなたは YouTube チャンネル「アナザー日本紀」（歴史に、ありえないルールを1つだけ足して、史実が少しだけひっくり返る『もしも歴史』のショート）の企画係です。
先に channels/nihongi/手順書.md の §0〜§4 と §10 を最後の行まで読んでください。
{TTP_NETA}
次の{n}行を作り、最後に JSON の配列だけを出力してください（前後の説明は不要）。
各行：{{"id": "R<連番>", "企画": "もしも〜（1文）", "distort": "{'／'.join(book_.get('distorts', []))} のどれか1つ", "era": "江戸／戦国／幕末／平安／昭和／その他", "fact_main": "『へえ』の主役の史実（年・人・場所が入る1文）", "note": "調べた出どころ（URL か資料名）とオチの方向"}}
決まり
- 道具を置くだけの企画は作らない。置いた結果、史実の何が変わるか・見えるかまで言える物だけ。説明が要る設定は使わない（1文目で分かる）。
- fact_main は WebSearch で本当にあったことを確かめ、出どころを note に書く。説・逸話は『といわれる』と書く。確かめられない物は入れない。
- 時代の配分は 江戸5〜6割・戦国2〜3割・幕末1〜2割。ずらし方は主力の2つ（{'・'.join(MAIN)}）を{n}行のうち7〜8行にし、残りの5つは合わせて2〜3行（2026-11-07 手順書 §2。同じずらし方を2つ続けて並べない）。{('今回は特に「' + need + '」の行を多めに。') if need else ''}
- オチは、和歌・遺言・史料の中身を知らなくても、絵を見て分かる結果1つにできる企画だけ（手順書 §3）。
- 実在の人の性・病気・民族を笑いの種にする物、今も生きている人や今も遺族・関係者がいる近現代の事件は使わない（手順書 §4）。
- 昭和は、戦争ではない物（東京オリンピック・新幹線・家電・高度経済成長など）だけ。戦争そのもの（戦場・空襲・原爆・特攻・戦死）はショートのずらしの種にしない（手順書 v2.7 §2）。
- 次の史実は『へえ』の主役に使い済み。同じ物を作らない：{json.dumps(used_facts(past), ensure_ascii=False)}
- 次の企画は未使用の行として既にある。重ねない：{json.dumps([r['企画'] for r in rows], ensure_ascii=False)}
"""
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_PICK_MODEL", "sonnet"), "--allowedTools", "Read", "WebSearch", "WebFetch",
           "--permission-mode", "acceptEdits", "--output-format", "json"]
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=claude_env(), input=p, capture_output=True, text=True, encoding="utf-8", timeout=1800)
        out = json.loads(r.stdout).get("result", "")
        arr = json.loads(out[out.index("["):out.rindex("]") + 1])
    except Exception as e:  # noqa: BLE001
        log(f"【メモ】ネタの補充ができませんでした（{type(e).__name__}）。今ある行から選びます")
        return []
    have = refill_rows()
    start = len(have) + 1
    new = []
    for i, x in enumerate(arr):
        if not (x.get("企画") and x.get("distort") in book_.get("distorts", []) and x.get("fact_main")):
            continue
        if any(same_fact(x["fact_main"], f) for f in used_facts(past) + [r.get("fact_main") for r in rows + new]):
            continue
        x["id"] = f"R{start + len(new):03d}"
        new.append(x)
    if new:
        jsave(os.path.join(HIST, "ネタ補充.json"), have + new)
        log(f"ネタを{len(new)}行足しました（history/nihongi/ネタ補充.json）")
    return new


def next_no(prefix):
    """毎日の制作の番号は 101 から（手で作った番号と衝突しない）"""
    names = [x.get("work") or "" for x in past_works()] + [e.get("work") or "" for e in ustore.load(CH)]
    if os.path.isdir(VDIR):
        names += os.listdir(VDIR)
    nums = [int(m.group(1)) for m in (re.match(prefix + r"(\d+)", n) for n in names) if m and int(m.group(1)) >= 101]
    return (max(nums) if nums else 100) + 1


def pick_short(today):
    past = past_works()
    shorts = [x for x in past if x["kind"] == "short"]
    rows = [r for r in book().get("rows", []) + refill_rows()]
    wip_ids = {jload(os.path.join(VDIR, d, "neta.json"), {}).get("id") for d in (os.listdir(VDIR) if os.path.isdir(VDIR) else [])}
    prod_ids = {p.get("neta_id") for p in jload(os.path.join(HIST, "produced.json"), [])}
    unused = [r for r in rows if r["id"] not in wip_ids | prod_ids]
    last = shorts[-1] if shorts else {}
    # 主力のずらし方で、前のショートと違う行が切れていたら、その行を多めに補充する（2026-11-07）
    need = [m for m in MAIN if m != last.get("distort") and not any(m in (r.get("distort") or "") for r in unused)]
    if len(unused) <= REFILL_AT or need:
        unused += refill(unused, past, need="・".join(need))
    last4 = [x.get("distort") for x in shorts[-4:]]
    sub7 = sum(1 for x in shorts[-7:] if not is_main(x.get("distort")))
    last10 = shorts[-10:]
    mix = book().get("era_mix", {})
    cnt = lambda era: sum(1 for x in last10 if (x.get("era") or "その他") == era)
    cands, skipped = [], {}
    for r in unused:
        if r["distort"] == last.get("distort"):
            skipped[r["id"]] = "前のショートと同じずらし方"
            continue
        if any(same_fact(r.get("fact_main"), f) for f in used_facts(past)):
            skipped[r["id"]] = "『へえ』の主役の史実が過去の回と同じ"
            continue
        era = r.get("era") if r.get("era") in mix else "その他"
        deficit = mix.get(era, 0.03) * (len(last10) + 1) - cnt(era)
        sub = 0 if is_main(r["distort"]) else (1 if sub7 >= 1 else 0)
        idx = rows.index(r) if r in rows else len(rows) + unused.index(r)
        cands.append((sub, -round(deficit, 3), last4.count(r["distort"]), idx, r))
    if not cands:
        log(json.dumps({"選ばなかった行": skipped}, ensure_ascii=False))
        sys.exit("【止まりました】nihongi：今出せるネタがありません（ネタ帳.json に行を足すか、補充を確かめる）")
    cands.sort(key=lambda c: c[:4])
    r = cands[0][4]
    no = f"S{next_no('S')}"
    kind_ = "主力のずらし方" if is_main(r["distort"]) else f"主力以外のずらし方（直近7本で主力以外は{sub7}本）"
    return r, no, f"{kind_}「{r['distort']}」で、時代の配分でいちばん足りない時代（{r.get('era')}）を先に。前のショート（{last.get('no')}：{last.get('distort')}）と違う"


def long_rows_all():
    """横動画の『分かれ道』の行（ネタ帳.json の long_rows → history/nihongi/ネタ補充_横.json の順）"""
    return book().get("long_rows", []) + jload(os.path.join(HIST, "ネタ補充_横.json"), [])


def refill_long(rows, past, n=6):
    """『分かれ道』の行が少なくなったら、claude -p で足す（WebSearch で史実を確かめさせる）。足せなかったら何もしない"""
    p = f"""あなたは YouTube チャンネル「アナザー日本紀」の横動画の企画係です。
先に channels/nihongi/手順書.md の §4・§7・§10 を最後の行まで読んでください。
{TTP_NETA}
横動画の企画のうち『分かれ道』（日本の歴史で本当に起きた大きな出来事・決断を1つだけ逆にして、その後の日本がどうなったかを見せる）を{n}行作り、最後に JSON の配列だけを出力してください（前後の説明は不要）。
各行：{{"企画": "もしも〜たら（検索でそのまま打たれる言い方）", "検索語": "人が検索窓に打つ言い方（例 本能寺の変がなかったら）", "distort": "分かれ道", "era": "江戸／戦国／幕末／昭和／その他",
"fact_main": "逆にする史実（年・人・場所が入る1文）", "分かれ道": "逆にする1点（例 光秀が本能寺を襲わなかった）", "note": "調べた出どころ（URL か資料名）と、良い未来・悪い未来の方向"}}
決まり
- 選ぶのは、検索される量が多い有名な出来事だけ（教科書に載る・誰でも名前を知っている人や出来事）。知らない人物・用語だけの企画は作らない。
- fact_main は WebSearch で本当にあったことを確かめ、出どころを note に書く。説・逸話は『といわれる』と書く。
- 今も生きている人や今も遺族・関係者がいる近現代の事件は使わない（手順書 §4）。
- 昭和の戦争は使ってよい（2026-11-12 手順書 v2.7 §4・§7）。ただし{n}行のうち昭和は1行まで。開戦・終戦・外交の分かれ道を先にし、戦いの勝ち負けを逆にする物は、良い未来を「日本が勝った」ではなく助かった命・続いた暮らしにできる物だけ。国どうしで今も争いのある題（慰安婦・南京事件・靖国神社など）は主役にしない。死者数は公的な出どころ（国立公文書館・アジア歴史資料センター・厚生労働省など）で確かめ、note に書く。
- 次の企画は既にある。重ねない：{json.dumps([r.get('企画') for r in rows], ensure_ascii=False)}
- 次の史実は過去の回で主役に使った。同じ出来事を逆にするのはよいが、企画の言い方は重ねない：{json.dumps(used_facts(past), ensure_ascii=False)}
"""
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_PICK_MODEL", "sonnet"), "--allowedTools", "Read", "WebSearch", "WebFetch",
           "--permission-mode", "acceptEdits", "--output-format", "json"]
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=claude_env(), input=p, capture_output=True, text=True, encoding="utf-8", timeout=1800)
        out = json.loads(r.stdout).get("result", "")
        arr = json.loads(out[out.index("["):out.rindex("]") + 1])
    except Exception as e:  # noqa: BLE001
        log(f"【メモ】横動画の『分かれ道』の補充ができませんでした（{type(e).__name__}）。今ある行から選びます")
        return []
    path = os.path.join(HIST, "ネタ補充_横.json")
    have = jload(path, [])
    names = {re.sub(r"\s", "", r.get("企画") or "") for r in rows}
    new = []
    for x in arr:
        if not (x.get("企画") and x.get("fact_main") and x.get("検索語")) or re.sub(r"\s", "", x["企画"]) in names:
            continue
        x["distort"] = LONG_IF
        x["id"] = f"W{101 + len(have) + len(new)}"  # ネタ帳.json の W001〜 と衝突しない
        new.append(x)
    if new:
        jsave(path, have + new)
        log(f"横動画の『分かれ道』を{len(new)}行足しました（history/nihongi/ネタ補充_横.json）")
    return new


def pick_long_if(past):
    """『分かれ道』の横動画（2026-11-12 手順書 v2.7 §7。昭和は直近4本に1本まで）。使っていない行を上から順に。無ければ None"""
    rows = long_rows_all()
    wip_ids = {jload(os.path.join(VDIR, d, "neta.json"), {}).get("id") for d in (os.listdir(VDIR) if os.path.isdir(VDIR) else [])}
    prod_ids = {p.get("neta_id") for p in jload(os.path.join(HIST, "produced.json"), [])}
    unused = [r for r in rows if r["id"] not in wip_ids | prod_ids]
    # 昭和の『分かれ道』は横動画の直近4本に1本まで（2026-11-12 手順書 v2.7 §7）：直近3本に昭和があれば、昭和の行は今回は選ばない
    showa_recent = any(x.get("era") == SHOWA for x in [x for x in past if x["kind"] == "long"][-(SHOWA_EVERY - 1):])
    ok = [r for r in unused if not (showa_recent and r.get("era") == SHOWA)]
    if len(ok) <= LONG_REFILL_AT:
        new = refill_long(rows, past)
        unused += new
        ok += [r for r in new if not (showa_recent and r.get("era") == SHOWA)]
    if not ok:
        if unused:
            log(f"【メモ】『分かれ道』の残りは昭和の行だけで、直近{SHOWA_EVERY - 1}本の横動画に昭和があるので今回は選びません（手順書 v2.7 §7）")
        return None
    r = ok[0]
    showa_note = "／昭和の回：手順書 v2.7 §4 の『昭和（戦争を含む）の扱い方』を全部守る（笑いにしない・美化しない・被害も加害も小さく言わない・むごい絵を出さない・どの国の死者も同じ重さ・数字は公的な出どころで『〜とされる』・題とサムネは広告に合う言葉）。良い未来は助かった命・続いた暮らし" if r.get("era") == SHOWA else ""
    row = {**r, "kind": "long", "distort": LONG_IF,
           "note": (r.get("note") or "") + "／『分かれ道』の横動画：史実の1点だけを逆にし、その後の日本を章ごとに追う。最後の章で良い未来と悪い未来を並べ、視聴者に『どっちの日本になったと思うか』を聞く（手順書 v2.7 §7）" + showa_note}
    return row, f"L{next_no('L')}", f"『分かれ道』の横動画（検索される『もしも』。直近2本の横動画が両方『分かれ道』でない時に選ぶ。検索語：{r.get('検索語')}）"


def pick_long():
    """横動画は3本のうち2本を『分かれ道』、1本を伸びたショートから（2026-11-12）。選んだ方が無ければ、もう一方から"""
    past = past_works()
    longs = [x for x in past if x["kind"] == "long"]
    want_if = sum(1 for x in longs[-2:] if x.get("distort") == LONG_IF) < 2
    order = (lambda: pick_long_if(past), pick_long_from_short) if want_if else (pick_long_from_short, lambda: pick_long_if(past))
    for f in order:
        got = f()
        if got:
            return got
    # 失敗ではない。次のショートが上がるか、分かれ道の行を足せば作れる（終了コード 76＝run_daily.py が「待ち」にする。Issue にしない。2026-11-01）
    print("横動画の元にできる物がまだありません（分かれ道の行が切れていて、上げたショートで横動画にしていない物も無い）。待ちます", file=sys.stderr)
    sys.exit(76)


def pick_long_from_short():
    book_ = book()
    past = past_works()
    long_done = set(book_.get("long_done_from", [])) | {x.get("from_short") for x in past if x["kind"] == "long" and x.get("from_short")}
    up = ustore.load(CH)
    ent = {}
    for e in up:
        m = re.match(r"S(\d+)", e.get("work") or "")
        if m and ustore.kind_of(e) == "short" and not e.get("retired") and not e.get("missing"):
            ent["S" + m.group(1)] = e
    cands = [x for x in past if x["kind"] == "short" and x["no"] not in long_done and x["no"] in ent]
    if not cands:
        log("横動画の元にできるショートがまだありません（上げたショートで、まだ横動画にしていない物が無い）")
        return None
    cands.sort(key=lambda x: (-int(ent[x["no"]].get("views_now") or 0), number_key(x["no"])))
    s = cands[0]
    e = ent[s["no"]]
    no = f"L{next_no('L')}"
    sw = e.get("work") or s["no"]
    row = {"id": f"long_{s['no']}", "kind": "long", "企画": f"{s['企画']}【完全版】", "distort": s["distort"], "era": s["era"], "fact_main": s["fact_main"],
           "from_short": s["no"], "from_short_work": sw, "from_short_title": e.get("title"), "from_short_views": e.get("views_now"),
           "short_script": f"history/nihongi/scripts/{sw}.json",
           "note": "元のショートのずらしたルールをそのまま使い、ショートで言えなかった史実を章ごとに足す（制作ルール §7）"}
    why = f"まだ横動画にしていないショートのうち、再生が多い順（{s['no']}：{e.get('views_now')}回）"
    return row, no, why


def main():
    a = argparse.ArgumentParser()
    a.add_argument("ch", choices=[CH])
    a.add_argument("--kind", choices=["short", "long"], required=True)
    a.add_argument("--dry", action="store_true")
    a.add_argument("--today")
    a = a.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(JST).date()
    row, no, why = pick_short(today) if a.kind == "short" else pick_long()
    work = os.path.join(VDIR, f"{no}_{re.sub(r'[^0-9a-z_]', '', row['id'].lower())}")
    neta = {**{k: v for k, v in row.items()}, "kind": a.kind, "no": no, "made": today.isoformat(), "回した理由": why}
    print(json.dumps(neta, ensure_ascii=False), file=sys.stderr)
    if a.dry:
        print(work)
        return
    os.makedirs(work, exist_ok=True)
    jsave(os.path.join(work, "neta.json"), neta)
    print(work)


if __name__ == "__main__":
    main()
