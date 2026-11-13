# アナザー日本紀：横動画の「冒頭の問い」の効き目を数字で見て、次の案（冒頭60秒に主役の人物の絵）へ進むかを決める（2026-11-13）
#   python -X utf8 pipeline/nihongi_open_judge.py [--dry]
# ・本人（2026-11-13）「これあなたが自分でやってよ」。手順書 v2.8 で、A01〜A05 のすぐ後（声で25秒以内）に問いを1つ置くことにした。
#   その数字を毎日の見張り（watch.yml）のあとに見て、決まりどおりに次へ進める。人に「数字を見て」と頼まない
# ・問いの位置（q_sec）：台本の声の字を頭から数え、最初の問いの文より前の字数÷6.4字/秒
#   （OneDrive の ClaudeBackup\tools\youtube\nihongi_open_check_v1.py と同じ数え方）。
#   毎日の制作の回は history/nihongi/scripts/<作業フォルダ>.json から数える。手で作った回は台本が repo に無いので、
#   history/nihongi/open_q_hand.json（手で測った値。"L007" のような頭の番号ごと）を読む。どちらにも無い回は判定に入れない
# ・30秒・60秒の維持率（r30・r60）：7日後の数字（metrics_auto.json の d7）がある横動画について、公開日から d7 を取った日までの
#   視聴維持のグラフ（audienceWatchRatio）を1回だけ取り、30秒・60秒に当たる点を読む。取った値は open_judge.json に残す
# ・判定（1回だけ）：v2.8 より後に台本を書いた横動画で、q_sec が25秒以下・r30 と r60 がある回が2本以上たまったら、
#   q_sec が25秒より遅い回（いつの回でも）の真ん中と比べる。r30 も r60 も、差が -0.03 以上（悪くなっていない）なら案2へ進む
#   進む時：手順書を v2.9 にして（v2.8 は 手順書_v2.8_<日付>.md に写す）冒頭60秒の行の下に1行足し、書き手の版の文字を直し、
#   改善ログに1行足し、Issue で知らせる。進まない時：Issue で知らせる（手順書はそのまま。冒頭の問いは続ける）
# ・書き手が守っていない時：v2.8 より後の毎日の制作の回で q_sec が25秒を超えた回が2本たまったら、1回だけ Issue
# ・--dry：YouTube から読むが、ファイルを書かず、Issue も出さない
import argparse, datetime, json, os, re, shutil, statistics, subprocess, sys, traceback, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import issue, jload, now
from run_daily import hpath, jsave
import ustore

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = "nihongi"
CPS = 6.4  # 声の速さの目安（字/秒）
Q_LINE, MIN_N, NOT_WORSE = 25, 2, -0.03
# v2.8（2026-11-13）より前に台本を書いた横動画の頭の番号。ここに無い番号は v2.8 より後の回として扱う
PRE_V28 = {f"L{n:03d}" for n in range(1, 17)} | {"L101", "L102", "L103", "L104", "L105", "L106", "L107", "L108", "L109"}
NOT_Q = ("わずか", "確か", "はるか", "ばかりか", "どころか", "静か", "豊か", "ほか", "なか", "まさか")

DOC = os.path.join(ROOT, "channels", CH, "手順書.md")
WRITER = os.path.join(ROOT, "pipeline", "write_script_nihongi.py")
KAIZEN = hpath(CH, "改善ログ.md")
ANCHOR = "  - 冒頭60秒の台本は、1枚の絵を約10秒見せる"
V_OLD, V_NEW = "v2.8", "v2.9"
H1_OLD = "# アナザー日本紀 制作ルール v2.8（2026-11-13）"


def head(work):
    return (work or "").split("_")[0]


def is_q(s):
    s = s.strip()
    if not s or s.startswith("もしも"):
        return False
    if s.endswith(("？", "?")):
        return True
    return s.endswith("か") and not s.endswith(NOT_Q)


def q_of(cuts):
    """最初の問いの文の（頭の秒, 文, カットの id）。無ければ None。nihongi_open_check_v1.py の check() と同じ数え方
    （問いの文より前の声の字数 ÷ 6.4。open_q_hand.json の値もこの数え方なので、そろえておく）"""
    pos = 0
    for c in cuts:
        for sent in re.findall(r"[^。？?！!]*[。？?！!]?", c.get("narration") or ""):
            if is_q(sent.rstrip("。")):
                return round(pos / CPS), sent.strip(), c.get("id")
            pos += len(sent)
    return None


def q_for(work, hand):
    p = hpath(CH, os.path.join("scripts", f"{work}.json"))
    if os.path.exists(p):
        r = q_of(jload(p, {}).get("cuts") or [])
        if r:
            return {"q_sec": r[0], "q_text": r[1], "q_cut": r[2], "出どころ": "scripts"}
        return {"q_sec": None, "出どころ": "scripts（問いが見つからない）"}
    h = hand.get(head(work))
    if h and h.get("q_sec") is not None:
        return {"q_sec": h["q_sec"], "q_text": h.get("q_text"), "出どころ": "open_q_hand.json"}
    return None


def curve_points(e, end):
    """公開日から end までの視聴維持のグラフから、30秒・60秒の点を読む"""
    import watch  # YouTube の鍵が要る所だけ（手元の試しでは読み込まない）
    start = e["published_at"][:10]
    q = {"ids": "channel==MINE", "startDate": start, "endDate": max(end, start), "metrics": "audienceWatchRatio",
         "dimensions": "elapsedVideoTimeRatio", "filters": f"video=={e['video_id']}"}
    r = watch.get(CH, watch.ANA + "?" + urllib.parse.urlencode(q))
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    pts = sorted((x["elapsedVideoTimeRatio"], x["audienceWatchRatio"]) for x in (dict(zip(cols, row)) for row in r.get("rows", [])))
    sec = e.get("seconds") or 0
    if not pts or not sec:
        return None
    at = lambda t: round(min(pts, key=lambda p: abs(p[0] - t / sec))[1], 4)
    return {"r30": at(30), "r60": at(60), "期間": f"{start}〜{end}", "長さ（秒）": sec}


def collect(state, hand, fetch):
    metrics = jload(hpath(CH, "metrics_auto.json"), {})
    vids = state.setdefault("videos", {})
    up = ustore.load(CH)
    if fetch:  # 手で上げた回の記録（読むだけのファイル）には公開日時と長さが無いので、見張りと同じく YouTube から読み直す
        import watch
        watch.refresh(CH, up)
    for e in up:
        if ustore.kind_of(e) != "long" or e.get("missing") or not e.get("video_id"):
            continue
        w = e["work"]
        v = vids.setdefault(w, {})
        v["v2.8より後"] = head(w) not in PRE_V28
        q = q_for(w, hand)
        if q:
            v.update(q)
        d7 = (metrics.get(w) or {}).get("d7") or {}
        if d7.get("取った日") and "r30" not in v and e.get("published_at") and fetch:
            try:
                pts = curve_points(e, d7["取った日"])
            except Exception as err:  # 1本取れなくても、ほかの回は続ける
                v["取れなかった"] = f"{type(err).__name__} {now().date()}"
                continue
            if pts:
                v.pop("取れなかった", None)
                v.update(pts, 平均視聴率=d7.get("averageViewPercentage"), 再生=d7.get("views"))
    return vids


def groups(vids):
    t = {w: v for w, v in vids.items() if v.get("v2.8より後") and v.get("q_sec") is not None and v["q_sec"] <= Q_LINE and "r30" in v}
    c = {w: v for w, v in vids.items() if v.get("q_sec") is not None and v["q_sec"] > Q_LINE and "r30" in v}
    return t, c


def med(g, k):
    return round(statistics.median(v[k] for v in g.values()), 4)


def read_keep(path):
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read()
    return raw, ("\r\n" if "\r\n" in raw else "\n")


def write_keep(path, raw):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(raw)


def plan_doc(today, nums):
    """手順書 v2.8 → v2.9 の中身を作る。思った形でなければ None（手順書は直さない）"""
    raw, eol = read_keep(DOC)
    lines = raw.split(eol)
    hit = [i for i, l in enumerate(lines) if l.startswith(ANCHOR)]
    if lines[0] != H1_OLD or len(hit) != 1:
        return None
    rule = (f"  - 冒頭60秒の6枚前後のうち2枚以上は、主役の人物の劇画（表情のアップ）にする（{today} から。冒頭の問いの数字を見て自動で足した）。"
            "動かさず、ゆっくり寄るだけ（`open_still` は守る）。光は上と同じ青緑の薄明かりで頼む。"
            "前の回の同じ人物の絵を `same_as` で使い回してもよい。頼む絵の枚数は増やさない（6枚前後のうちの2枚を人物にする）。")
    change = (f"v2.9 の変更：{today}、見張りのあとの `pipeline/nihongi_open_judge.py` が、v2.8 の冒頭の問いの数字を見て進めた"
              f"（{nums}）。変えた所：§7 の冒頭60秒の行の下に、主役の人物の絵を2枚以上にする行を1行足した。"
              f"古い版は `手順書_v2.8_{today}.md`。")
    lines[hit[0] + 1:hit[0] + 1] = [rule]
    lines[0] = f"# アナザー日本紀 制作ルール {V_NEW}（{today}）"
    lines[2:2] = [change, ""]
    return raw, eol.join(lines)


def plan_writer():
    raw, _ = read_keep(WRITER)
    old = f"制作ルール {V_OLD}"
    if raw.count(old) != 2:
        return None
    return raw, raw.replace(old, f"制作ルール {V_NEW}")


def kaizen_line(today, nums):
    return (f"- {today}｜作り方（冒頭の問いの判定・pipeline/nihongi_open_judge.py・手順書 {V_NEW}）｜（測った数字：{nums}）"
            "｜次の回で上げること：横動画の冒頭60秒の6枚前後のうち2枚以上を、主役の人物の劇画（表情のアップ）にする"
            "（動かさず、ゆっくり寄るだけ・青緑の薄明かり・冒頭の問いは続ける。ショートは前の行を続ける）")


def append_kaizen(line):
    raw, eol = read_keep(KAIZEN)
    if line in raw:
        return
    body = raw if raw.endswith(eol) or not raw else raw + eol
    write_keep(KAIZEN, body + line + (eol if raw.endswith(eol) else ""))


def go(today, nums, dry):
    """案2へ進める。書いた物を返す"""
    d, w = plan_doc(today, nums), plan_writer()
    done = []
    if dry:
        return [f"（--dry）手順書：{'直せる' if d else '形が違うので直さない'}／書き手：{'直せる' if w else '形が違うので直さない'}"]
    if d and w:
        back = os.path.join(os.path.dirname(DOC), f"手順書_v2.8_{today}.md")
        if not os.path.exists(back):
            shutil.copyfile(DOC, back)  # バイトのまま写す（改行もそのまま）
        write_keep(DOC, d[1])
        write_keep(WRITER, w[1])
        done += [os.path.relpath(p, ROOT) for p in (back, DOC, WRITER)]
    append_kaizen(kaizen_line(today, nums))
    done.append(os.path.relpath(KAIZEN, ROOT))
    # 見張りの commit は history だけを足すので、history の外で書いた物はここで足しておく
    subprocess.run(["git", "add", "--"] + [p for p in done if not p.startswith("history")], cwd=ROOT)
    return done


def judge(state, dry):
    vids = state["videos"]
    t, c = groups(vids)
    state["今の数"] = {"問い25秒以内（v2.8より後）": sorted(t), "問いが25秒より遅い": sorted(c)}
    late = sorted(w for w, v in vids.items() if v.get("v2.8より後") and (v.get("出どころ") or "").startswith("scripts")
                  and (v.get("q_sec") is None or v["q_sec"] > Q_LINE))
    if len(late) >= MIN_N and not state.get("守っていない知らせ"):
        msg = "／".join(f"{w}：" + (f"{vids[w]['q_sec']}秒「{vids[w].get('q_text')}」" if vids[w].get("q_sec") is not None else "問いが見つからない")
                       for w in late)
        if not dry:
            issue("【日本紀】横動画の冒頭の問いが25秒より遅い回が続いています",
                  f"{now():%m/%d %H:%M} v2.8 より後の毎日の制作の回：{msg}。書き手 write_script_nihongi.py が手順書 §7 の冒頭の問いを守れているか見てください")
            state["守っていない知らせ"] = now().isoformat(timespec="seconds")
    if state.get("判定") or len(t) < MIN_N or len(c) < MIN_N:
        return f"判定はまだ（問い25秒以内 {len(t)}本・遅い回 {len(c)}本。両方{MIN_N}本以上で決める）" if not state.get("判定") else "判定ずみ"
    d30, d60 = round(med(t, "r30") - med(c, "r30"), 4), round(med(t, "r60") - med(c, "r60"), 4)
    nums = (f"問い25秒以内 {len(t)}本（{'・'.join(sorted(t))}）の30秒の維持 {med(t, 'r30')}・60秒 {med(t, 'r60')}／"
            f"遅い回 {len(c)}本の真ん中 {med(c, 'r30')}・{med(c, 'r60')}／差 {d30:+}・{d60:+}")
    ok = d30 >= NOT_WORSE and d60 >= NOT_WORSE
    today = now().date().isoformat()
    if ok:
        done = go(today, nums, dry)
        line = f"{today} 案2（冒頭60秒に主役の人物の絵）へ進めました。{nums}。書いた物：{'・'.join(done)}"
        title = "【日本紀】冒頭の問いの判定：案2（冒頭の人物の絵）へ進めました"
    else:
        line = f"{today} 冒頭の問いで30秒か60秒の維持が {NOT_WORSE} より悪くなったので、案2へは進めていません。{nums}"
        title = "【日本紀】冒頭の問いの判定：案2は見送り（数字が下がった）"
    if not dry:
        issue(title, line)
        state["判定"] = {"日": today, "進めた": ok, "数字": nums}
    return line


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--dry", action="store_true")
    a.add_argument("--no-fetch", action="store_true", help="YouTube から読まない（手元の試し）")
    a = a.parse_args()
    os.environ["TZ"] = "Asia/Tokyo"
    st_p = hpath(CH, "open_judge.json")
    state = jload(st_p, {})
    try:
        collect(state, jload(hpath(CH, "open_q_hand.json"), {}), not a.no_fetch)
        print("日本紀 冒頭の問い：" + judge(state, a.dry))
    except Exception as e:
        print(traceback.format_exc())
        if not a.dry:
            issue("【止まりました】nihongi：冒頭の問いの判定で止まりました", f"{now():%m/%d %H:%M} {type(e).__name__}：{e}")
    finally:
        state["最後に見た"] = now().isoformat(timespec="seconds")
        if not a.dry:
            jsave(st_p, state)


if __name__ == "__main__":
    main()
