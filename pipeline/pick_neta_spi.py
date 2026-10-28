# ①ネタ（千年こよみ・2026-10-29 新設。心理学ch の pick_neta_psy.py をもとにした。元は残している）
#   python -X utf8 pipeline\pick_neta_spi.py spi [--dry] [--today 2026-10-29]
# ・channels\spi\ネタ帳.json の行と、暦の固定ファイルから自動で作る行（A-4：重なりのある月ごと／C2：2027-02〜2027-12 の月ごとに2つ）から、
#   次に作る回を1つ選び、作業フォルダに neta.json と facts.json（暦の欄 "koyomi" だけ。pipeline\koyomi_spi.py が作る）を置く
# ・公開日（pub_date）を先に決める（手順書 §13：月・水・金・日の 18:00。日付が中身に出る回は、その日より前に出す）：
#   空いている枠＝今日から LEAD 日より後の 月・水・金・日 で、history\spi\pub_plan.json（この道具が書く。作業フォルダ→公開の予定日）と
#   history\spi\uploaded.json の公開日・予約日に入っていない日。
#   公開できる期間（window）：型A の行事＝その日の10日前〜3日前（手順書 §3）／A-4・C2＝前月20日〜その月10日／C＝2027-01-31 まで／B＝いつでも
#   どの行も「期間の中の最初の空き枠」を出し、その日がいちばん早い行を選ぶ。同じ日なら、期間の終わりが近い行（日付のある行）を先にする
#   （日付のある回は、過ぎると出せないため。手順書 §14「日付の近い吉日・行事を先に使う」）
# ・型の混ぜ方（手順書 §3・§8）：前の回と同じ型は、ほかに選べる行がある時は後ろへ。型B は同じ週（月〜日）に2本まで。
#   数え上げの骨組み（A-2・B-2・C2-2）は直近9本で合わせて3本まで。骨組みは、同じ型の前の回と違う物を選ぶ。
#   型の後回し（見張り watch.py が history\spi\type_hold.json に書いた型）は後ろへ。型D と hold の付いた行は選ばない
# ・特典の無い型は選ばない（LINE の案内で約束する物が無いため。ネタ帳.json の「特典」の glob に当たるファイルがある型だけ）
# ・hook_type（つかみの型）・line_copy（LINE の案内の文の番号）・sub_copy（登録の呼びかけの番号）もここで決めて neta.json に書く
#   （hook_type は型ごとに 日付→場面→問い の順に回す。sub_copy は直近5本でいちばん使っていない番号。line_copy は型ごとに1→2→3。
#    ②は「この回の吉日」を言う文なので、kichijitsu の無い回では飛ばす）
# ・使った行：history\spi\produced.json の neta_id・作り途中の回（videos の中の neta.json）・pub_plan.json・ネタ帳の used_by
# ・最後の行に作業フォルダのパスを出す（run_daily.py が読む）
import argparse, datetime as dt, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import koyomi_spi as K

ROOT = K.ROOT
CH = "spi"
DAYS = (0, 2, 4, 6)  # 月・水・金・日（手順書 §13）
LEAD = int(os.environ.get("SPI_LEAD_DAYS", 3))  # 作り始めてから公開まで最低これだけ空ける（絵の順番待ち・在庫の段取り）
HORIZON = 150  # 何日先の枠まで見るか
COUNTING = {"A-2", "B-2", "C2-2"}
HOOKS = ["日付", "場面", "問い"]


def jload(p, default):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def hpath(name):
    return os.path.join(ROOT, "history", CH, name)


def auto_rows(used_months_a4):
    """A-4（重なりのある月）と C2（2027-02〜）の行を暦の固定ファイルから作る"""
    out = []
    for y, m in K.months_between("2026-11-01", K.K()["meta"]["valid_to"]):
        ym = f"{y}-{m:02d}"
        ov = K.overlaps(f"{ym}-01", 0, until=f"{ym}-31")
        if ov and ym not in used_months_a4:
            # 主役の重なり：その月でいちばん強い組み合わせ（天赦日を含む物＞一粒万倍日を含む物）。同じ組み合わせの日は全部数える
            best = sorted(ov, key=lambda o: (0 if "天赦日" in o["names"] else 1 if "一粒万倍日" in o["names"] else 2, o["iso"]))[0]
            names = best["names"].split(" × ")
            saikyo = names == ["天赦日", "一粒万倍日"]
            out.append({"id": f"a4_{y}_{m:02d}", "type": "A", "frames": ["A-4"], "target_month": ym, "overlap": names, "kichijitsu": True,
                        "題": f"{m}月の{'最強開運日（天赦日と一粒万倍日の重なり）' if saikyo else best['names'] + 'の重なり'}を全部数える",
                        "target": "次の吉日に、始めごとや買い物の日取りを合わせたい50〜60代の女性", "auto": "A-4"})
        if ym >= "2027-02":
            for fr in ("C2-1", "C2-2"):
                out.append({"id": f"c2_{y}_{m:02d}_{fr[-1]}", "type": "C2", "frames": [fr], "target_month": ym, "kichijitsu": True,
                            "題": f"{m}月の吉日と行事の総まとめ（{'日付の順' if fr == 'C2-1' else 'その月の吉日の重なり5つ'}）",
                            "target": "来月の予定を吉日に合わせて決めたい50〜60代の女性", "auto": "C2"})
    return out


def event_dates(row, after):
    """型A の行事の日（data_ref から暦の固定ファイルで探す）。after より後の最初の1日"""
    ref = row.get("data_ref") or {}
    after = max(after, ref.get("after", ""))
    for d in K.K()["days"]:
        if d["date"] < after:
            continue
        hit = (("gyoji" in ref and any(ref["gyoji"] in g for g in d["gyoji"]))
               or ("sekki" in ref and (d["sekki"] or {}).get("name") == ref["sekki"])
               or ("zassetsu" in ref and ref["zassetsu"] in d["zassetsu"])
               or ("holiday" in ref and d["holiday"] == ref["holiday"]))
        if hit:
            return d["date"]
    return None


def window(row, earliest):
    """(公開できる最初の日, 最後の日, 主役の日の一覧)。出せない行は None"""
    t = row["type"]
    if t == "A" and row.get("target_month"):  # A-4
        y, m = map(int, row["target_month"].split("-"))
        p = dt.date(y, m, 1) - dt.timedelta(days=1)
        focus = [o["iso"] for o in K.overlaps(f"{row['target_month']}-01", 0, names=row["overlap"], until=f"{row['target_month']}-31")]
        return dt.date(p.year, p.month, 20), dt.date(y, m, 10), focus
    if t == "C2":
        y, m = map(int, row["target_month"].split("-"))
        p = dt.date(y, m, 1) - dt.timedelta(days=1)
        return dt.date(p.year, p.month, 20), dt.date(y, m, 10), []
    if t == "A":
        e = event_dates(row, (earliest + dt.timedelta(days=3)).isoformat())
        if not e:
            return None
        ed = dt.date.fromisoformat(e)
        return ed - dt.timedelta(days=10), ed - dt.timedelta(days=3), [e]
    if t == "C":
        return earliest, dt.date(2027, 1, 31), []
    return earliest, earliest + dt.timedelta(days=HORIZON), []  # B


def main():
    a = argparse.ArgumentParser()
    a.add_argument("ch", choices=[CH])
    a.add_argument("--dry", action="store_true")
    a.add_argument("--today", help="試し用：今日の日付を替える（YYYY-MM-DD）")
    a = a.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else K.today()
    cdir = os.path.join(ROOT, "channels", CH)
    book = jload(os.path.join(cdir, "ネタ帳.json"), {})
    prod = jload(hpath("produced.json"), [])
    up = jload(hpath("uploaded.json"), [])
    plan = jload(hpath("pub_plan.json"), {})
    hold = jload(hpath("type_hold.json"), {})
    vdir = os.path.join(cdir, "videos")
    wdirs = sorted(os.listdir(vdir)) if os.path.isdir(vdir) else []
    wip = {d: x for d, x in ((d, jload(os.path.join(vdir, d, "neta.json"), None)) for d in wdirs) if x}
    up_works = {e.get("work") for e in up}
    # 予定が古くなった行（公開の予定日を過ぎたのに上げていない＝止めた回）は、枠も題も空ける
    plan = {w: v for w, v in plan.items() if w in up_works or w in wip or v.get("pub_date", "") >= today.isoformat()}

    # 作った順（直近の型・骨組み・番号を数えるため）。同じ回は produced → 作り途中 → pub_plan の順に1回だけ
    by = {}
    for w, v in plan.items():
        by[w] = {**v, "work": w}
    for w, x in wip.items():
        by[w] = {**by.get(w, {}), **x, "neta_id": x.get("id"), "work": w}
    for x in prod:
        by[x.get("work")] = {**by.get(x.get("work"), {}), **x}
    recent = sorted(by.values(), key=lambda x: (x.get("made") or "", x.get("work") or ""))
    used = {x.get("neta_id") for x in recent}
    used |= {r["id"] for r in book.get("rows", []) if r.get("used_by")}
    rows = [r for r in book.get("rows", [])] + auto_rows({"2026-12"})  # 2026-12 の最強開運日は 001 で使った

    # 空いている枠
    busy = {v["pub_date"] for v in plan.values() if v.get("pub_date")}
    for e in up:
        w = e.get("publish_at") or e.get("published_at")
        if w and not e.get("missing") and not e.get("retired"):
            busy.add(dt.datetime.fromisoformat(w.replace("Z", "+00:00")).astimezone(K.JST).date().isoformat())
    earliest = today + dt.timedelta(days=LEAD)
    slots = [earliest + dt.timedelta(days=i) for i in range(HORIZON)]
    slots = [d for d in slots if d.weekday() in DAYS and d.isoformat() not in busy]

    tok = {t: bool(glob.glob(os.path.join(ROOT, g))) for t, g in (book.get("特典") or {}).items() if not t.startswith("_")}
    last_type = recent[-1].get("type") if recent else None
    last9 = [x.get("frame") for x in recent[-9:]]
    skipped, cands = {}, []
    for r in rows:
        if r["id"] in used:
            continue
        if r.get("hold") or r["type"] == "D":
            skipped[r["id"]] = r.get("hold") or "型D"
            continue
        if not tok.get(r["type"], False):
            skipped[r["id"]] = f"型{r['type']} の特典ファイルが無い（{(book.get('特典') or {}).get(r['type'])}）"
            continue
        w = window(r, earliest)
        if not w:
            skipped[r["id"]] = "暦の固定ファイルの期間に、この行事の日が無い"
            continue
        ws, we, focus = w
        if r["type"] == "C2" and r["target_month"] < "2027-02":
            continue
        free = [d for d in slots if max(ws, earliest) <= d <= we]
        # 型B は同じ週（月〜日）に2本まで
        if r["type"] == "B":
            def b_in_week(d):
                mon = d - dt.timedelta(days=d.weekday())
                planned = [v for v in plan.values() if v.get("type") == "B"]
                return sum(mon <= dt.date.fromisoformat(v["pub_date"]) < mon + dt.timedelta(days=7) for v in planned)
            free = [d for d in free if b_in_week(d) < 2]
        if not free:
            if we < earliest:
                skipped[r["id"]] = f"公開できる期間（〜{we}）が過ぎた"
            continue
        # 骨組み：数え上げの上限と、同じ型の前の回と違う物
        prev_fr = next((x.get("frame") for x in reversed(recent) if x.get("type") == r["type"]), None)
        frs = [f for f in r.get("frames") or [r["type"] + "-1"] if not (f in COUNTING and sum(x in COUNTING for x in last9) >= 3)]
        if not frs:
            skipped[r["id"]] = "数え上げの骨組みが直近9本で3本"
            continue
        frame = next((f for f in frs if f != prev_fr), frs[0])
        cands.append({"row": r, "pub": free[0], "window": [max(ws, earliest).isoformat(), we.isoformat()], "focus": focus, "frame": frame,
                      "late": we, "free_n": len(free)})
    if not cands:
        print(json.dumps({"選ばなかった行": skipped}, ensure_ascii=False, indent=1))
        sys.exit("【止まりました】spi：今出せるネタがありません（上の理由）。ネタ帳.json か特典を足してください（在庫で公開をつなぐ）")

    def key(c):
        r = c["row"]
        return (c["pub"],                                  # いちばん早い空き枠に入る行
                r["type"] in hold,                         # 後回しの型は後ろ
                r["type"] == last_type,                    # 前の回と同じ型は後ろ
                0 if r["type"] in ("A", "C2") else 1,      # 日付のある回を先に
                c["free_n"], c["late"], r["id"])
    cands.sort(key=key)
    c = cands[0]
    r = c["row"]

    # つかみの型・案内文・呼びかけの番号
    same = [x for x in recent if x.get("type") == r["type"]]
    hook = HOOKS[len(same) % 3]
    lc_prev = [x.get("line_copy") for x in same if x.get("line_copy")]
    lc = (lc_prev[-1] % 3 + 1) if lc_prev else 1
    if lc == 2 and r["type"] in ("A", "C2") and not r.get("kichijitsu"):
        lc = 3
    sub5 = [x.get("sub_copy") for x in recent[-5:] if x.get("sub_copy")]
    sc = min((1, 2, 3), key=lambda n: (sub5.count(n), (n - ((sub5[-1] if sub5 else 0) % 3) - 1) % 3))

    names = [x.get("work", "") for x in prod + up] + wdirs + list(plan) + [str(x.get("used_by", "")) for x in book.get("rows", [])]
    n = max([int(m.group(1)) for m in (re.match(r"(\d{3})_", s) for s in names) if m] or [0]) + 1
    pub = c["pub"].isoformat()
    slug = re.sub(r"[^0-9a-z_]", "", r["id"].lower())
    work = os.path.join(vdir, f"{n:03d}_{slug}")
    neta = {**{k: v for k, v in r.items() if k not in ("frames",)}, "frame": c["frame"], "pub_date": pub,
            "pub_wd": K.wd(pub), "window": c["window"], "focus_dates": c["focus"], "hook_type": hook, "line_copy": lc, "sub_copy": sc,
            "made": today.isoformat(),
            "回した理由": f"空いている枠 {pub}（{K.wd(pub)}）に入る行のうち、" + ("期間の終わりが近い日付の回" if r["type"] in ("A", "C2") else "日付の無い回（その枠に入る日付の回が無い）")
                     + f"。骨組み {c['frame']}（同じ型の前の回と変える）"}
    if (r.get("data_ref") or {}).get("gyoji"):
        neta["gyoji"] = [r["data_ref"]["gyoji"]]  # 行事の出典（data/gyoji.json）を facts.json に写すため
    print(json.dumps(neta, ensure_ascii=False))
    if skipped:
        print("選ばなかった行：" + "／".join(f"{k}（{v}）" for k, v in list(skipped.items())[:12]), file=sys.stderr)
    if a.dry:
        print(work)
        return
    os.makedirs(work, exist_ok=True)
    json.dump(neta, open(os.path.join(work, "neta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    facts = {"_説明": "koyomi の欄は pick_neta_spi.py（koyomi_spi.py）がプログラムで作った暦の値。書き手は書き換えない。"
                      "sources・quotes は書き手（write_script_spi.py）が Web で調べて足す",
             "koyomi": K.facts(neta), "sources": {}, "quotes": []}
    json.dump(facts, open(os.path.join(work, "facts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    plan = jload(hpath("pub_plan.json"), {})  # 古い行も消さずに残す（記録）。数える時だけ上で外す
    plan[os.path.basename(work)] = {"neta_id": r["id"], "type": r["type"], "frame": c["frame"], "pub_date": pub, "window": c["window"],
                                    "hook_type": hook, "line_copy": lc, "sub_copy": sc, "made": today.isoformat()}
    os.makedirs(os.path.dirname(hpath("pub_plan.json")), exist_ok=True)
    json.dump(plan, open(hpath("pub_plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(work)


if __name__ == "__main__":
    main()
