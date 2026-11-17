# 指摘ナレッジ（2026-11-17 本人「動画に対して行っている意見や指摘は全て記録し、言語化してナレッジとして記憶し、次に動画を生成するときの布石にしてレベルを上げていける仕組みに」）
#
# 2つの流れを分ける：
#   ・改善ログ.md … 作り手（Claude）が自分で決めた「次に上げること」（今まで通り）
#   ・指摘ナレッジ … 本人が出した指摘。原文を残し、次の動画で守る形に言い換えて、全部の作る入口で読ませる
#
# 置き場所：
#   受信箱（原文・会話から自動で拾った物）… OneDrive\YouTube自動チャンネル\指摘\受信箱.jsonl（GitHub には上げない）
#   本人の原文 … 同じフォルダの 原文.jsonl（--quote の言葉。S番号つき。GitHub には上げない）
#   ナレッジ本体 … history/_指摘/ナレッジ.json（正本。git に入るのでクラウドの制作も読める）
#     yt-auto は公開リポジトリなので、ここには言い換えたルールだけを置き、本人の原文・手元のパスは入れない（2026-11-17）
#   読ませる形 … history/_指摘/ナレッジ_<ch>.md（共通＋そのチャンネル。render が作る。手で直さない）
#
# 使い方（python -X utf8 pipeline/shiteki.py ...）：
#   add  --ch job --bunya 台本・構成 --rule "次の動画で守る1文" [--ng "..."] [--ok "..."] [--why "..."] [--quote "本人の言葉"] [--inbox I0003] [--src 会話]
#   hit  S012 [--quote "..."] [--inbox I0004]   … 同じ指摘がまた出た（回数+1。3回で「道具か手順書へ上げる」候補）
#   set  S012 --state 点検化 --note "check_job_script.py の〇〇で止める"   … 状態：有効/点検化/手順書化/廃止
#   edit S012 [--rule/--ng/--ok/--why/--bunya/--ch ...]
#   inbox [--all]           … 受信箱のまだ見ていない物
#   done I0003 [I0004 ...]  … 受信箱の物を「見た（指摘ではなかった・登録済み）」にする
#   capture --text "..." [--ch job] [--src 司令室]   … 受信箱に原文を足す（フックと見回りが使う）
#   hook                    … UserPromptSubmit フック用（標準入力の JSON を読む）
#   render                  … ナレッジ_<ch>.md を全部作り直す（add/hit/set/edit のあとは自動）
#   show <ch>               … そのチャンネルの読ませる文を表示
#   stats                   … 件数と、上げる候補
#   publish                 … ナレッジの json と md だけを GitHub の main へ送る（クラウドの書き手が読む。原文・受信箱は送らない）
import argparse, datetime, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.environ.get("SHITEKI_DIR") or os.path.join(ROOT, "history", "_指摘")  # SHITEKI_DIR は試し用
KB = os.path.join(DIR, "ナレッジ.json")
INBOX = os.environ.get("SHITEKI_INBOX") or os.path.join(os.path.expanduser("~"), "OneDrive", "YouTube自動チャンネル", "指摘", "受信箱.jsonl")
JST = datetime.timezone(datetime.timedelta(hours=9))
CHS = ["job", "psy", "spi", "nihongi", "okinu", "kakure", "shimei", "shinshiten", "tokujiro"]
CH_NAMES = {"job": "あの仕事の年収と一生", "psy": "しずくの心理学", "spi": "千年こよみ", "nihongi": "アナザー日本紀",
            "okinu": "金運おきぬ", "kakure": "かくれ神語り", "shimei": "指名手配ボード", "shinshiten": "シン視点事件簿", "tokujiro": "徳次郎"}
CH_WORDS = {"job": r"年収|あの仕事|\bjob\b", "psy": r"しずく|心理学|\bpsy\b", "spi": r"こよみ|千年|\bspi\b", "nihongi": r"日本紀|ニホンキ|nihongi",
            "okinu": r"おきぬ|okinu", "kakure": r"かくれ神|kakure", "shimei": r"指名手配|shimei", "shinshiten": r"シン視点|shinshiten", "tokujiro": r"徳次郎|tokujiro"}
BUNYA = ["台本・構成", "つかみ", "言い回し", "読み・発音", "声・音", "絵・動き", "テロップ・字", "サムネ", "題・概要欄", "本数・投稿", "その他"]
STATES = ["有効", "点検化", "手順書化", "廃止"]
PROMOTE_AT = 3
# 動画への指摘らしい言葉（フックで拾う。拾いすぎは done で落とす）
VIDEO_WORDS = r"動画|サムネ|台本|テロップ|字幕|ナレ|BGM|効果音|ショート|長尺|横動画|縦動画|尺|カット|つかみ|冒頭|フック|題|タイトル|概要欄|読み間違|読み方|発音|イントネーション|声|絵|画像|映像|動き|紙芝居|場面|セリフ|言い回し|チャンネル"
QUOTES = os.path.join(os.path.dirname(INBOX), "原文.jsonl")  # 本人の原文（公開リポジトリに入れない）
AUTO_PREFIX = ("次のファイルが今回の指示書です",)


def now():
    return datetime.datetime.now(JST)


def load():
    if os.path.exists(KB):
        return json.load(open(KB, encoding="utf-8"))
    return {"_説明": "本人の動画への指摘を言語化したルール。正本。shiteki.py で足す・直す（手で直したら render を回す）", "rules": [], "inbox_done": []}


def save(kb):
    os.makedirs(DIR, exist_ok=True)
    tmp = KB + ".tmp"
    json.dump(kb, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, KB)
    render(kb)
    print("（ナレッジを書き換えた。クラウドの書き手は GitHub の main を読むので、shiteki.py publish で送る）")


def next_id(kb):
    n = max([int(r["id"][1:]) for r in kb["rules"]] or [0])
    return f"S{n + 1:03d}"


def find(kb, rid):
    for r in kb["rules"]:
        if r["id"] == rid:
            return r
    sys.exit(f"【止まりました】{rid} がありません")


def inbox_rows():
    if not os.path.exists(INBOX):
        return []
    rows = []
    for line in open(INBOX, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def guess_ch(text, cwd=""):
    hit = [c for c, w in CH_WORDS.items() if re.search(w, text)]
    if len(hit) == 1:
        return hit[0]
    for c in CHS:
        if re.search(rf"[\\/]({c})([\\/]|$)", cwd or ""):
            return c
    return "" if not hit else ",".join(hit)


def keep_quote(rid, quote, src="", date=""):
    """本人の原文は OneDrive の 原文.jsonl に残す（ナレッジ.json は公開リポジトリに入るため）"""
    if not quote:
        return
    os.makedirs(os.path.dirname(QUOTES), exist_ok=True)
    with open(QUOTES, "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": rid, "at": date or now().date().isoformat(), "src": src, "text": quote}, ensure_ascii=False) + "\n")


def capture(text, ch="", src="会話", cwd="", session=""):
    os.makedirs(os.path.dirname(INBOX), exist_ok=True)
    rows = inbox_rows()
    iid = f"I{len(rows) + 1:04d}"
    row = {"id": iid, "at": now().isoformat(timespec="seconds"), "src": src, "ch": ch or guess_ch(text, cwd), "text": text, "cwd": cwd, "session": session}
    with open(INBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def line(r):
    s = f"- {r['id']}［{r['分野']}・{r.get('最終') or r.get('日付') or '日付不明'}］{r['ルール']}"
    if r.get("NG") or r.get("OK"):
        s += f"（NG：{r.get('NG') or '－'} → OK：{r.get('OK') or '－'}）"
    if r.get("理由"):
        s += f" 理由：{r['理由']}"
    if r.get("回数", 1) >= 2:
        s += f" ※{r['回数']}回目の指摘"
    return s


def render_text(kb, ch):
    act = [r for r in kb["rules"] if r.get("状態", "有効") == "有効" and (r["ch"] == "all" or ch in r["ch"].split(","))]
    done = [r for r in kb["rules"] if r.get("状態") in ("点検化", "手順書化") and (r["ch"] == "all" or ch in r["ch"].split(","))]
    name = CH_NAMES.get(ch, ch)
    out = [f"# 指摘ナレッジ（{name}・key {ch}）",
           "",
           "本人が出来上がった動画を見て出した指摘を、次の動画で守る形に言い換えた物。shiteki.py が作る（手で直さない。正本は history/_指摘/ナレッジ.json）。",
           "",
           "## 使い方（作る前・作った後）",
           "1. 作り始める前に、この下の全部を最後まで読む。チャンネル別の決まり（看板・手順書・点検）とぶつかる時は、日付が新しいほうを守り、記録に「ぶつかった所：S番号と手順書の節」を1行書く（持ち主が手順書を直す材料）。",
           "2. 台本・題・サムネの字・絵の指示を書き終えたら、下の1つずつに当たっていないかを見て、当たっていたら直してから先へ進む（「全部OK」とまとめて書かない）。",
           "3. 最後の報告に1行：「指摘ナレッジ：n件を確認・直した所 m か所（主な1つ S番号）」。",
           "4. 同じ間違いをまたしてしまった時は、報告に S番号を書く（持ち主が shiteki.py hit で数える。3回で道具か手順書へ上げる）。",
           ""]
    if not act:
        out.append("（まだありません）")
    for b in BUNYA:
        rs = [r for r in act if r["分野"] == b]
        if rs:
            out.append(f"## {b}")
            out += [line(r) for r in sorted(rs, key=lambda r: (r["ch"] != "all", r["id"]))]
            out.append("")
    if done:
        out.append(f"（ほかに {len(done)} 件は点検のプログラムか手順書に入れ済みなので、ここには載せない）")
    return "\n".join(out).rstrip() + "\n"


def render(kb=None):
    kb = kb or load()
    os.makedirs(DIR, exist_ok=True)
    for ch in CHS:
        open(os.path.join(DIR, f"ナレッジ_{ch}.md"), "w", encoding="utf-8").write(render_text(kb, ch))


def text_for(ch):
    """作る道具（write_script.py など）が指示書に足すための文。無ければ空"""
    p = os.path.join(DIR, f"ナレッジ_{ch}.md")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def hook():
    """UserPromptSubmit：動画への指摘らしい発言を受信箱に原文で残し、Claude に言語化を促す。何があっても止めない"""
    try:
        d = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
        text = (d.get("prompt") or "").strip()
        if not text or text.startswith(AUTO_PREFIX) or len(text) > 4000 or not re.search(VIDEO_WORDS, text):
            return
        cwd = d.get("cwd") or ""
        row = capture(text, src="会話", cwd=cwd, session=d.get("session_id") or "")
        msg = (f"【指摘ナレッジ】この発言は受信箱 {row['id']}（推定ch：{row['ch'] or '不明'}）に原文で残した。"
               "動画（台本・つかみ・言い回し・読み・声・絵・テロップ・サムネ・題など）への指摘や好みが入っているなら、直す作業と同じターンで "
               "`python -X utf8 C:\\yt-auto\\pipeline\\shiteki.py add --ch <ch|all> --bunya <分野> --rule \"次の動画で守る1文\" --ng \"…\" --ok \"…\" --why \"…\" "
               f"--quote \"本人の言葉\" --inbox {row['id']}` で言語化して登録する（既にあるルールの再発なら `hit S番号 --inbox {row['id']}`。"
               "先に `shiteki.py show <ch>` で重複を見る）。小さな指摘も1件ずつ登録する。動画への指摘でなければ "
               f"`shiteki.py done {row['id']}`。登録したら返答の最後に「指摘ナレッジ：S番号」を1行書く。")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}}, ensure_ascii=False))
    except Exception as e:  # フックは会話を止めない
        try:
            with open(os.path.join(os.path.dirname(INBOX), "_hook_error.log"), "a", encoding="utf-8") as f:
                f.write(f"{now().isoformat()} {e!r}\n")
        except Exception:
            pass


def publish():
    """ナレッジ（history/_指摘 の json と md だけ）を GitHub の main へ送る。原文と受信箱は送らない。
    手元の C:\\yt-auto はクラウドとずれているので、別の置き場（%LOCALAPPDATA%\\yt-auto-shiteki）に取り出して送る"""
    import shutil, subprocess
    url = "https://github.com/sota0116/yt-auto.git"
    wd = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "yt-auto-shiteki")
    g = lambda *a, check=True: subprocess.run(["git", "-C", wd, *a], check=check, capture_output=True, text=True, encoding="utf-8")
    if not os.path.isdir(os.path.join(wd, ".git")):
        subprocess.run(["git", "clone", "-q", "--depth", "50", url, wd], check=True)
    g("fetch", "-q", "origin", "main"); g("checkout", "-q", "-B", "main", "origin/main")
    dst = os.path.join(wd, "history", "_指摘"); os.makedirs(dst, exist_ok=True)
    names = ["ナレッジ.json"] + [f"ナレッジ_{c}.md" for c in CHS]
    for n in names:
        shutil.copyfile(os.path.join(DIR, n), os.path.join(dst, n))
    g("add", "--", *[os.path.join("history", "_指摘", n) for n in names])
    if not g("diff", "--cached", "--quiet", check=False).returncode:
        print("送る変更なし（GitHub と同じ）"); return
    kb = load()
    g("commit", "-q", "-m", f"指摘ナレッジ更新：全{len(kb['rules'])}件（有効 {sum(r['状態'] == '有効' for r in kb['rules'])}）")
    r = g("push", "-q", "origin", "HEAD:main", check=False)
    if r.returncode:
        g("pull", "-q", "--rebase", "origin", "main"); r = g("push", "-q", "origin", "HEAD:main", check=False)
    head = g("rev-parse", "HEAD").stdout.strip(); remote = g("ls-remote", "origin", "main").stdout.split()[:1]
    print(("送った " if [head] == remote else "【送れなかった】") + head[:7], r.stderr.strip()[-300:])


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--ch", required=True); a.add_argument("--bunya", required=True); a.add_argument("--rule", required=True)
    a.add_argument("--ng", default=""); a.add_argument("--ok", default=""); a.add_argument("--why", default="")
    a.add_argument("--quote", default=""); a.add_argument("--inbox", default=""); a.add_argument("--src", default="会話")
    a.add_argument("--date", default=""); a.add_argument("--note", default="")
    h = sub.add_parser("hit"); h.add_argument("id"); h.add_argument("--quote", default=""); h.add_argument("--inbox", default="")
    s = sub.add_parser("set"); s.add_argument("id"); s.add_argument("--state", required=True, choices=STATES); s.add_argument("--note", default="")
    e = sub.add_parser("edit"); e.add_argument("id")
    for k in ("rule", "ng", "ok", "why", "bunya", "ch"):
        e.add_argument(f"--{k}")
    i = sub.add_parser("inbox"); i.add_argument("--all", action="store_true")
    dn = sub.add_parser("done"); dn.add_argument("ids", nargs="+")
    c = sub.add_parser("capture"); c.add_argument("--text", required=True); c.add_argument("--ch", default=""); c.add_argument("--src", default="手入力")
    sub.add_parser("hook"); sub.add_parser("render"); sub.add_parser("stats"); sub.add_parser("publish")
    sh = sub.add_parser("show"); sh.add_argument("ch")
    x = ap.parse_args()

    if x.cmd == "hook":
        return hook()
    if x.cmd == "publish":
        return publish()
    if x.cmd == "capture":
        print(capture(x.text, x.ch, x.src)["id"]); return
    kb = load()
    today = now().date().isoformat()
    if x.cmd == "add":
        for c_ in x.ch.split(","):
            if c_ not in CHS + ["all"]:
                sys.exit(f"【止まりました】知らないチャンネル：{c_}（{'/'.join(CHS)}/all）")
        if x.bunya not in BUNYA:
            sys.exit(f"【止まりました】分野は {'/'.join(BUNYA)} のどれか")
        r = {"id": next_id(kb), "ch": x.ch, "分野": x.bunya, "ルール": x.rule, "NG": x.ng, "OK": x.ok, "理由": x.why,
             "出典": [s_ for s_ in (x.inbox, x.src) if s_], "日付": x.date or today,
             "最終": x.date or today, "回数": 1, "状態": "有効", "メモ": x.note}
        kb["rules"].append(r)
        keep_quote(r["id"], x.quote, x.src, x.date)
        if x.inbox and x.inbox not in kb["inbox_done"]:
            kb["inbox_done"].append(x.inbox)
        save(kb); print(f"{r['id']} を足した（{r['ch']}・{r['分野']}）")
    elif x.cmd == "hit":
        r = find(kb, x.id)
        r["回数"] = r.get("回数", 1) + 1; r["最終"] = today
        keep_quote(r["id"], x.quote, x.inbox or "hit")
        if x.inbox:
            r["出典"].append(x.inbox)
            if x.inbox not in kb["inbox_done"]:
                kb["inbox_done"].append(x.inbox)
        save(kb)
        print(f"{r['id']} は {r['回数']} 回目")
        if r["回数"] >= PROMOTE_AT and r["状態"] == "有効":
            print(f"【上げる候補】{r['id']} は{r['回数']}回出た。人の注意に頼らず、点検のプログラムか手順書に入れて set {r['id']} --state 点検化/手順書化 にする")
    elif x.cmd == "set":
        r = find(kb, x.id); r["状態"] = x.state
        if x.note:
            r["メモ"] = x.note
        save(kb); print(f"{r['id']} → {x.state}")
    elif x.cmd == "edit":
        r = find(kb, x.id)
        for k, key in (("rule", "ルール"), ("ng", "NG"), ("ok", "OK"), ("why", "理由"), ("bunya", "分野"), ("ch", "ch")):
            v = getattr(x, k)
            if v is not None:
                r[key] = v
        save(kb); print(f"{r['id']} を直した")
    elif x.cmd == "inbox":
        rows = [r_ for r_ in inbox_rows() if x.all or r_["id"] not in kb["inbox_done"]]
        for r_ in rows:
            print(f"{r_['id']} {r_['at'][:16]} [{r_['ch'] or '?'}] {r_['src']}：{r_['text'][:300]}")
        print(f"（{len(rows)} 件）")
    elif x.cmd == "done":
        for i_ in x.ids:
            if i_ not in kb["inbox_done"]:
                kb["inbox_done"].append(i_)
        save(kb); print(f"{len(x.ids)} 件を見た扱いにした")
    elif x.cmd == "render":
        render(kb); print(f"{len(CHS)} チャンネル分を作った（{DIR}）")
    elif x.cmd == "show":
        print(render_text(kb, x.ch))
    elif x.cmd == "stats":
        from collections import Counter
        rs = kb["rules"]
        print(f"全 {len(rs)} 件：" + "・".join(f"{k} {v}" for k, v in Counter(r['状態'] for r in rs).items()))
        print("ch：" + "・".join(f"{k} {v}" for k, v in Counter(r['ch'] for r in rs).most_common()))
        print("分野：" + "・".join(f"{k} {v}" for k, v in Counter(r['分野'] for r in rs).most_common()))
        up = [r for r in rs if r.get("回数", 1) >= PROMOTE_AT and r["状態"] == "有効"]
        print(f"上げる候補（{PROMOTE_AT}回以上・有効）：" + ("、".join(f"{r['id']}×{r['回数']}" for r in up) or "なし"))
        print(f"受信箱の未処理：{len([r_ for r_ in inbox_rows() if r_['id'] not in kb['inbox_done']])} 件")


if __name__ == "__main__":
    main()
