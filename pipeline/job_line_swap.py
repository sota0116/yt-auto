# 仕事ch：公開済み・予約中の動画の LINE リンクを、UTAGE の登録経路に替える（2026-11-01。接続を確かめたあとに1回だけ動かす）
#   python -X utf8 pipeline/job_line_swap.py [--go]
# ・--go を付けた時だけ書き換える（付けない時は、替える本数と対象だけ出す）
# ・概要欄：長尺は長尺の経路、3分以下はショートの経路に替える。title・tags など他の項目はそのまま送り返す
# ・入れてあるコメント：長尺の経路に替える
# ・history/job/uploaded.json の comment も替える（公開前の回に、古いリンクのコメントが入らないように）
# ・何度動かしても同じ：古いリンクが残っている物だけ替えるので、API の上限で途中で止まっても、もう一度動かせば続きから進む
# ・記録は history/job/line_swap.json
# ・--profile：ショートの説明文に、プロフィールのリンクへの案内の1行を足す（2026-11-02。ショートの説明欄のリンクは押せないため）。リンクとコメントは替えない
import argparse, datetime, json, os, re, sys, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from short_upload import PROFILE_NOTE
from upload_job import API, ROOT, api

CH = "job"
OLD = "https://lin.ee/wQwnVsE"
LONG = "https://utage-system.com/line/open/m1FcpYY2zwWA?mtid=obkoW3UnzT4f"
SHORT = "https://utage-system.com/line/open/m1FcpYY2zwWA?mtid=DQNRx7AqeMn5"
SHORT_MAX = 180  # 秒。YouTube のショートの上限


def get(url):
    return json.load(api(CH, "GET", url, timeout=60))


def seconds(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def videos():
    """チャンネルの全動画（非公開・予約中も）。投稿のリストから順に取る"""
    pl = get(f"{API}/channels?part=contentDetails&mine=true")["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], ""
    while True:
        r = get(f"{API}/playlistItems?part=contentDetails&maxResults=50&playlistId={pl}" + (f"&pageToken={page}" if page else ""))
        ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
        page = r.get("nextPageToken")
        if not page:
            break
    out = []
    for i in range(0, len(ids), 50):
        out += get(f"{API}/videos?part=snippet,contentDetails&id={','.join(ids[i:i+50])}").get("items", [])
    return out


def swap_description(v, go):
    sn = v["snippet"]
    if OLD not in sn.get("description", ""):
        return None
    kind = "short" if seconds(v["contentDetails"].get("duration")) <= SHORT_MAX else "long"
    new = sn["description"].replace(OLD, SHORT if kind == "short" else LONG)
    if go:
        keep = ("title", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage")
        body = {"id": v["id"], "snippet": {**{k: sn[k] for k in keep if k in sn}, "description": new}}
        api(CH, "PUT", f"{API}/videos?part=snippet", body, timeout=60)
    return kind


def add_profile_note(v, go):
    """ショートの説明文の、ショートの経路の URL の上に案内の1行を足す。足してある物と URL の無い物はそのまま"""
    sn = v["snippet"]
    desc = sn.get("description", "")
    if seconds(v["contentDetails"].get("duration")) > SHORT_MAX or SHORT not in desc or PROFILE_NOTE in desc:
        return False
    if go:
        keep = ("title", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage")
        new = desc.replace(SHORT, f"{PROFILE_NOTE}\n{SHORT}", 1)
        body = {"id": v["id"], "snippet": {**{k: sn[k] for k in keep if k in sn}, "description": new}}
        api(CH, "PUT", f"{API}/videos?part=snippet", body, timeout=60)
    return True


def profile_main(go):
    done, fails = [], []
    for v in videos():
        try:
            if add_profile_note(v, go):
                done.append(v["id"])
                print(f"  ショート：{v['id']} {v['snippet']['title'][:40]}")
        except urllib.error.HTTPError as ex:
            fails.append(f"{v['id']}：{ex.code} {ex.read()[:200]!r}")
    print(f"案内の1行を足す本数：{len(done)}")
    if go:
        lp = os.path.join(ROOT, "history", CH, "line_swap.json")
        log = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else []
        log.append({"at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds"),
                    "profile_note": done, "fails": fails})
        json.dump(log, open(lp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        print("（--go が無いので替えていません）")
    if fails:
        print("【止まった物】もう一度動かすと続きから進みます")
        print("\n".join("  " + f for f in fails))
        sys.exit(1)


def swap_comment(e, go):
    if not e.get("comment_id") or e.get("comment_gone"):
        return False
    items = get(f"{API}/commentThreads?part=snippet&id={e['comment_id']}").get("items")
    if not items:
        return False
    top = items[0]["snippet"]["topLevelComment"]
    text = top["snippet"].get("textOriginal") or e.get("comment") or ""
    if OLD not in text:
        return False
    if go:
        body = {"id": top["id"], "snippet": {"textOriginal": text.replace(OLD, LONG)}}
        api(CH, "PUT", f"{API}/comments?part=snippet", body, timeout=60)
    return True


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--go", action="store_true")
    a.add_argument("--profile", action="store_true")
    a = a.parse_args()
    if a.profile:
        return profile_main(a.go)
    hp = os.path.join(ROOT, "history", CH, "uploaded.json")
    hist = json.load(open(hp, encoding="utf-8"))
    done, fails = {"long": [], "short": [], "comment": []}, []
    for v in videos():
        try:
            kind = swap_description(v, a.go)
            if kind:
                done[kind].append(v["id"])
                print(f"  概要欄（{kind}）：{v['id']} {v['snippet']['title'][:40]}")
        except urllib.error.HTTPError as ex:
            fails.append(f"概要欄 {v['id']}：{ex.code} {ex.read()[:200]!r}")
    for e in hist:
        try:
            if swap_comment(e, a.go):
                done["comment"].append(e["video_id"])
                print(f"  コメント：{e['video_id']} {e['work']}")
        except urllib.error.HTTPError as ex:
            fails.append(f"コメント {e['video_id']}：{ex.code} {ex.read()[:200]!r}")
    pending = [e for e in hist if OLD in (e.get("comment") or "")]
    print(f"替える本数：長尺 {len(done['long'])}、ショート {len(done['short'])}、コメント {len(done['comment'])}、記録のコメント文 {len(pending)}")
    if a.go:
        for e in pending:
            e["comment"] = e["comment"].replace(OLD, LONG)
        json.dump(hist, open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        lp = os.path.join(ROOT, "history", CH, "line_swap.json")
        log = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else []
        log.append({"at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds"),
                    **done, "uploaded_json_comments": len(pending), "fails": fails})
        json.dump(log, open(lp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        print("（--go が無いので替えていません）")
    if fails:
        print("【止まった物】もう一度動かすと続きから進みます")
        print("\n".join("  " + f for f in fails))
        sys.exit(1)


if __name__ == "__main__":
    main()
