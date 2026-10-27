# ①ネタ（心理学ch・2026-10-27 新設）：channels\psy\ネタ帳.json から次に作る回を選び、作業フォルダに neta.json を置く
#   python -X utf8 pipeline\pick_neta_psy.py psy [--dry]
# ・使っていない行のうち、前の回と「area」（人づきあい・ひとりの時間・眠りと夜・幸せの心理）がちがう最初の行を選ぶ（同じ話題が続かないように）。
#   ちがう area の行が無ければ、使っていない最初の行
# ・型の後回し：見張り（watch.py）が history\psy\type_hold.json に書いた area（直近5本の平均視聴率が30%未満）は後ろに回す。
#   neta.json の type は area にする（アップの記録と数字が area ごとに分かれ、週報と見張りが area ごとに比べられるように。2026-10-27）
# ・使った行：history\psy\produced.json の neta_id と、作り途中の回（videos の中の neta.json）
# ・回の番号：videos の中・produced.json・uploaded.json の作業フォルダの番号のいちばん大きい数＋1
#   （001 は手で作って uploaded.json にだけある。クラウドは videos を引き継がないこともあるので、全部から数える）
# ・研究（facts.json）は書く段（write_script_psy.py）が Web で調べて作る。この段は置かない
# ・最後の行に作業フォルダのパスを出す（run_daily.py が読む）
import argparse, datetime, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JST = datetime.timezone(datetime.timedelta(hours=9))


def jload(p, default):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def main():
    a = argparse.ArgumentParser()
    a.add_argument("ch", choices=["psy"])
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    cdir = os.path.join(ROOT, "channels", a.ch)
    rows = jload(os.path.join(cdir, "ネタ帳.json"), [])
    prod = jload(os.path.join(ROOT, "history", a.ch, "produced.json"), [])
    up = jload(os.path.join(ROOT, "history", a.ch, "uploaded.json"), [])
    vdir = os.path.join(cdir, "videos")
    wip = [jload(os.path.join(vdir, d, "neta.json"), None) for d in sorted(os.listdir(vdir))] if os.path.isdir(vdir) else []
    wip = [x for x in wip if x]
    used = {x.get("neta_id") for x in prod} | {x.get("id") for x in wip}
    names = [x.get("work", "") for x in prod + up] + (os.listdir(vdir) if os.path.isdir(vdir) else [])
    n = max([int(m.group(1)) for m in (re.match(r"(\d{3})_", s) for s in names) if m] or [0]) + 1
    last = (sorted(wip + [{"area": next((r["area"] for r in rows if r["id"] == x.get("neta_id")), None), "made": x.get("made", "")}
                          for x in prod], key=lambda x: x.get("made") or "") or [{}])[-1].get("area")
    hold = jload(os.path.join(ROOT, "history", a.ch, "type_hold.json"), {})
    free = [r for r in rows if r["id"] not in used and not r.get("hold")]
    free.sort(key=lambda r: r["area"] in hold)  # 並びは保ったまま、後回しの area を後ろへ
    if not free:
        sys.exit("【止まりました】psy：ネタ帳.json の行を全部使いました。ネタ帳を足してください（在庫で公開をつなぐ）")
    row = next((r for r in free if r["area"] != last), free[0])
    slug = re.sub(r"[^0-9a-z_]", "", row["id"].lower().removeprefix("p_"))
    work = os.path.join(vdir, f"{n:03d}_{slug}")
    neta = {**row, "type": row["area"], "frame": row["area"], "made": datetime.datetime.now(JST).date().isoformat()}
    print(json.dumps(neta, ensure_ascii=False))
    if a.dry:
        print(work)
        return
    os.makedirs(work, exist_ok=True)
    json.dump(neta, open(os.path.join(work, "neta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(work)


if __name__ == "__main__":
    main()
