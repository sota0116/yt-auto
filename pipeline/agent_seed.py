# 手元の素材を、最初に1回だけ GitHub の Release へ置く（PC で setup_agent_github_v1.ps1 が動かす）
#   python -X utf8 pipeline/agent_seed.py <ch> [<ch> …] [--dry]
# ・共通の資料（看板・調査・動画スキル・道具）は毎回置き直す。チャンネルの素材は、すでに保存があれば置かない
#   （クラウドの方が進んでいるので、古い手元の中身で上書きしないため）
# ・--dry は上げずに、入れる物の大きさだけを出す
import glob, os, sys, tarfile, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_state as a

OD = r"C:\Users\koneb\OneDrive\YouTube自動チャンネル"
TOOLS = r"C:\Users\koneb\OneDrive\ClaudeBackup\tools"
SKILL = r"C:\Users\koneb\OneDrive\ClaudeBackup\skills\youtube-video-maker"
NAMES = {"kakure": "かくれ神語り", "shimei": "指名手配ボード"}


def shared_items(chs):
    """(元, tar の中の名前)。指示書（agent/prompt_*.md）が読む物だけ"""
    items = [(SKILL, "skill")]
    for rel in (r"youtube\loudnorm2.py", r"youtube\landscape_to_portrait.py", r"youtube\frame_crop.py", r"yt\lovart_motion_v2.py"):
        items.append((os.path.join(TOOLS, rel), "tools/" + os.path.basename(rel)))
    for rel in (r"設計\輸入候補の組み込み先_v3_2026-10-30.md", r"調査\競合_神話_2026-10-29.md", r"調査\research_thumb_title_import_2026-10-30.md"):
        items.append((os.path.join(OD, rel), rel.replace("\\", "/")))
    items.append((os.path.join(OD, r"金運おきぬ\videos\S008_切出_おみくじ\script.json"), "手本/okinu_S008/script.json"))
    for ch in NAMES:  # 共通の資料は全チャンネル分（あとで足すチャンネルが古い資料で動かないように）
        for p in glob.glob(os.path.join(OD, "設計", f"チャンネル看板_{NAMES[ch]}_v*.md")):
            items.append((p, "設計/" + os.path.basename(p)))
    miss = [p for p, _ in items if not os.path.exists(p)]
    if miss or not any("チャンネル看板" in arc for _, arc in items):
        sys.exit("【止まりました】入れる資料がありません：" + "、".join(miss or ["チャンネル看板"]))
    return items


def channel_items(ch):
    K = os.path.join(OD, NAMES[ch])
    items = [(K, ""), (os.path.join(r"C:\yt-auto\history", ch), "_history")]
    if ch == "shimei":  # BGM が各回のフォルダにしかない。上げ終えた回の wav は残さないので、素材に移す
        items.append((sorted(glob.glob(os.path.join(K, "videos", "*", "bgm_suspense1.wav")))[0], "素材/bgm/bgm_suspense1.wav"))
    return items


def size(tar_path):
    with tarfile.open(tar_path) as t:
        return len(t.getnames())


def main():
    chs = [x for x in sys.argv[1:] if not x.startswith("--")]
    dry = "--dry" in sys.argv
    bad = [c for c in chs if c not in NAMES]
    if bad:
        sys.exit(f"【止まりました】知らないチャンネル：{bad}")
    have = [] if dry else a.assets()
    os.environ.setdefault("RUNNER_TEMP", tempfile.gettempdir())
    with tempfile.TemporaryDirectory(dir=os.environ["RUNNER_TEMP"]) as tmp:
        t = os.path.join(tmp, "s.tar")
        a.pack(shared_items(chs), t)
        print(f"共通の資料：{size(t)} ファイル・{os.path.getsize(t) / 1024 ** 2:.0f}MB", flush=True)
        if not dry:
            a.upload("shared", t, tmp)
        for ch in chs:
            if a.stamps(ch, have):
                print(f"{ch} はもう保存があるので置きません（クラウドの方が新しい）", flush=True)
                continue
            K = os.path.join(OD, NAMES[ch])
            a.pack(channel_items(ch), t, a.heavy(os.path.join(K, "videos")))
            print(f"{ch}：{size(t)} ファイル・{os.path.getsize(t) / 1024 ** 2:.0f}MB", flush=True)
            if not dry:
                a.upload(ch, t, tmp)


if __name__ == "__main__":
    main()
