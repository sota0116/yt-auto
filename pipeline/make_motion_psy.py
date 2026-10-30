# ⑥の2 動く絵（心理学ch・2026-10-27 新設）：script.json の "motion": true のカットの絵（images\<id>.png）を、
#   Lovart の Kling 2.6 で5秒の動画（images\<id>.mp4）にする。build_long_psy.py は mp4 があれば絵より先に使う
#   python -X utf8 pipeline\make_motion_psy.py <作業フォルダ> [--par 3] [--only A01,B03] [--force]
# ・元は手元の lovart_motion_v2.py（001 で使った頼み方）。頼み方の文（MOTION）は同じ
# ・お金：unlimited（無料）の時だけ頼む。クレジットを使う確認（pending_confirmation）が出たら confirm せず、そのカットは静止画のまま
# ・make_images_lovart.py と同じく、頼んだら会話ID を images\_motion.json に書き、終わった物から受け取る（止まっても二重に頼まない）
# ・時間：環境変数 MOTION_DEADLINE（その時刻を過ぎたら新しく頼まない。run_daily.py が時間の枠から決める）
# ・終了コード：0＝全部済んだ（できなかったカットは静止画のまま進む）／3＝まだ待ち・まだ頼んでいないカットがある（run_daily.py が「途中」にして次の実行で続ける）
#   3回の実行をまたいでも終わらなければ、残りは静止画のまま0で終える（動く絵のために公開を止めない）
# ・詰まった時（2026-10-29）：--boost は run_daily.py が速いモードにした間だけ使う。順番待ちを捨てて頼み直し、クレジットの確認が出たら
#   見積もりが1本の上限（目安の2倍）以下で、その日の残り（lovart_boost.left_today）に収まる時だけ confirm して、使った量を足す。
#   --boost でない時に速いモードになっていたら（別の回が使っている間）、新しく頼まずに「まだ待ち」（3）で終える
import argparse, json, os, shutil, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_images_lovart import client, PROJECT  # noqa: E402
from lovart_boost import add_spent, left_today, unit  # noqa: E402

MODEL = "generate_video_kling_v2_6"
THREAD_MAX = 60 * 60  # 1本を待つ上限（秒）。超えたら頼み直す（1カット2回まで）
RUNS_MAX = 3
MOTION = ("添付の絵を、そのまま動き出す5秒の動画にしてください。説明の返事はいりません。\n"
          "絵柄・色・構図・キャラの形と顔は変えない。新しいキャラや物を足さない。文字・字幕を入れない。音はいらない。\n"
          "動きは小さく、ゆっくり：キャラのまばたき・うなずき・顔の向き・手の小さな動き、湯気・葉・光のゆれ。"
          "カメラはほとんど動かさない（ごくゆっくり寄るくらい）。\n場面：{scene}")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--par", type=int, default=3, help="同時に頼む数（絵と同じ Lovart の同時の上限を分け合う）")
    a.add_argument("--only", default="")
    a.add_argument("--force", action="store_true")
    a.add_argument("--boost", action="store_true", help="速いモードの間だけ（run_daily.py が使う）")
    a = a.parse_args()
    deadline = float(os.environ.get("MOTION_DEADLINE") or time.time() + 3 * 3600)
    ch = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(a.work))))
    img = os.path.join(a.work, "images")
    s = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))
    only = set(filter(None, a.only.split(",")))
    cuts = {c["id"]: c for c in s["cuts"] if c.get("motion") and not c.get("same_as") and not c.get("card")
            and os.path.exists(os.path.join(img, c["id"] + ".png")) and (not only or c["id"] in only)}
    log_p = os.path.join(img, "_motion.json")
    log = json.load(open(log_p, encoding="utf-8")) if os.path.exists(log_p) else {}
    save = lambda: json.dump(log, open(log_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not a.boost:  # 速いモードで頼み直す実行は、無料の実行の回数に数えない
        log["_runs"] = log.get("_runs", 0) + 1
    save()
    done = lambda i: os.path.exists(os.path.join(img, i + ".mp4")) and not a.force
    todo = [i for i in cuts if not done(i) and (a.force or log.get(i, {}).get("状態") != "失敗" or log[i].get("回", 0) < 2)]
    if not todo:
        print("動かすカットはもう全部済んでいます")
        return
    sk = client()
    free = lambda: sk.query_mode().get("unlimited") is True
    paused = not a.boost and not free()
    if paused:  # 前は静止画のまま0で終えていた。別の回が詰まりを取っている間だけなので、次の実行で続ける（2026-10-29）
        print("Lovart が速いモードです（別の回が詰まりを取っている間）。クレジットを使わないよう、新しく頼まずに待ちます", flush=True)
        log["_runs"] -= 1  # 待っただけの実行は、3回の数に入れない
        save()
    # できたはずの物のファイルが無い時（作業フォルダが消えて、history の控えから戻した時。2026-10-30 psy 005）は、頼み直さずに
    # 同じ会話（thread）から受け取り直す。Lovart は終わった会話の結果を持っているので、クレジットも順番待ちも要らない
    for i in todo:
        if log.get(i, {}).get("状態") == "できた" and log[i].get("thread") and not a.force:
            log[i] = {"状態": "待ち", "thread": log[i]["thread"], "頼んだ時刻": time.time(), "回": log[i].get("回", 1), "受け取り直し": True}
    waiting = {i: log[i] for i in todo if log.get(i, {}).get("状態") == "待ち" and not a.force
               and (not a.boost or log[i].get("受け取り直し"))}
    queue = [i for i in todo if i not in waiting]
    checked = time.time()
    print(f"Lovart（{'速いモード' if a.boost else '無料モード'}・Kling 2.6）：新しく頼む {len(queue)} 本・前回の続き {len(waiting)} 本（同時に{a.par}本・{log['_runs']}回目の実行）", flush=True)
    while (queue and not paused and time.time() < deadline) or (waiting and time.time() < deadline + 20 * 60):
        if not a.boost and not paused and time.time() - checked > 60:
            checked = time.time()
            paused = not free()
        while queue and not paused and len(waiting) < a.par and time.time() < deadline:
            i = queue.pop(0)
            tries = log.get(i, {}).get("回", 0) + 1 if not a.force else 1
            try:
                url = sk.upload_file(os.path.join(img, i + ".png"))
                tid = sk.send(MOTION.format(scene=cuts[i]["image"]), PROJECT, attachments=[url],
                              prefer_models={"VIDEO": [MODEL]}, include_tools=[MODEL])
            except Exception as e:
                if "409" in str(e) or "429" in str(e) or "limit" in str(e).lower():  # 同時の上限（絵と分け合う）は待って頼み直す
                    print(i, "順番待ち（2分あけて頼み直す）", str(e)[:80], flush=True)
                    queue.insert(0, i); time.sleep(120); break
                log[i] = {"状態": "失敗", "理由": f"頼めなかった：{type(e).__name__} {str(e)[:200]}", "回": tries}; save()
                print(i, log[i]["理由"], flush=True)
                continue
            waiting[i] = log[i] = {"状態": "待ち", "thread": tid, "頼んだ時刻": time.time(), "回": tries}
            save()
        time.sleep(20)
        for i in list(waiting):
            w = waiting[i]
            try:
                st = sk.get_status(w["thread"])["status"]
                if st not in ("done", "abort"):
                    r = sk.get_result(w["thread"]) if int(time.time()) % 4 == 0 else {}
                    if r.get("pending_confirmation"):
                        st = "pending"
                    elif time.time() - w["頼んだ時刻"] > THREAD_MAX:
                        st = "too_long"
                    else:
                        continue
                r = sk.get_result(w["thread"])
            except Exception as e:
                print(i, "確かめられない（あとでもう一度）", str(e)[:120], flush=True)
                continue
            if r.get("pending_confirmation"):
                st = "pending"
            if st == "pending" and a.boost and not w.get("confirmed"):
                cost = (r.get("pending_confirmation") or {}).get("estimated_cost")
                try:
                    cost = float(cost if cost is not None else unit("video"))
                except (TypeError, ValueError):
                    cost = 1e9
                if cost <= 2 * unit("video") and cost <= left_today(ch):
                    try:
                        sk.confirm(w["thread"])
                    except Exception as e:
                        print(i, "確認を送れなかった（あとでもう一度）", str(e)[:120], flush=True)
                        continue
                    add_spent(ch, cost, f"{os.path.basename(a.work)} {i} の動く絵")
                    w.update({"confirmed": True, "頼んだ時刻": time.time()})
                    print(i, f"クレジット {cost:g} で進めました（今日の残り {left_today(ch)}）", flush=True)
                    continue
                print(i, f"見積もり {cost:g} が上限を超えるので進めない（今日の残り {left_today(ch)}）", flush=True)
            del waiting[i]
            tmp = os.path.join(img, "_motion_dl", i)
            got = [d["local_path"] for d in sk.download_artifacts(r, tmp, "lovart") if d.get("local_path") and d.get("type") == "video"]
            if got:
                shutil.copyfile(got[0], os.path.join(img, i + ".mp4"))
                log[i] = {"状態": "できた", "thread": w["thread"], "回": w["回"], "秒": round(time.time() - w["頼んだ時刻"])}
            elif st == "pending":
                log[i] = {"状態": "失敗", "理由": "クレジットを使う確認が出た（confirm していない）", "thread": w["thread"], "回": 2}
            else:
                why = {"too_long": "60分待っても終わらない", "abort": "Lovart 側で中止"}.get(st) or \
                      ("動画が返ってこない：" + " ".join(it.get("text", "") for it in r.get("items", []))[:200])
                log[i] = {"状態": "失敗", "理由": why, "thread": w["thread"], "回": w["回"]}
                if w["回"] < 2:
                    queue.append(i)
            shutil.rmtree(tmp, ignore_errors=True)
            print(i, log[i]["状態"], log[i].get("理由", ""), log[i].get("秒", ""), flush=True)
            save()
    ok = [i for i in cuts if os.path.exists(os.path.join(img, i + ".mp4"))]
    rest = [i for i in cuts if i not in ok and (log.get(i, {}).get("状態") == "待ち" or i in queue)]
    print(f"動く絵：できた {len(ok)}/{len(cuts)} 本・まだ {len(rest)} 本 {rest}")
    if a.boost:  # 速いモードの実行は、続きの判断を run_daily.py に任せる（このあと無料の実行が続く）
        return
    if rest and log["_runs"] < RUNS_MAX:
        sys.exit(3)
    if rest:
        print(f"{RUNS_MAX}回の実行で終わらなかった {len(rest)} 本は静止画のまま進みます")


if __name__ == "__main__":
    main()
