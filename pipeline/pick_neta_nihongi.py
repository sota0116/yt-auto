# ①ネタ（アナザー日本紀・2026-10-29 新設。千年こよみ pick_neta_spi.py と同じ形：作業フォルダを作り、最後の行にそのパスを出す）
#   python -X utf8 pipeline/pick_neta_nihongi.py nihongi --kind short|long [--dry]
# ・ショート（short）：channels/nihongi/ネタ帳.json の rows と history/nihongi/ネタ補充.json（この道具が claude -p で足す）の使っていない行から1つ選ぶ。
#   選び方（制作ルール §2）：①前のショートと同じずらし方は選ばない（2本続けない） ②『へえ』の主役の史実を過去に使った回と同じにしない
#   ③時代の配分（江戸5〜6割・戦国2〜3割・幕末1〜2割）に直近10本がいちばん足りない時代の行を先に ④直近4本で使っていないずらし方を先に
#   使っていない行が3つ以下になったら、先に claude -p（WebSearch で史実を確かめる）で10行を足す
# ・横動画（long）：公開済み（または予約済み）のショートのうち、まだ横動画にしていない1本を選ぶ（再生が多い順。数字がまだ無ければ番号の若い順）。
#   手で作った S001〜S005 は L001・L002 に入っているので選ばない（ネタ帳.json の long_done_from）。企画・ずらし方・時代・史実は元のショートと同じ
# ・番号：毎日の制作が作る回は S101・L101 から（手で作った S001〜S010・L001〜L002 と衝突しない）。作業フォルダは channels/nihongi/videos/S101_<ネタの id>
# ・neta.json（kind・no・企画・distort・era・fact_main・from_short など）を作業フォルダに置く。run_daily.py の record() が履歴に写す
import argparse, datetime as dt, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nihongi_common import (ROOT, CH, CDIR, HIST, VDIR, jload, jsave, book, refill_rows, past_works, number_key, claude_env)  # noqa: E402
import ustore  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))
REFILL_AT = 3  # 使っていない行がこの数以下なら、先に補充する


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


def refill(rows, past, n=10):
    """claude -p で新しい行を足す（使っていない行が少なくなった時）。WebSearch で史実を確かめさせる。足せなかったら何もしない"""
    book_ = book()
    p = f"""あなたは YouTube チャンネル「アナザー日本紀」（歴史に、ありえないルールを1つだけ足して、史実が少しだけひっくり返る『もしも歴史』のショート）の企画係です。
先に channels/nihongi/手順書.md の §0〜§4 と §10 を最後の行まで読んでください。
次の{n}行を作り、最後に JSON の配列だけを出力してください（前後の説明は不要）。
各行：{{"id": "R<連番>", "企画": "もしも〜（1文）", "distort": "{'／'.join(book_.get('distorts', []))} のどれか1つ", "era": "江戸／戦国／幕末／平安／その他", "fact_main": "『へえ』の主役の史実（年・人・場所が入る1文）", "note": "調べた出どころ（URL か資料名）とオチの方向"}}
決まり
- 道具を置くだけの企画は作らない。置いた結果、史実の何が変わるか・見えるかまで言える物だけ。説明が要る設定は使わない（1文目で分かる）。
- fact_main は WebSearch で本当にあったことを確かめ、出どころを note に書く。説・逸話は『といわれる』と書く。確かめられない物は入れない。
- 時代の配分は 江戸5〜6割・戦国2〜3割・幕末1〜2割。ずらし方は7つを偏らせず混ぜる（同じずらし方を2つ続けて並べない）。
- 昭和の戦争の死者・被害を笑いにする物、実在の人の性・病気・民族を笑いの種にする物、今も遺族や関係者がいる近現代の事件は使わない。
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
    if len(unused) <= REFILL_AT:
        unused += refill(unused, past)
    last = shorts[-1] if shorts else {}
    last4 = [x.get("distort") for x in shorts[-4:]]
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
        cands.append((-round(deficit, 3), last4.count(r["distort"]), rows.index(r), r))
    if not cands:
        log(json.dumps({"選ばなかった行": skipped}, ensure_ascii=False))
        sys.exit("【止まりました】nihongi：今出せるネタがありません（ネタ帳.json に行を足すか、補充を確かめる）")
    cands.sort(key=lambda c: c[:3])
    r = cands[0][3]
    no = f"S{next_no('S')}"
    return r, no, f"時代の配分でいちばん足りない時代（{r.get('era')}）で、直近4本で使っていないずらし方（{r['distort']}）。前のショート（{last.get('no')}：{last.get('distort')}）と違う"


def pick_long():
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
        sys.exit("【止まりました】nihongi：横動画の元にできるショートがありません（上げたショートで、まだ横動画にしていない物が無い）")
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
