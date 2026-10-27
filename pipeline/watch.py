# 見張り（設計書 §2「毎日（数字の見張り。12:07 JST）」・§4「見張り役どうしで見張る」・§5⑪）
#   python -X utf8 pipeline\watch.py job [spi] [psy] [--dry]
# ・psy（しずくの心理学）は 2026-10-26 は見るだけだった。2026-10-27 から毎日の制作に入れ、在庫・公開の見張りと明日の予約もする
#   （段階 stock_phase と公開の時刻 publish_time は、チャンネルの profile.json を先に見る）
# ・上げた動画の今の状態を YouTube から読み、history\<ch>\uploaded.json に書く（published・publish_at・missing）。
#   retired の付いた回（作り直して差し替えた古い版）は missing と同じ扱い
#   毎日の実行（run_daily.py）は published の付いていない本数を在庫として数える
# ・公開された回には、チャンネルからコメントを1件入れる（説明文の1段落目＝LINE の案内とリンク。PR は付けない）。
#   入れたコメントが消された回が2本出たら、そのチャンネルはコメントをやめる（history\<ch>\watch.json の comments_off）
# ・数字：公開72時間後と7日後に、表示回数・クリック率・平均視聴率・登録・視聴維持のグラフを取り、history\<ch>\metrics.json に書く
#   表示1,000回以上でクリック率4%未満なら差し替える（72時間：タイトル2番目＋サムネB案／7日：タイトル3番目。1本2回まで）
#   クリック率は API で取れない（2026-10-28 に公式の指標の一覧で確かめた。Studio の画面だけ）。取れなかったことは watch.json に残す
#   その時、仕事ch（VIEWS_SWAP）は公開ページの再生回数で決める：同じ時点（72時間・7日）のほかの回の真ん中の7割に届かなければ差し替える
#   （比べるほかの回が2本に届かない間は差し替えない。本人「見ないから自動で」のため、Studio の「テストと比較」は待たない）
# ・型の後回し：同じ型の直近5本（7日後の数字がある回）の平均視聴率が30%未満なら history\<ch>\type_hold.json に書く（pick_neta.py が後ろに回す）
# ・在庫・公開の見張り：在庫が0本、26時間公開がない、明後日の公開予約がない（審査前。月曜はまだ無ければ Issue）
#   審査の後（STOCK_PHASE=post）は、明日の公開予約が無ければ在庫から1本を PUBLISH_TIME（無ければ 19:00）に予約する
#   （profile.json の publish_every_days が2以上のチャンネルは、前の公開からその日数があく日だけ。仕事chは 2026-10-27 から1日おき）
# ・予告ショート（history\<ch>\teasers.json。make_teaser_job.py が非公開で上げる）：長尺の公開の TEASER_AFTER 分後に公開を予約する（2026-10-28）
# ・見張り役どうしの見張り：毎日の実行が26時間ない、週報が8日ない → Issue。最後に heartbeat.json の watch を書き、HC_WATCH に合図
# ・--dry：YouTube に書かない（コメント・差し替え・予約をしない）。読むのと記録だけ
import argparse, datetime, json, os, re, statistics, sys, traceback, urllib.error, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notify import issue, ping, stale, jload, now, JST
from run_daily import hpath, jsave
from upload_job import api, API

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANA = "https://youtubeanalytics.googleapis.com/v2/reports"
CTR_LINE, IMP_LINE = 4.0, 1000
VIEWS_SWAP, VIEWS_LINE = {"job"}, 0.7  # クリック率が取れない時に、再生で差し替えを決めるチャンネルと線（ほかの回の真ん中の7割）
TEASER_AFTER = 150  # 長尺の公開から何分後に予告を出すか（19:00 の長尺なら 21:30。ショートの 20:10 から1時間20分あける）
WATCH_ONLY = {"spi"}  # 在庫・予約を持たないチャンネル（手で作って、Claude が上げる）。psy は 2026-10-27 に毎日の制作へ入れたので外した。
# spi（千年こよみ）は 2026-10-28 に見張りへ入れた（本人の指示）。手で作って上げるので、在庫0本・26時間公開なしの Issue と明日の予約はしない


def prof(ch, key, env, default):
    """チャンネルの profile.json の値（stock_phase・publish_time）を先に見る。無ければ設定値（STOCK_PHASE・PUBLISH_TIME）"""
    p = jload(os.path.join(ROOT, "channels", ch, "profile.json"), {})
    return p.get(key) or os.environ.get(env) or default


def get(ch, url):
    return json.load(api(ch, "GET", url, timeout=60))


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(JST) if s else None


def seconds(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    d, h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0, 0)
    return d * 86400 + h * 3600 + mi * 60 + s


def refresh(ch, up):
    """上げた動画の今の状態を読む。消えた動画は missing（在庫に数えない）"""
    ids = [e["video_id"] for e in up if e.get("video_id")]
    seen = {}
    for i in range(0, len(ids), 50):
        r = get(ch, f"{API}/videos?part=status,snippet,contentDetails,statistics&id={','.join(ids[i:i + 50])}")
        seen.update({it["id"]: it for it in r.get("items", [])})
    for e in up:
        it = seen.get(e.get("video_id"))
        if not it or e.get("retired"):  # retired＝作り直して差し替えた古い版（非公開のまま残す。在庫に数えない）
            e["missing"] = True
            continue
        e.pop("missing", None)
        st = it["status"]
        e["privacy_now"] = st.get("privacyStatus")
        e["publish_at"] = st.get("publishAt")
        e["seconds"] = seconds(it["contentDetails"].get("duration"))
        e["title_now"] = it["snippet"]["title"]
        e["synthetic_on"] = st.get("containsSyntheticMedia")
        e["views_now"] = int(it.get("statistics", {}).get("viewCount", 0))  # 公開ページの再生回数（アナリティクスより2〜3日早い）
        if st.get("privacyStatus") == "public" and not e.get("published"):
            e["published"] = True
            e["published_at"] = ts(it["snippet"].get("publishedAt")).isoformat(timespec="seconds")
    return seen


def comment(ch, e, state, dry):
    """公開された回にコメントを1件。7日間は残っているかを毎日確かめる
    公開の後に非公開へ戻した回（作り直す前の版など）は、コメントを入れられない（403）ので飛ばす（2026-10-25）"""
    if not e.get("published") or state.get("comments_off") or e.get("privacy_now") != "public":
        return
    if not e.get("comment_id"):
        if not e.get("comment") or dry:
            return
        body = {"snippet": {"videoId": e["video_id"], "topLevelComment": {"snippet": {"textOriginal": e["comment"]}}}}
        r = json.load(api(ch, "POST", f"{API}/commentThreads?part=snippet", body, timeout=60))
        e["comment_id"], e["comment_at"] = r["id"], now().isoformat(timespec="seconds")
        print(f"  コメントを入れました：{e['work']}")
        return
    if e.get("comment_gone") or now() - ts(e["comment_at"]) > datetime.timedelta(days=7):
        return
    if not get(ch, f"{API}/commentThreads?part=id&id={e['comment_id']}").get("items"):
        e["comment_gone"] = now().isoformat(timespec="seconds")
        gone = state.setdefault("comment_gone", [])
        gone.append(e["work"])
        if len(gone) >= 2:
            state["comments_off"] = now().isoformat(timespec="seconds")
            print("  リンクつきのコメントが2本消されたので、このチャンネルはコメントをやめます（概要欄の1行目だけにする）")


def report(ch, vid, start, metrics, dims=None):
    q = {"ids": "channel==MINE", "startDate": start, "endDate": now().date().isoformat(), "metrics": metrics,
         "filters": f"video=={vid}"}
    if dims:
        q["dimensions"] = dims
    r = get(ch, ANA + "?" + urllib.parse.urlencode(q))
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    return [dict(zip(cols, row)) for row in r.get("rows", [])]


def numbers(ch, e, state):
    start = e["published_at"][:10]
    row = (report(ch, e["video_id"], start, "views,averageViewPercentage,averageViewDuration,subscribersGained") or [{}])[0]
    try:
        imp = (report(ch, e["video_id"], start, "videoThumbnailImpressions,videoThumbnailImpressionsClickRate") or [{}])[0]
        row.update(impressions=imp.get("videoThumbnailImpressions"), ctr=imp.get("videoThumbnailImpressionsClickRate"))
        state["ctr_api"] = True
    except urllib.error.HTTPError as err:
        state["ctr_api"] = f"取れない（{err.code}）{now().date()}"
    curve = report(ch, e["video_id"], start, "audienceWatchRatio", "elapsedVideoTimeRatio")
    row["直す所"] = fixes(curve, e.get("seconds") or 0)
    return row


def fixes(curve, sec):
    """設計書 §2「離脱の位置から台本を直す規則」に当てはめる（視聴維持のグラフ＝経過の割合ごとの、見ている人の割合）"""
    if not curve or not sec:
        return []
    pts = sorted((c["elapsedVideoTimeRatio"], c["audienceWatchRatio"]) for c in curve)
    at = lambda x: min(pts, key=lambda p: abs(p[0] - x))[1]
    out = []
    if at(30 / sec) < 0.7:
        out.append("最初の30秒で30%以上が離脱 → つかみの型を変える（ネタ帳の次の3本で別の型のつかみ）")
    if at(60 / sec) < 0.5:
        out.append("1分の時点で残りが50%未満 → 前置きをさらに短くし、1文目から本編の場面に入る")
    mid = [(pts[i][0], pts[i - 1][1] - pts[i][1]) for i in range(1, len(pts)) if 0.1 <= pts[i][0] <= 0.8]
    if mid:
        x, drop = max(mid, key=lambda p: p[1])
        if drop >= 0.08:
            out.append(f"{x:.0%}あたりで急に落ちる（{drop:.0%}）→ その章を後ろに回し、クイズか山場を手前に置く")
    if at(0.8) > 0 and (at(0.8) - at(0.98)) / at(0.8) > 0.3:
        out.append("最後の2割で多く離脱 → 締めを短くする（振り返りを1文に）")
    return out


def swap(ch, e, n, dry):
    """差し替え n 回目（1：タイトル2番目＋サムネB案、2：タイトル3番目。サムネC案は週報で作る）"""
    titles = e.get("titles") or []
    if len(titles) <= n:
        return f"タイトル案が{n + 1}つ目まで無いので差し替えませんでした"
    if dry:
        return f"（--dry）差し替え{n}回目：{titles[n]}"
    it = get(ch, f"{API}/videos?part=snippet&id={e['video_id']}")["items"][0]
    sn = {k: it["snippet"][k] for k in ("title", "description", "categoryId", "defaultLanguage", "defaultAudioLanguage")
          if k in it["snippet"]}  # 送らなかった項目は消えるので、今の値をそのまま送り返す
    sn.update(title=titles[n], tags=it["snippet"].get("tags", []))
    api(ch, "PUT", f"{API}/videos?part=snippet", {"id": e["video_id"], "snippet": sn}, timeout=60)
    note = f"タイトルを「{titles[n]}」に"
    tb = os.path.join(ROOT, "channels", ch, "videos", e["work"], "thumb_b.jpg")
    if n == 1 and os.path.exists(tb):
        api(ch, "POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={e['video_id']}",
            open(tb, "rb").read(), {"Content-Type": "image/jpeg"}, timeout=120)
        note += "、サムネをB案に"
    elif n == 1:
        note += "（サムネB案のファイルが見つからないのでサムネはそのまま。週報に出す）"
    e.setdefault("swaps", []).append({"日時": now().isoformat(timespec="seconds"), "内容": note})
    return note


def watch_numbers(ch, up, state, metrics, dry):
    for e in up:
        if not e.get("published") or e.get("missing"):
            continue
        age = now() - ts(e["published_at"])
        m = metrics.setdefault(e["work"], {"type": e.get("type"), "video_id": e["video_id"]})
        if age >= datetime.timedelta(days=7) and "h72" not in m:
            m["h72"] = {"飛ばした": "見張りが72時間の時点で見られなかった（7日の数字だけ取る）"}
        for key, h in (("h72", 72), ("d7", 24 * 7)):
            if age >= datetime.timedelta(hours=h) and key not in m:
                m[key] = numbers(ch, e, state)
                m[key]["取った日"] = now().date().isoformat()
                row, n_sw = m[key], len(e.get("swaps", []))
                row["再生（公開ページ）"] = e.get("views_now")
                ctr, imp = row.get("ctr"), row.get("impressions") or 0
                if ctr is not None:
                    if imp < IMP_LINE or ctr >= CTR_LINE:
                        continue
                    why = f"クリック率 {ctr}%（表示 {imp}）"
                else:  # クリック率は API に無い（2026-10-28 に公式の指標の一覧で確かめた）。同じ時点のほかの回の再生と比べる
                    if ch not in VIEWS_SWAP or row["再生（公開ページ）"] is None:
                        continue
                    base = [x[key]["再生（公開ページ）"] for w, x in metrics.items()
                            if w != e["work"] and x.get(key, {}).get("再生（公開ページ）") is not None]
                    if len(base) < 2:
                        row["差し替えの判定"] = "比べるほかの回が2本に届かない"
                        continue
                    mid = statistics.median(base)
                    row["差し替えの判定"] = f"再生 {row['再生（公開ページ）']}・ほかの回の真ん中 {mid}"
                    if row["再生（公開ページ）"] >= mid * VIEWS_LINE:
                        continue
                    why = row["差し替えの判定"]
                if key == "h72" and n_sw == 0 or key == "d7" and n_sw < 2:
                    m[key]["差し替え"] = swap(ch, e, n_sw + 1, dry)
                    print(f"  {e['work']}：{why} → {m[key]['差し替え']}")


def type_hold(ch, metrics):
    by = {}
    for w, m in sorted(metrics.items()):
        if "d7" in m and m["d7"].get("averageViewPercentage") is not None:
            by.setdefault(m.get("type"), []).append(m["d7"]["averageViewPercentage"])
    hold = {t: round(sum(v[-5:]) / 5, 1) for t, v in by.items() if len(v) >= 5 and sum(v[-5:]) / 5 < 30}
    jsave(hpath(ch, "type_hold.json"), hold)
    return hold


def every(ch):
    """長尺の公開の間隔（日）。profile.json の publish_every_days（仕事chは 2026-10-27 から2＝1日おき）。無ければ毎日"""
    return int(prof(ch, "publish_every_days", "PUBLISH_EVERY_DAYS", 1))


def schedule_tomorrow(ch, up, dry):
    """審査の後だけ：明日の公開予約が無ければ、在庫から1本を予約する（軸の型を先に。設計書 §2）
    間隔が2日以上のチャンネルは、前の公開（予約を含む）から間隔があく日だけ入れる"""
    tom = (now() + datetime.timedelta(days=1)).date()
    days = [d.date() for d in (ts(e.get("publish_at")) or ts(e.get("published_at")) for e in up if not e.get("missing")) if d]
    if any(abs((tom - d).days) < every(ch) for d in days):
        return None if tom in days else f"明日は公開しない日（{every(ch)}日に1本）"
    axis = [t.strip() for t in (os.environ.get("AXIS_TYPES") or "").split(",") if t.strip()]
    pool = [e for e in up if not e.get("published") and not e.get("missing") and not e.get("publish_at")
            and e.get("privacy_now") == "private"]
    if not pool:
        return "在庫が無いので明日の予約を入れられません"
    pool.sort(key=lambda e: (0 if (e.get("type") or "")[:1] in axis or e.get("type") in axis else 1, e.get("uploaded_at", "")))
    e = pool[0]
    hh, mm = prof(ch, "publish_time", "PUBLISH_TIME", "19:00").split(":")
    at = datetime.datetime.combine(tom, datetime.time(int(hh), int(mm)), JST)
    if dry:
        return f"（--dry）{e['work']} を {at.isoformat()} に予約する"
    st = {"privacyStatus": "private", "publishAt": at.isoformat(), "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
              "embeddable": True, "publicStatsViewable": True}  # 送らないと予約の時にオフに戻る（2026-10-28 002 で起きた）
    api(ch, "PUT", f"{API}/videos?part=status", {"id": e["video_id"], "status": st}, timeout=60)
    e["publish_at"] = at.isoformat()
    return f"{e['work']} を {at.strftime('%m/%d %H:%M')} に予約しました"


def schedule_teasers(ch, up, dry):
    """予告の公開を、長尺の公開（予約を含む）の TEASER_AFTER 分後に予約する。
    その時刻がもう過ぎた（30分を切った）時は、次の日の同じ時刻にする。予告どうしは同じ日に重ねない"""
    p = hpath(ch, "teasers.json")
    tz = jload(p, {})
    by = {e.get("video_id"): e for e in up if not e.get("missing")}
    used = {ts(t["publish_at"]).date() for t in tz.values() if t.get("publish_at")}
    out = []
    for w, t in tz.items():
        e = by.get(t.get("long_id"))
        base = e and (ts(e.get("publish_at")) or ts(e.get("published_at")))
        if t.get("publish_at") or not base:
            continue
        at = (base + datetime.timedelta(minutes=TEASER_AFTER)).replace(second=0, microsecond=0)
        while at < now() + datetime.timedelta(minutes=30) or at.date() in used:
            at += datetime.timedelta(days=1)
        used.add(at.date())
        if dry:
            out.append(f"（--dry）{w} の予告を {at.strftime('%m/%d %H:%M')} に予約する")
            continue
        st = {"privacyStatus": "private", "publishAt": at.isoformat(), "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
              "embeddable": True, "publicStatsViewable": True}  # 送らないと予約の時にオフに戻る（2026-10-28 002 で起きた）
        try:
            api(ch, "PUT", f"{API}/videos?part=status", {"id": t["video_id"], "status": st}, timeout=60)
        except urllib.error.HTTPError as err:  # 予告が予約できなくても、本編の見張りは止めない
            t["予約の失敗"] = f"{err.code} {now().isoformat(timespec='seconds')}"
            out.append(f"{w} の予告を予約できませんでした（{err.code}）")
            continue
        t["publish_at"] = at.isoformat()
        out.append(f"{w} の予告を {at.strftime('%m/%d %H:%M')} に予約しました")
    if tz and not dry:
        jsave(p, tz)
    return out or None


def watch_channel(ch, dry):
    up_p, st_p, me_p = hpath(ch, "uploaded.json"), hpath(ch, "watch.json"), hpath(ch, "metrics.json")
    up, state, metrics = jload(up_p, []), jload(st_p, {}), jload(me_p, {})
    when = now().strftime("%m/%d %H:%M")
    if not up:
        print(f"{ch}：まだ上げた動画がありません")
        return
    try:
        refresh(ch, up)
        for e in up:
            try:
                comment(ch, e, state, dry)
            except urllib.error.HTTPError as err:  # コメントで断られても、数字と明日の予約は止めない
                e["comment_error"] = f"{err.code} {now().isoformat(timespec='seconds')}"
                print(f"  コメントを入れられませんでした（{err.code}）：{e['work']}")
        watch_numbers(ch, up, state, metrics, dry)
        state["type_hold"] = type_hold(ch, metrics)
        if prof(ch, "stock_phase", "STOCK_PHASE", "pre") == "post" and ch not in WATCH_ONLY:
            state["予約"] = schedule_tomorrow(ch, up, dry)
            state["予告の予約"] = schedule_teasers(ch, up, dry)
    finally:  # 途中で落ちても、読めた分は残す
        jsave(up_p, up)
        jsave(me_p, metrics)
    live = [e for e in up if not e.get("missing")]
    started = any(e.get("published") or e.get("publish_at") for e in live)  # 公開を始めた後だけ、公開の見張りをする
    n_stock = sum(1 for e in live if not e.get("published"))
    state.update(在庫=n_stock, 最後の見張り=now().isoformat(timespec="seconds"))
    if started and ch not in WATCH_ONLY:
        if n_stock == 0:
            issue(f"【止まりました】{ch}：在庫が0本", f"{when} 在庫（上げて、まだ公開していない動画）が0本です")
        last = max((ts(e["published_at"]) for e in live if e.get("published_at")), default=None)
        gap = 26 + 24 * (every(ch) - 1)  # 1日おきのチャンネルは50時間
        if last and now() - last > datetime.timedelta(hours=gap):
            issue(f"【止まりました】{ch}：{gap}時間公開がない", f"{when} 最後の公開：{last.strftime('%m/%d %H:%M')}")
        day2 = (now() + datetime.timedelta(days=2)).date()
        span = {day2 + datetime.timedelta(days=i) for i in range(every(ch))}  # 1日おきなら明後日か、その次の日にあればよい
        has2 = any(ts(e.get("publish_at")) and ts(e["publish_at"]).date() in span for e in live)
        state["明後日の予約"] = "あり" if has2 else f"なし（{day2}）"
        if not has2 and now().weekday() == 0:
            issue(f"【止まりました】{ch}：明後日の公開予約がない", f"{when} {day2} に公開予定の動画がありません。週報の「今週やること」の予約をしてください")
    off = [e["work"] for e in live if e.get("published") and e.get("synthetic_on") is False]
    state["AIの申告がオフ"] = off  # 週報の「今週やること」に出す（設計書 §5⑪）
    jsave(st_p, state)
    print(f"{ch}：在庫 {n_stock}本・公開済み {sum(1 for e in live if e.get('published'))}本・コメントをやめた {bool(state.get('comments_off'))}")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("chs", nargs="+", choices=["job", "spi", "psy"])
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    os.environ["TZ"] = "Asia/Tokyo"
    hb_p = os.path.join(ROOT, "history", "heartbeat.json")
    when = now().strftime("%m/%d %H:%M")
    failed = False
    for ch in a.chs:
        try:
            watch_channel(ch, a.dry)
        except SystemExit as e:  # ログインが切れた（yt_auth.py が止めた）など
            failed = True
            issue(f"【止まりました】{ch}：YouTube のログインが切れた", f"{when} 見張り：{e}")
        except Exception as e:
            failed = True
            issue(f"【止まりました】{ch}：見張りで止まりました", f"{when} {type(e).__name__}：{e}\n{traceback.format_exc()[-600:]}")
        hb = jload(hb_p, {})
        if hb.get(f"daily_{ch}") and stale(hb, f"daily_{ch}", 26):
            issue(f"【止まりました】{ch}：毎日の実行が26時間ない", f"{when} 最後の毎日の実行：{hb.get(f'daily_{ch}')}")
    hb = jload(hb_p, {})
    if hb.get("weekly") and stale(hb, "weekly", 24 * 8):
        issue("【止まりました】週報：8日動いていません", f"{when} 最後の週報：{hb.get('weekly')}")
    hb["watch"] = now().isoformat(timespec="seconds")
    jsave(hb_p, hb)
    ping("HC_WATCH", "/fail" if failed else "")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
