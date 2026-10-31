# 「Claude が1本作る」チャンネル（agent.yml）の素材と作りかけを、暗号にして GitHub の Release に置く（2026-10-31 本人「kakure・shimei も github の無料にして」）
#   python -X utf8 pipeline/agent_state.py restore <ch>  … 共通の資料（agent_shared）と、そのチャンネルの素材（channels/<ch>）を戻す
#   python -X utf8 pipeline/agent_state.py save <ch>     … channels/<ch> を保存する。動画・声など、上げ終えた回の大きいファイルは残さない
# ・キャッシュ（毎日の制作が使う）は全体で10GBの枠があり、押し出されて消えることがある（2026-10-30 psy）。こちらは Release に置くので枠の外で、消えない
# ・リポジトリは公開なので、中身は暗号にする（甘茶の曲は音楽だけの配布が禁止・動画スキルは配布物・台本は公開前）。鍵は Secrets の AGENT_STATE_PASS
# ・1ファイル2GBまでなので分けて置き、全部上げ終えたら .done を置く。.done の無い保存は読まない（上げている途中で落ちても、前の保存が残る）
# ・保存は新しい2組を残す
import glob, json, os, re, shutil, subprocess, sys, tarfile, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.environ.get("GITHUB_REPOSITORY", "sota0116/yt-auto")
TAG = "agent-state"
PART = 1900 * 1024 * 1024
GPG = shutil.which("gpg") or r"C:\Program Files\Git\usr\bin\gpg.exe"
HEAVY_DIRS = ("_build", "voice", "sfx", "check")  # 上げ終えた回で残さない物


def gh(*a, capture=False):
    r = subprocess.run(["gh", *a, "-R", REPO], capture_output=capture, text=capture, encoding="utf-8" if capture else None)
    if r.returncode:
        sys.exit(f"【止まりました】gh {a[0]} {a[1] if len(a) > 1 else ''} が失敗しました")
    return r.stdout if capture else ""


def assets():
    return [x["name"] for x in json.loads(gh("release", "view", TAG, "--json", "assets", capture=True))["assets"]]


def stamps(key, names=None):
    """.done のある保存を、新しい順に"""
    names = assets() if names is None else names
    return sorted((n[len(key) + 1:-5] for n in names if n.startswith(key + "-") and n.endswith(".done")), reverse=True)


def gpg(pw, *a):
    subprocess.run([GPG, "-q", "--batch", "--yes", "--pinentry-mode", "loopback", "--passphrase-fd", "0", *a], input=(pw + "\n").encode(), check=True)


def password():
    pw = os.environ.get("AGENT_STATE_PASS")
    if not pw:
        sys.exit("【止まりました】AGENT_STATE_PASS がありません（中身は人に見せない）")
    return pw


def pack(items, tar_path, skip=lambda rel: False):
    """items＝[(手元のフォルダかファイル, tar の中の名前)]"""
    with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as t:
        for src, arc in items:
            if os.path.isfile(src):
                t.add(src, arc)
                continue
            for d, dirs, files in os.walk(src):
                rel_d = os.path.relpath(d, src).replace("\\", "/")
                rel_d = "" if rel_d == "." else rel_d
                dirs[:] = [x for x in dirs if x != "__pycache__" and not skip(f"{rel_d}/{x}/".lstrip("/"))]
                for f in files:
                    rel = f"{rel_d}/{f}".lstrip("/")
                    if not skip(rel):
                        t.add(os.path.join(d, f), f"{arc}/{rel}".strip("/"), recursive=False)


def upload(key, tar_path, tmp):
    pw = password()
    enc = os.path.join(tmp, "s.gpg")
    gpg(pw, "-c", "--cipher-algo", "AES256", "--compress-algo", "none", "-o", enc.replace("\\", "/"), tar_path.replace("\\", "/"))
    stamp = time.strftime("%Y%m%d%H%M%S")
    parts = []
    with open(enc, "rb") as f:
        while True:
            b = f.read(PART)
            if not b:
                break
            p = os.path.join(tmp, f"{key}-{stamp}.tar.gpg.{len(parts):03d}")
            open(p, "wb").write(b)
            parts.append(p)
    os.remove(enc)
    for p in parts:
        gh("release", "upload", TAG, p)
        os.remove(p)
    mark = os.path.join(tmp, f"{key}-{stamp}.done")
    open(mark, "w").write(str(len(parts)))
    gh("release", "upload", TAG, mark)
    names = assets()
    keep = stamps(key, names)[:2]
    for n in names:
        m = re.match(re.escape(key) + r"-(\d{14})\.", n)
        if m and m.group(1) not in keep:
            gh("release", "delete-asset", TAG, n, "-y")
    print(f"{key} を保存しました（{len(parts)} ファイル）", flush=True)


def fetch(key, dest):
    names = assets()
    st = stamps(key, names)
    if not st:
        sys.exit(f"【止まりました】{key} の保存が Release にありません（PC で setup_agent_github を動かす）")
    with tempfile.TemporaryDirectory(dir=os.environ.get("RUNNER_TEMP")) as tmp:
        parts = sorted(n for n in names if n.startswith(f"{key}-{st[0]}.tar.gpg."))
        for n in parts:
            gh("release", "download", TAG, "-p", n, "-D", tmp)
        enc = os.path.join(tmp, "s.gpg")
        with open(enc, "wb") as out:
            for n in parts:
                with open(os.path.join(tmp, n), "rb") as f:
                    shutil.copyfileobj(f, out)
                os.remove(os.path.join(tmp, n))
        tar_path = os.path.join(tmp, "s.tar")
        gpg(password(), "-d", "-o", tar_path, enc)
        os.remove(enc)
        os.makedirs(dest, exist_ok=True)
        with tarfile.open(tar_path) as t:
            t.extractall(dest, filter="data")
    print(f"{key} を戻しました（{st[0]}）", flush=True)


def done_names(videos):
    return {n for n in os.listdir(videos) if os.path.exists(os.path.join(videos, n, "uploaded.json"))} if os.path.isdir(videos) else set()


def heavy(videos):
    """上げ終えた回の大きいファイルを残さない決まり。ショートの切り出しが使うので、新しい2本の横動画の images は残す"""
    done = done_names(videos)
    longs = sorted((n for n in done if re.match(r"L?\d", n)), reverse=True)[:2]

    def skip(rel):
        m = re.match(r"videos/([^/]+)/(.*)", rel)
        if not m:
            return False
        name, rest = m.group(1), m.group(2)
        if name.startswith("_"):  # _chara_001_… _thumb_001_… _yoko_S002_…：元の回が上がったら絵は残さない（切り抜きは characters に残る）
            parts = name.split("_")
            base = parts[2] if len(parts) > 2 else ""
            return rest.startswith("images/") and any(n.startswith(base + "_") for n in done)
        if name not in done:
            return False  # 作りかけは全部残す
        if rest.startswith("images/"):
            return name not in longs
        if rest.split("/")[0] in HEAVY_DIRS:
            return True
        return "/" not in rest and rest.lower().endswith((".mp4", ".wav", ".mov"))
    return skip


def restore(ch):
    fetch("shared", os.path.join(ROOT, "agent_shared"))
    K = os.path.join(ROOT, "channels", ch)
    fetch(ch, K)
    hd = os.path.join(K, "_history")  # 最初の保存だけが持つ、PC の記録
    if os.path.isdir(hd):
        os.makedirs(os.path.join(ROOT, "history", ch), exist_ok=True)
        for p in glob.glob(os.path.join(hd, "*")):
            dst = os.path.join(ROOT, "history", ch, os.path.basename(p))
            if not os.path.exists(dst):
                shutil.copyfile(p, dst)
        shutil.rmtree(hd)


def save(ch):
    K = os.path.join(ROOT, "channels", ch)
    with tempfile.TemporaryDirectory(dir=os.environ.get("RUNNER_TEMP")) as tmp:
        t = os.path.join(tmp, "s.tar")
        pack([(K, "")], t, heavy(os.path.join(K, "videos")))
        upload(ch, t, tmp)


def main():
    cmd, ch = sys.argv[1], sys.argv[2]
    {"restore": restore, "save": save}[cmd](ch)


if __name__ == "__main__":
    main()
