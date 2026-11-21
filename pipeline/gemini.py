# Gemini を呼ぶ共通部品（台本ゲート・絵ゲート・完成品ゲート・声で使う）
# ・鍵は環境変数 GEMINI_API_KEY か、YT_SECRETS_DIR の keys.env から読む。値は画面に出さない
# ・混んでいる（429・5xx）時は、待つ時間を倍にしながら5回までやり直す（設計書 §4・§5⑤）
# ・ただし「1日の回数の上限」の 429 はやり直さず、終了コード 75 で止める（上限は太平洋時間の0時＝日本時間の16時（夏時間）か17時に戻る）
# ・前払い残高が0（402）の時も、やり直さずに「残高を足して」と止める
# ・「月の使用上限（spending cap）」の 429 もやり直さずに止める（2026-11-21。やり直しの待ちで research が2日続けて時間切れになった）
# ・2026-10-24 から ask() はふだん Claude（claude -p・契約の範囲内）が答える。Gemini は前払い残高が0で、足さない方針。JUDGE=gemini で Gemini に戻せる
# ・2026-11-17 本人「Gemini でパワーアップ」：支払い設定の無いプロジェクトの無料キー GEMINI_API_KEY_FREE を足した。
#   使うのは ask_media()（動画・音声をそのまま見る／聞く。YouTube の URL も渡せる）だけ。Claude が見られない物だけを Gemini に回す。
#   無料キーの時は、残高0のキー（GEMINI_API_KEY）へは決して落ちない。無料枠に送った内容は Google の改善に使われる（公開する動画・公開の競合動画だけを渡す）
#   鍵の確かめ：python -X utf8 pipeline\gemini.py --free --ping（鍵の中身は出さない）
import base64, json, os, sys, time, urllib.error, urllib.request

API = "https://generativelanguage.googleapis.com/v1beta"
UPLOAD = "https://generativelanguage.googleapis.com/upload/v1beta/files"
TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
MEDIA_MODEL = os.environ.get("GEMINI_MEDIA_MODEL", TEXT_MODEL)
QUOTA_DAY = 75  # 1日の回数の上限に届いた時の終了コード
SPEND_CAP = "Gemini の月の使用上限に届きました"  # 止まった時の文。research.py の watch() がこの文で残りを飛ばす


def key(free=False):
    """free=True は無料キー（GEMINI_API_KEY_FREE）だけを読む。無い時は残高0のキーに落ちずに止める"""
    name = "GEMINI_API_KEY_FREE" if free else "GEMINI_API_KEY"
    if os.environ.get(name):
        return os.environ[name]
    p = os.path.join(os.environ.get("YT_SECRETS_DIR", r"C:\yt-auto-secrets"), "keys.env")
    found = None
    if os.path.exists(p):
        for line in open(p, encoding="utf-8-sig"):
            if line.strip().startswith(name + "="):
                found = line.split("=", 1)[1].strip().strip('"')  # 同じ行が2つあれば後の方（足し直した方）
    if found:
        return found
    sys.exit(f"【止まりました】{name} が見つかりません（中身は人に見せない）")


def _req(method, path, body=None, timeout=300, free=False):
    url = f"{API}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    wait = 4
    for i in range(6):
        r = urllib.request.Request(url, data=data, method=method,
                                   headers={"Content-Type": "application/json", "x-goog-api-key": key(free)})
        try:
            with urllib.request.urlopen(r, timeout=timeout) as res:
                return json.loads(res.read())
        except urllib.error.HTTPError as e:
            full = e.read().decode("utf-8", "replace")
            msg = full[:400]
            if e.code == 429 and "per_day" in full.lower().replace("perday", "per_day"):
                # 1日の回数の上限：やり直しても通らない。終了コード 75 で「あとで続き」と伝える（run_daily.py が失敗に数えない）
                print("【回数の上限】Gemini の1日の上限に届きました（日本時間の16時か17時に戻る）", file=sys.stderr, flush=True)
                raise SystemExit(QUOTA_DAY)
            if e.code == 429 and "spending cap" in full.lower():
                # 月の使用上限（2026-11-20 から無料キーで発生）：やり直しても月が替わるまで通らない。
                # 4〜64秒の待ちを5回くり返すと1本約2分かかり、43本で約89分を待つだけで使って research が時間切れになった
                raise SystemExit(f"【止まりました】{SPEND_CAP}（AI Studio の https://ai.studio/spend で確かめる）")
            if e.code == 402:  # 前払いの残高が0（2026-10-24 に2本目の声の作り直しで発生）。やり直しても通らない
                raise SystemExit("【止まりました】Gemini の前払い残高がありません。AI Studio（https://ai.studio/projects）の支払いで残高を足すと、次の実行から続きを作ります")
            if e.code in (429, 500, 502, 503, 504) and i < 5:
                time.sleep(wait); wait *= 2; continue
            raise SystemExit(f"【止まりました】Gemini {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:  # ConnectionError：長い動画を見せた時の途中切れ（2026-11-17）
            if i < 5:
                time.sleep(wait); wait *= 2; continue
            raise SystemExit(f"【止まりました】Gemini に届きません: {e}")


def models():
    out, tok = [], ""
    while True:
        r = _req("GET", "models?pageSize=200" + (f"&pageToken={tok}" if tok else ""))
        out += r.get("models", [])
        tok = r.get("nextPageToken")
        if not tok:
            return out


MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".wav": "audio/wav", ".mp3": "audio/mp3", ".mp4": "video/mp4",
        ".aac": "audio/aac", ".flac": "audio/flac", ".ogg": "audio/ogg", ".mov": "video/mov", ".webm": "video/webm"}


def upload(path, free=True):
    """動画・音声を Files API に上げる（1回の頼みに直接入れられるのは約20MBまでなので、長い動画はこちら）。
    処理が終わる（ACTIVE）まで待って、ファイルの情報（name・uri・mimeType）を返す。上げた物は48時間で消える"""
    size, mime = os.path.getsize(path), MIME[os.path.splitext(path)[1].lower()]
    try:
        r = urllib.request.Request(UPLOAD, method="POST",
                                   data=json.dumps({"file": {"display_name": os.path.basename(path)}}).encode(),
                                   headers={"Content-Type": "application/json", "x-goog-api-key": key(free),
                                            "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                                            "X-Goog-Upload-Header-Content-Length": str(size),
                                            "X-Goog-Upload-Header-Content-Type": mime})
        with urllib.request.urlopen(r, timeout=120) as res:
            url = res.headers["X-Goog-Upload-URL"]
        with open(path, "rb") as fh:
            r = urllib.request.Request(url, data=fh.read(), method="POST",
                                       headers={"Content-Length": str(size), "X-Goog-Upload-Offset": "0",
                                                "X-Goog-Upload-Command": "upload, finalize"})
        with urllib.request.urlopen(r, timeout=1800) as res:
            f = json.loads(res.read())["file"]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"【止まりました】Gemini に {os.path.basename(path)} を上げられません {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    for _ in range(120):  # 長い動画でも10分まで待つ
        if f.get("state") != "PROCESSING":
            break
        time.sleep(5)
        f = _req("GET", f["name"], free=free)
    if f.get("state") != "ACTIVE":
        raise SystemExit(f"【止まりました】Gemini が {os.path.basename(path)} を読み込めません（{f.get('state')}）")
    return f


def ask_media(prompt, files=(), youtube=(), schema=None, model=None, low_res=False, temperature=0.2):
    """動画・音声・画像をそのまま Gemini（無料キー）に見せて／聞かせて答えを受け取る。Claude には頼まない（Claude は音と動画を見られない）。
    files：手元のファイル（動画・音声は Files API で上げ、画像は直接入れる）。youtube：公開の YouTube 動画の URL（上げなくてよい）。
    low_res=True で動画の絵を粗く読む（使う量が約3分の1。音はそのまま）。使ったトークン数も返す"""
    parts, up = [], []
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if MIME[ext].startswith("image/"):
            parts.append({"inline_data": {"mime_type": MIME[ext], "data": base64.b64encode(open(f, "rb").read()).decode()}})
        else:
            u = upload(f)
            up.append(u["name"])
            parts.append({"file_data": {"mime_type": u["mimeType"], "file_uri": u["uri"]}})
    for y in youtube:
        parts.append({"file_data": {"file_uri": y}})
    parts.append({"text": prompt})
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": temperature}}
    if schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = schema
    if low_res:
        body["generationConfig"]["mediaResolution"] = "MEDIA_RESOLUTION_LOW"
    try:
        r = _req("POST", f"models/{model or MEDIA_MODEL}:generateContent", body, timeout=900, free=True)
    finally:
        for n in up:  # 待たずに消す（失敗しても48時間で消える）
            try:
                _req("DELETE", n, free=True, timeout=30)
            except SystemExit:
                pass
    cand = (r.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    if not text:
        raise SystemExit(f"【止まりました】Gemini の答えが空です（{cand.get('finishReason') or r.get('promptFeedback')}）")
    return text, r.get("usageMetadata", {})


SECRET_ENV = ("YT_SECRETS_DIR", "GEMINI_API_KEY", "GEMINI_API_KEY_FREE", "ESTAT_APP_ID", "OPENAI_API_KEY", "UTAGE_API_KEY", "LOVART_ACCESS_KEY",
              "LOVART_SECRET_KEY", "YT_CLIENT_SECRET", "YT_TOKEN_JOB", "YT_TOKEN_SPI")


def _ascii_schema(sch, names):
    """Claude の structured output は項目名が英数字だけ。日本語の項目名を p0, p1… に置き換え、意味は description に残す"""
    if not isinstance(sch, dict):
        return sch
    out = {k: _ascii_schema(v, names) for k, v in sch.items() if k not in ("properties", "required")}
    if "properties" in sch:
        out["properties"] = {}
        for k, v in sch["properties"].items():
            a = names.setdefault(k, f"p{len(names)}")
            out["properties"][a] = {**_ascii_schema(v, names), "description": k}
        out["required"] = [names[k] for k in sch.get("required", [])]
        out["additionalProperties"] = False
    return out


def _back(x, rev):
    if isinstance(x, dict):
        return {rev.get(k, k): _back(v, rev) for k, v in x.items()}
    if isinstance(x, list):
        return [_back(v, rev) for v in x]
    return x


def _ask_claude(prompt, schema=None, images=None):
    """Claude（claude -p・契約の範囲内で追加のお金なし）に聞く。画像はファイルの場所を渡して Read で見させる"""
    import shutil, subprocess
    if any(os.path.splitext(f)[1].lower() not in (".png", ".jpg", ".jpeg") for f in images or []):
        raise SystemExit("【止まりました】Claude の判定に渡せるのは画像だけです（音声・動画は不可）")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = prompt
    if images:
        p += ("\n\n添付（順に1枚目〜）。Read で全部を順に開いて見てから答えてください：\n"
              + "\n".join(f"{i + 1}. {os.path.abspath(f)}" for i, f in enumerate(images)))
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_JUDGE_MODEL", "sonnet"),
           "--allowedTools", "Read", "--output-format", "json"]
    names = {}
    if schema:
        cmd += ["--json-schema", json.dumps(_ascii_schema(schema, names), ensure_ascii=False)]
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["YT_SECRETS_DIR"] = os.path.join(root, "_no_secrets_here")  # 判定の作業から鍵の場所を見えなくする
    for i in range(3):
        r = subprocess.run(cmd, cwd=root, env=env, input=p, capture_output=True, text=True, encoding="utf-8", timeout=1800)
        try:
            d = json.loads(r.stdout)
        except json.JSONDecodeError:
            d = {"is_error": True, "result": (r.stdout + r.stderr)[-400:]}
        if not d.get("is_error"):
            if schema:
                so = d.get("structured_output")
                if so is None:
                    so = json.loads(d.get("result") or "{}")
                return json.dumps(_back(so, {v: k for k, v in names.items()}), ensure_ascii=False), {}
            return d.get("result", ""), {}
        if i < 2:
            time.sleep(30 * (i + 1)); continue
    raise SystemExit(f"【止まりました】Claude の判定が返りません：{str(d.get('result'))[:300]}")


def ask(prompt, model=None, search=False, schema=None, images=None, temperature=0.2):
    """文字で聞いて文字（schema があれば JSON）で受け取る。images には画像・音声のファイルも渡せる。使ったトークン数も返す
    2026-10-24 から、ふだんは Claude が答える（Gemini は前払い残高が0で、足さない方針）。JUDGE=gemini の時だけ Gemini"""
    if os.environ.get("JUDGE", "claude") == "claude" and not search:
        return _ask_claude(prompt, schema, images)
    parts = [{"text": prompt}]
    for im in images or []:
        parts.append({"inline_data": {"mime_type": MIME[os.path.splitext(im)[1].lower()],
                                      "data": base64.b64encode(open(im, "rb").read()).decode()}})
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": temperature}}
    if search:
        body["tools"] = [{"google_search": {}}]
    elif schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = schema
    r = _req("POST", f"models/{model or TEXT_MODEL}:generateContent", body)
    cand = (r.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    return text, r.get("usageMetadata", {})


TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")


def _pcm(data):
    """返ってきた音が、すでに wav の頭（RIFF）つきなら、中の音だけを取り出す。
    頭ごと包むと、頭の44バイトが大きな音として鳴る（2026-10-24 の1本目で、カットの切り替わりごとに「バチッ」と鳴った）"""
    import io, wave
    if data[:4] != b"RIFF":
        return data
    with wave.open(io.BytesIO(data)) as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, 24000):
            raise RuntimeError(f"Gemini TTS の音の形が想定と違う：{w.getnchannels()}ch・{w.getsampwidth() * 8}bit・{w.getframerate()}Hz")
        return w.readframes(w.getnframes())


def tts(prompt, voice, model=None):
    """声を作る。24kHz・16bit・モノラルの wav のバイト列と、使ったトークン数を返す"""
    import io, wave
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    r = _req("POST", f"models/{model or TTS_MODEL}:generateContent", body)
    pcm = _pcm(base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
    return buf.getvalue(), r.get("usageMetadata", {})


def tts_multi(turns, voices, model=None):
    """2人の掛け合いを1回で作る。voices は {"話し手の名前": "声の名前"}（2人まで）。turns は [(話し手の名前, 読む文, 話し方の指示)]。
    1日に頼める回数に上限があるので、カットごとに頼まずに、まとめて頼むのに使う。
    3.8 の TTS は、文の頭に「名前:」を書く形を断る（2026-10-24 に 400）。1行ずつ別の部品にして speechMetadata に話し手と話し方を書く"""
    import io, wave
    cfg = [{"speaker": n, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": v}}} for n, v in voices.items()]
    parts = [{"text": t, "speechMetadata": {"speaker": n, **({"style": s} if s else {})}} for n, t, s in turns]
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": cfg}}}}
    r = _req("POST", f"models/{model or TTS_MODEL}:generateContent", body)
    pcm = _pcm(base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
    return buf.getvalue(), r.get("usageMetadata", {})


if __name__ == "__main__":
    if "--free" in sys.argv and "--ping" in sys.argv:  # 無料キーの確かめ。出すのは返事の番号とモデルの名前だけ（鍵は出さない）
        ms = [m["name"] for m in _req("GET", "models?pageSize=200", free=True).get("models", [])]
        print("モデルの数:", len(ms))
        print("flash / pro:", ", ".join(n.split("/")[-1] for n in ms if ("flash" in n or "pro" in n) and "tts" not in n))
        r = _req("POST", f"models/{MEDIA_MODEL}:generateContent", {"contents": [{"parts": [{"text": "「はい」とだけ答えて"}]}]}, free=True)
        print(MEDIA_MODEL, "の返事:", r["candidates"][0]["content"]["parts"][0]["text"].strip())
        sys.exit(0)
    for m in models():
        if "generateContent" in m.get("supportedGenerationMethods", []):
            print(m["name"], "|", m.get("displayName", ""))
