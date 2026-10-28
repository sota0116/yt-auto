# ①ネタ（金運おきぬ・2026-10-29 新設）：次に作る回を1つ選び、作業フォルダに neta.json を置く。最後の行に作業フォルダのパスを出す（run_daily.py が読む）
#   python -X utf8 pipeline\pick_neta_okinu.py okinu [--kind short|long|cut] [--from <長尺の作業フォルダ>] [--dry] [--today 2026-10-29]
# ・種類（kind）：short＝単独のショート／long＝長尺／cut＝長尺の1場面を切り出したショート（手順書 §13）。
#   指定が無ければ、環境変数 OKINU_KIND → 無ければ自動：最後に長尺を作ってから OKINU_LONG_EVERY_DAYS（既定3）日以上たっていれば long、そうでなければ short
#   （長尺は毎日でなくてよい・ショートは毎日1〜3本。手順書 §0。切り出しは長尺の絵が作業フォルダに残っている手元の実行だけ。クラウドは絵を消すので kind=cut は使えない）
# ・中身は ネタ帳.json の行（小物1つ・悩み1つ・年齢1つ・「やっていいか」の問い1つ。手順書 §1）。使った行（history・作業フォルダ・手で作った回の小物）は選ばない。
#   直前の回と年齢が同じ行・悩みの言葉が同じ行は後ろへ（手順書 §12 の2：前の回と同じにしない）
# ・番号のぶつかりを避ける（手順書 §13 の作業フォルダ名）：手で作る回は 001〜099／S001〜S099。自動の回は 101／S101 から、
#   次を取る前に OneDrive の videos・repo の videos・history/okinu の uploaded／produced／pub_plan にある番号を全部数えて、いちばん大きい番号の次にする
import argparse, datetime as dt, glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = "okinu"
HAND_DIR = os.environ.get("OKINU_HAND_DIR", r"C:\Users\koneb\OneDrive\YouTube自動チャンネル\金運おきぬ\videos")
AUTO_FROM = 100  # 自動の番号は 101 から（手で作る回は 001〜099）
LONG_EVERY = int(os.environ.get("OKINU_LONG_EVERY_DAYS", 3))
HEROES = ["sawako", "sumie"]  # ショートの主人公（手順書 §1：視聴者と同年代の女性）。交互に回す


def jload(p, default):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def hpath(name):
    return os.path.join(ROOT, "history", CH, name)


def today_jst():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()


def names_seen(vdir):
    """番号を数えるための名前の全部：repo の videos・手元の OneDrive の videos・history の work"""
    out = set()
    for d in (vdir, HAND_DIR):
        if os.path.isdir(d):
            out |= set(os.listdir(d))
    for fn in ("uploaded.json", "produced.json"):
        out |= {x.get("work", "") for x in jload(hpath(fn), []) if isinstance(x, dict)}
    out |= set(jload(hpath("pub_plan.json"), {}))
    return {n for n in out if n}


def number(name):
    """('S' なら short、無ければ long, 番号)。001v6 の v6 や _切出_ は見ない。番号が無い名前は None"""
    m = re.match(r"(S?)(\d{3})(?!\d)", name)
    return (("short" if m.group(1) else "long"), int(m.group(2))) if m else None


def next_num(kind, names):
    """kind が short／cut なら S 系列、long なら数字だけの系列。自動の番号は 101 から（手で予約中の 001〜099 とぶつからない）"""
    series = "long" if kind == "long" else "short"
    seen = [n[1] for n in (number(x) for x in names) if n and n[0] == series]
    return max([AUTO_FROM] + seen) + 1


def slug(s):
    return re.sub(r"[\\/:*?\"<>|\s　]", "", s)[:12]


def last_made(rows_made, kind):
    xs = [x.get("made", "") for x in rows_made if x.get("kind") == kind]
    return max(xs) if xs else ""


def main():
    a = argparse.ArgumentParser()
    a.add_argument("ch", choices=[CH])
    a.add_argument("--kind", choices=["short", "long", "cut"], default=os.environ.get("OKINU_KIND") or None)
    a.add_argument("--from", dest="from_long", default="", help="kind=cut の時の長尺の作業フォルダ（無ければ自動で探す）")
    a.add_argument("--dry", action="store_true")
    a.add_argument("--today")
    a = a.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else today_jst()
    cdir = os.path.join(ROOT, "channels", CH)
    book = jload(os.path.join(cdir, "ネタ帳.json"), {})
    prod, plan = jload(hpath("produced.json"), []), jload(hpath("pub_plan.json"), {})
    vdir = os.path.join(cdir, "videos")
    names = names_seen(vdir)
    wip = {}
    for base in (vdir,):
        for d in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            x = jload(os.path.join(base, d, "neta.json"), None)
            if x:
                wip[d] = x
    by = {}  # 同じ回は pub_plan → 作り途中 → produced の順に重ねる（produced には kind・年・小物が無いので、plan の物を消さない）
    for w, v in plan.items():
        by[w] = {**v, "work": w}
    for w, x in wip.items():
        by[w] = {**by.get(w, {}), **x, "work": w}
    for x in prod:
        if isinstance(x, dict):
            by[x.get("work")] = {**by.get(x.get("work"), {}), **{k: v for k, v in x.items() if v is not None}}
    made = sorted(by.values(), key=lambda m: (m.get("made") or "", m.get("work") or ""))

    kind = a.kind
    if not kind:
        lm = last_made(made, "long")
        kind = "long" if (not lm or (today - dt.date.fromisoformat(lm)).days >= LONG_EVERY) else "short"
    why = ""

    if kind == "cut":
        # 切り出し：自動で作った長尺（neta.json の items が残っている）で、まだ切り出していない小物を1つ。手で作った長尺は手で切り出す
        cands = []
        base = [a.from_long] if a.from_long else [os.path.join(vdir, d) for d in sorted(os.listdir(vdir), reverse=True)] if os.path.isdir(vdir) else []
        for lw in base:
            n = jload(os.path.join(lw, "neta.json"), None)
            if not n or n.get("kind") != "long" or not os.path.exists(os.path.join(lw, "script.json")) or not os.path.isdir(os.path.join(lw, "images")):
                continue
            cut_done = {jload(os.path.join(vdir, d, "neta.json"), {}).get("item") for d in os.listdir(vdir) if "_切出_" in d
                        and jload(os.path.join(vdir, d, "neta.json"), {}).get("long") == os.path.basename(lw)}
            left = [i for i in n.get("items", []) if i not in cut_done]
            if left:
                cands.append((lw, n, left[0]))
        if not cands:
            sys.exit("【切り出せる長尺がありません】絵が作業フォルダに残っている自動の長尺で、まだ切り出していない小物があるものが無い（クラウドは絵を消すので kind=cut は手元だけ）")
        lw, ln, item = cands[0]
        up = {x.get("work"): x for x in jload(hpath("uploaded.json"), [])}.get(os.path.basename(lw), {})
        n = next_num("cut", names)
        work = os.path.join(vdir, f"S{n:03d}_切出_{slug(item)}")
        neta = {"kind": "cut", "id": f"cut_{os.path.basename(lw)}_{slug(item)}", "item": item, "long": os.path.basename(lw), "long_dir": lw,
                "long_title": ln.get("題") or ln.get("小物"), "long_video_id": up.get("video_id"),
                "long_publish": up.get("publish_at"), "小物": item, "悩み": ln.get("悩み"), "年": ln.get("年"),
                "主人公": ln.get("主人公") or "sawako", "num": n, "made": today.isoformat()}
        why = f"長尺 {os.path.basename(lw)} の小物「{item}」の場面を切り出す（まだ切り出していない）"
    else:
        used_ids = {m.get("neta_id") or m.get("id") for m in made}
        used_ids |= {r["id"] for r in book.get("rows", []) if r.get("used_by")}
        hand_items = " ".join(book.get("手で作った回", {}).values())
        recent = [m for m in made if m.get("kind") == kind][-4:]
        last = recent[-1] if recent else {}
        rows, skipped = [], {}
        for r in book.get("rows", []):
            if r.get("kind") != kind:
                continue
            if r.get("hold"):
                skipped[r["id"]] = "hold"
            elif r["id"] in used_ids:
                skipped[r["id"]] = "使用済み"
            elif r["小物"] in hand_items:
                skipped[r["id"]] = "手で作った回と同じ小物"
            else:
                rows.append(r)
        if not rows:
            sys.exit(f"【止まりました】ネタ帳に、まだ作っていない {kind} の行がありません（ネタ帳.json に行を足す）")

        def key(r):  # 前の回と同じ年齢の行は後ろへ。同点はネタ帳の順
            return (1 if last.get("年") == r.get("年") else 0, rows.index(r))
        r = sorted(rows, key=key)[0]
        prev_hero = next((m.get("主人公") for m in reversed(made) if m.get("kind") == "short" and m.get("主人公")), None)
        hero = HEROES[(HEROES.index(prev_hero) + 1) % 2] if prev_hero in HEROES else HEROES[0]
        n = next_num(kind, names)
        work = os.path.join(vdir, (f"{n:03d}_" if kind == "long" else f"S{n:03d}_") + slug(r["小物"]))
        neta = {**{k: v for k, v in r.items() if k != "hold"}, "kind": kind, "neta_id": r["id"], "主人公": "sawako" if kind == "long" else hero,
                "num": n, "made": today.isoformat()}
        why = f"ネタ帳の未使用 {len(rows)} 行から「{r['小物']}」（前の回と年齢が違う行を先に）"
    neta["回した理由"] = why + f"。番号 {'S' if kind != 'long' else ''}{n:03d}（手で作る 001〜099／S001〜S099 とぶつからない自動の番号。数えた名前 {len(names)} 個）"
    print(json.dumps(neta, ensure_ascii=False))
    if a.dry:
        print(work)
        return
    os.makedirs(work, exist_ok=True)
    json.dump(neta, open(os.path.join(work, "neta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    plan[os.path.basename(work)] = {k: neta.get(k) for k in ("neta_id", "kind", "主人公", "年", "悩み", "小物", "made", "num", "long")}
    plan[os.path.basename(work)]["neta_id"] = neta.get("neta_id") or neta.get("id")
    os.makedirs(os.path.dirname(hpath("pub_plan.json")), exist_ok=True)
    json.dump(plan, open(hpath("pub_plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(work)


if __name__ == "__main__":
    main()
