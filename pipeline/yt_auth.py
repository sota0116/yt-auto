# YouTube のログイン（チャンネルごとに1回。準備手順書 A6）
#   python -X utf8 pipeline\yt_auth.py login --channel job   … ブラウザでチャンネルを選んでログイン。最後にチャンネル名を出す
#   python -X utf8 pipeline\yt_auth.py check --channel job   … ログインがまだ生きているか（8日目の確かめ）。チャンネル名を出す
# ・鍵の置き場は環境変数 YT_SECRETS_DIR（無ければ C:\yt-auto-secrets）。client_secret.json を読み、token_<チャンネル>.json に保存する
# ・鍵とトークンの中身は画面に出さない
# ・追加のライブラリは要らない（vendor/youtube-video-maker/scripts/youtube_upload.py のログインを、権限4つとチャンネル別に直した物）
import argparse, base64, hashlib, http.server, json, os, secrets as _s, sys, time, urllib.error, urllib.parse, urllib.request

SEC = os.environ.get("YT_SECRETS_DIR", r"C:\yt-auto-secrets")
CLIENT = os.path.join(SEC, "client_secret.json")
# drive.file は YouTube の権限と1回のログインで一緒に頼めない（Google のエラー「scopes that cannot be requested together」）。
# ドライブは設計書の「道2」でしか使わないので、要る時に別のログインにする
SCOPES = " ".join("https://www.googleapis.com/auth/" + s for s in
                  ["youtube", "youtube.force-ssl", "yt-analytics.readonly"])
NAMES = {"job": "仕事と職場（あの仕事の年収と一生）", "spi": "スピ開運（千年こよみ）", "psy": "しずくの心理学"}


def token_path(ch):
    return os.path.join(SEC, f"token_{ch}.json")


def client():
    if not os.path.exists(CLIENT):
        sys.exit(f"【止まりました】{CLIENT} がありません。準備手順書 A4-4 で取ったファイルを、この名前で置いてください。")
    c = json.load(open(CLIENT, encoding="utf-8"))
    if "installed" not in c:
        sys.exit("【止まりました】client_secret.json が「デスクトップ アプリ」用ではありません。準備手順書 A4-4 の種類を確かめてください。")
    return c["installed"]


def post_form(url, data):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, urllib.parse.urlencode(data).encode()), timeout=60))


def save_token(ch, tok):
    os.makedirs(SEC, exist_ok=True)
    with open(os.open(token_path(ch), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        json.dump(tok, f)


def login(ch):
    c = client()
    verifier = _s.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = _s.token_urlsafe(16)
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q or "error" in q:
                got.update(q)
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("ログインできました。このタブは閉じてOKです。".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = c["auth_uri"] + "?" + urllib.parse.urlencode(dict(
        client_id=c["client_id"], redirect_uri=redirect, response_type="code", scope=SCOPES, state=state,
        access_type="offline", prompt="consent select_account", code_challenge=challenge, code_challenge_method="S256"))
    print(f"【{NAMES[ch]}】のログインです。ブラウザで A1 の Google アカウントを選び、次にこのチャンネルを選んでください。", flush=True)
    print("ブラウザが開かなければ、このURLを開いてください：\n" + url, flush=True)
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass
    while "code" not in got and "error" not in got:
        srv.handle_request()
    if "error" in got:
        sys.exit("ログインが中止されました: " + got["error"][0])
    if got.get("state", [""])[0] != state:
        sys.exit("【止まりました】ログインの返事が、このコマンドの物と合いません。もう一度 login を打ってください。")
    tok = post_form(c["token_uri"], dict(code=got["code"][0], client_id=c["client_id"], client_secret=c["client_secret"],
                                         redirect_uri=redirect, grant_type="authorization_code", code_verifier=verifier))
    missing = [s for s in SCOPES.split() if s not in tok.get("scope", "").split()]
    if missing:
        print("【注意】許可されていない権限があります：", ", ".join(s.rsplit("/", 1)[1] for s in missing))
        print("        許可の画面で全部に印を付けて、もう一度 login を打ってください。")
    if "refresh_token" not in tok:
        sys.exit("【止まりました】長く使えるログイン情報が返ってきませんでした。https://myaccount.google.com/permissions で yt-auto のアクセスを取り消してから、もう一度 login を打ってください。")
    tok["expires_at"] = time.time() + tok["expires_in"] - 60
    tok["issued_at"] = time.strftime("%Y-%m-%d")
    save_token(ch, tok)
    print("ログイン情報を保存しました：", token_path(ch))
    whoami(ch)


def access_token(ch):
    p = token_path(ch)
    if not os.path.exists(p):
        sys.exit(f"【止まりました】{ch} はまだログインしていません。先に login --channel {ch} を打ってください。")
    tok = json.load(open(p, encoding="utf-8"))
    if time.time() < tok.get("expires_at", 0):
        return tok["access_token"]
    c = client()
    try:
        new = post_form(c["token_uri"], dict(refresh_token=tok["refresh_token"], client_id=c["client_id"],
                                             client_secret=c["client_secret"], grant_type="refresh_token"))
    except urllib.error.HTTPError:
        sys.exit(f"【止まりました】{ch} のログインが切れています。同意画面が「テスト」のままだと7日で切れます（準備手順書 A4-3）。login --channel {ch} をやり直してください。")
    tok.update(new, expires_at=time.time() + new["expires_in"] - 60)
    save_token(ch, tok)
    return tok["access_token"]


def whoami(ch):
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                                 headers={"Authorization": "Bearer " + access_token(ch)})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    items = d.get("items", [])
    if not items:
        sys.exit("【止まりました】選んだアカウントに YouTube チャンネルがありません。チャンネルを選ぶ画面で、正しいチャンネルを選び直してください。")
    for it in items:
        print(f"チャンネル名：{it['snippet']['title']}（ID {it['id']}）")
    print(f"→ ここに【{NAMES[ch]}】のチャンネル名が出ていれば完了です。違っていたら Claude に言ってください。")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["login", "check"])
    p.add_argument("--channel", required=True, choices=list(NAMES))
    a = p.parse_args()
    login(a.channel) if a.cmd == "login" else whoami(a.channel)
