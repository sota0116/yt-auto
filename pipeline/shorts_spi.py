# ⑨b ショートを本編から自動で作って上げる（千年こよみ・2026-10-30 新設。run_daily.py が本編を上げて予約を入れた直後に回す）
#   python -X utf8 pipeline/shorts_spi.py <作業フォルダ> [--dry] [--offline]
# ・本編の絵（images/_v3）はアップの後に消すので、ショートは本編と同じ実行の中で作る（手順書 §12）
# ・本数と種類（§12「teaser 1本・after 2本を基本にし、余った枠を solo で埋める」）：
#     本編に予約あり → teaser（予告の枠が空いている時だけ。無ければ solo）・after・after・solo の4本
#     本編が公開済み → after・after・solo
#     本編の日が未定 → solo・solo（after と teaser は本編の公開の日が要る）
#   千年こよみの本編は週4本・ショートの枠は毎日2つ（週14）なので、1本の本編から4本で枠がほぼ埋まる
# ・流れ：本編の状態を読む（_long.json）→ 台本の書き手（claude -p・鍵なし）が short.json … を書き、make_short_spi.py --check --offline で NG 0件まで直す
#   → ここでもう一度点検 → 組み立て → 全カットの1コマを並べて Claude が見る（§14 電子ゴミの線 1・3・4）→ 合格だけ upload_short_spi.py
#   点検・組み立て・見た目で落ちた物は、理由を渡して1回だけ書き直させる。それでも落ちた物は上げない（品質の門は下げない）
# ・1本が落ちてもほかは続ける。結果は作業フォルダの shorts_result.json。もう上げた物（<name>/uploaded.json）は飛ばす
# ・--dry：上げない（upload_short_spi.py --dry で題・説明・予約の枠を見るだけ）
import argparse, datetime, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_script import ROOT, DOCS, SECRET_ENV, doc, LEVELUP_ASK  # noqa: E402
from make_short_spi import fetch_long, CLOSE, CLOSE_TEASER, WEEK  # noqa: E402
from short_slot_spi import slot  # noqa: E402
from upload_short_spi import used_slots  # noqa: E402
import gemini  # noqa: E402

CH = "spi"
CH_DIR = os.path.join(ROOT, "channels", CH)
JST = datetime.timezone(datetime.timedelta(hours=9))
GOLDEN = [os.path.join(CH_DIR, "golden", f) for f in ("short_001_after.json", "short_001_after_2.json", "short_001_solo.json")]
HIST = os.path.join(ROOT, "history", CH, "shorts_uploaded.json")
# 改善ログ（毎日1つ上げる）はショート専用に分ける。本編の書き手は history/spi/改善ログ.md のいちばん下の行を読むので、混ぜると本編にショートの課題が入る
LEVELUP = os.path.join(ROOT, "history", CH, "改善ログ_ショート.md")
PY = [sys.executable, "-X", "utf8"]
rel = lambda p: os.path.relpath(p, ROOT).replace("\\", "/")


def jload(p, default):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def plan(work, lg):
    """作るショートの名前と種類。続きから回した時は、前に決めた物を使う（shorts_plan.json）"""
    p = os.path.join(work, "shorts_plan.json")
    if os.path.exists(p):
        return jload(p, {})
    at = lg["when"] and datetime.datetime.fromisoformat(lg["when"].replace("Z", "+00:00"))
    if lg["privacy"] == "private" and at:
        teaser_ok = slot("teaser", at, used_slots(jload(HIST, [])), datetime.datetime.now(JST)) is not None
        kinds = ["teaser" if teaser_ok else "solo", "after", "after", "solo"]
    elif at:
        kinds = ["after", "after", "solo"]
    else:
        kinds = ["solo", "solo"]
    pl = {("short" if i == 0 else f"short_{i + 1}"): k for i, k in enumerate(kinds)}
    json.dump(pl, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return pl


def close_text(kind, lg):
    if kind == "solo" or not lg["when"]:
        return None
    d = datetime.datetime.fromisoformat(lg["when"].replace("Z", "+00:00")).astimezone(JST).date()
    return (CLOSE_TEASER if kind == "teaser" else CLOSE).format(m=d.month, d=d.day, w=WEEK[d.weekday()])


def usable(work):
    """借りてよい本編のカット（語りがある・章の題のカードではない・images/_v3 に動画がある）"""
    s = jload(os.path.join(work, "script.json"), {})
    out = []
    for c in s.get("cuts", []):
        card = c.get("card") or {}
        if c.get("narration") and card.get("type") != "chapter_title" and os.path.exists(os.path.join(work, "images", "_v3", c["id"] + ".mp4")):
            out.append(f"{c['id']}（{card.get('type', 'photo')}）{c['narration'][:28]}")
    return out


def prompt(work, pl, lg, names, fixes):
    s = jload(os.path.join(work, "script.json"), {})
    at = lg["when"] and datetime.datetime.fromisoformat(lg["when"].replace("Z", "+00:00")).astimezone(JST)
    when = f"{at.month}月{at.day}日（{WEEK[at.weekday()]}）{at:%H:%M}" + ("に公開済み" if lg["privacy"] == "public" else "に公開の予約") if at else "未定"
    extra = [(os.path.join(ROOT, "history", CH, "学び.md"), "学び（週報が数字から書いた物。手順書とぶつかる時は手順書が勝つ）"),
             (LEVELUP, "ショートの改善ログ（自動で作った分。いちばん下の行の「次に上げること」を入れる）")]
    more = "".join(f"\n{i}. {rel(p)}（{w}）" for i, (p, w) in enumerate([x for x in extra if os.path.exists(x[0])], 8))
    jobs = "\n".join(f"- {rel(os.path.join(work, n + '.json'))}：kind「{pl[n]}」" + (f"。最後のカットは語り \"{{CLOSE}}\"・from \"END\"（道具が「{close_text(pl[n], lg)}」にする）" if close_text(pl[n], lg) else "")
                     for n in names)
    p = f"""あなたは YouTube チャンネル「千年こよみ」（暦・吉日・しきたりの解説。50〜60代の女性が家事の合間に見る）のショートの台本の書き手です。
本編（{rel(work)} の script.json。題「{s.get('title')}」・{when}・約{round(lg['seconds'] / 60)}分）から、縦のショートの台本を書いてください。

## 書くファイル（この{len(names)}つだけ。ほかのファイルは書き換えない）
{jobs}

## 先に全部読むファイル（部分読み禁止。手順書は最後の行まで）
1. {rel(doc(CH, '手順書.md'))}（決まりの正本。特に §4・§12・§14）
2. {rel(os.path.join(work, 'script.json'))}（本編の台本。ショートの中身はここから選ぶ。from に書くのはこのカットの id）
3. {rel(os.path.join(work, 'facts.json'))}（本編の暦の値と出典。ショートで言う日付・数・由来は、本編の語りかここにある物だけ）
4. {rel(GOLDEN[0])}・{rel(GOLDEN[1])}・{rel(GOLDEN[2])}（001 のショートの見本。形と密度だけを借りる。from は 001 の id なので写さない）
5. {rel(HIST)}（今までに上げたショート。hook（1文目）・band（帯の字）・title と同じ物・言い換えただけの物を書かない）
6. {rel(os.path.join(CH_DIR, '禁止表現.txt'))}（使わない言葉）
7. {rel(os.path.join(CH_DIR, 'profile.json'))}（チャンネルの設定）{more}

## 借りてよい本編のカット（id（絵の種類）語りの頭）
{chr(10).join(usable(work))}

## 書き方（手順書 §12 の要点。全部は手順書を見る）
- 形：{{"kind", "title"（10〜60字）, "lines"（上の帯 1〜2行・1行12字まで・金 #F2C14E の言葉は1つだけ・ほかは #FFFFFF）, "desc"（2行）, "cuts": [{{"id": "S01"…, "narration", "from", "emo"（任意）, "pan"（任意）, "peak"（いちばん面白い所に1つ。S01 と最後のカット以外）}}]}}
- 語り 170〜260字（句読点を除く）・5〜11カット・1カット40字まで。S01 は問いの形（？か「か。」で終える）。
- teaser・after：答えの一歩手前で止め、最後のカットを {{CLOSE}}・END にする。solo：答えまで言い切り、語りで本編に誘わない（「本編」と書かない）。
- 1本ずつ、別の問い・別の答え・別の1文目・別の帯の字・別の題にする。同じ回のショートどうしで、借りる絵（from）を半分以上同じにしない。同じ from は1本の中で2回まで。
- 人の出る photo と、要の図（kgrid・calendar など）を混ぜる。数か日付を声で言うのは2つまで。日付は曜日と一緒に読点で区切って言う。
- メタの言い方（この動画・今回・今日 など）と、答えの先送りだけの文（答えはこのあと・最後まで見て）を書かない。記号（──・…・※・★・→）を使わない。
- 電子ゴミの線（§14）：見た人が持ち帰れる事実（日付・由来・決まり・やり方）を1本に1つ以上入れる。本編を切っただけにしない。

## やること
1. 上のファイルを全部読む。
2. ショートの台本を書く。
3. 1本ずつ `python -X utf8 pipeline/make_short_spi.py --check --offline --name <short か short_2 …> {rel(work)}` を回し、NG が0件になるまで直す。
4. 最後に、1本ずつ「名前・kind・問い（S01）・持ち帰れる事実」を1行で書いて終える。

{LEVELUP_ASK}"""
    if fixes:
        p += f"""
## 今回は書き直し
次のショートが、点検・組み立て・見た目の確かめで落ちました。落ちた理由の所を直し、ほかは変えないでください。
{json.dumps(fixes, ensure_ascii=False, indent=1)}
"""
    return p


def write(work, pl, lg, names, fixes):
    tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(python -X utf8 pipeline/make_short_spi.py --check --offline:*)"]
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV + ("YT_TOKEN",)}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")  # 書く作業から鍵の場所を見えなくする
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_WRITER_MODEL", "opus"),
           "--allowedTools", *tools, "--permission-mode", "acceptEdits", "--output-format", "json"]
    if os.path.isdir(DOCS):
        cmd += ["--add-dir", DOCS]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(work, pl, lg, names, fixes), capture_output=True, text=True, encoding="utf-8", timeout=2700)
    open(os.path.join(work, "_write_shorts.log"), "a", encoding="utf-8").write(r.stdout + "\n" + r.stderr + "\n")
    try:
        out = json.loads(r.stdout)
        print(out.get("result", "")[-1200:])
        print(f"（Claude：{out.get('num_turns')}手・{out.get('duration_ms', 0) / 60000:.1f}分）", flush=True)
        if not fixes:
            levelup_add(work, out.get("result", ""))
    except json.JSONDecodeError:
        print(r.stdout[-1200:], r.stderr[-600:])


def levelup_add(work, result):
    """書き手の最後の「改善ログ：」の行を、日付と回の名前を付けてショートの改善ログに足す（write_script.levelup_add と同じ形）"""
    line = next((x.strip()[len("改善ログ："):] for x in reversed(result.splitlines()) if x.strip().startswith("改善ログ：")), "")
    if not line:
        print("【メモ】書き手が改善ログの行を書きませんでした")
        return
    head = "" if os.path.exists(LEVELUP) else "# ショートの改善ログ（作るたびに1行。日付｜回｜前より良くした所｜次に上げること）\n\n"
    with open(LEVELUP, "a", encoding="utf-8") as f:
        f.write(f"{head}- {datetime.datetime.now(JST):%Y-%m-%d}｜{os.path.basename(work)}｜{line}\n")


def sh(args):
    r = subprocess.run(PY + args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + "\n" + r.stderr).strip()


def look(work, name, kind):
    """組み立てた物の全カットの1コマを並べた1枚を Claude が見る（§14 電子ゴミの線 1・3・4）。問題の一覧を返す（空なら合格）"""
    code, out = sh([os.path.join(ROOT, "pipeline", "short_sheet_spi.py"), work, "--name", name])
    if code:
        return [f"1コマを並べられませんでした：{out[-200:]}"]
    cuts = jload(os.path.join(work, name, "script.json"), {}).get("cuts", [])
    S = {"type": "string"}
    sch = {"type": "object", "properties": {"合格": {"type": "boolean"}, "問題": {"type": "array", "items": S}}, "required": ["合格", "問題"]}
    goal = {"solo": "問いと答え（1本で言い切る）", "after": "問いと、答えの一歩手前（続きは本編）", "teaser": "問いと、答えの一歩手前（本編の予告）"}[kind]
    q = f"""YouTube に上げる前の縦のショート（千年こよみ・暦の解説。種類 {kind}）です。添付は、全カットの真ん中の1コマを左上から順に並べた1枚です（下の字はカットの id と語りの頭）。
語り（順に）：
{chr(10).join(f"{c['id']}：{c.get('narration', '')}" for c in cuts)}

次のどれかに当たれば不合格にし、問題を短く書いてください（当たらなければ合格・問題は空）。
1. 見た人が持ち帰れる事実（日付・由来・決まり・やり方）が1つも無い
2. {goal}が無い（本編を切っただけに見える）
3. 絵が語りと合っていない（話している物と違う物・季節や場面が違う）カットがある
4. ほとんど同じ絵が3カット以上続く
5. 絵の中の文字・表・札が画面の端で切れている、文字化けしている
6. 画面が真っ黒・真っ白・ほぼ何も映っていない、絵が崩れている（手・顔・体）"""
    t, _ = gemini.ask(q, schema=sch, images=[os.path.join(work, name, "sheet.jpg")])
    d = json.loads(t)
    return [] if d.get("合格") else (d.get("問題") or ["不合格（理由なし）"])


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--dry", action="store_true")
    a.add_argument("--offline", action="store_true", help="手元の試し：YouTube に聞かず作業フォルダの _long.json を使い、上げない")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    if not os.path.exists(os.path.join(work, "uploaded.json")):
        sys.exit("【止まりました】本編がまだ上がっていません（uploaded.json が無い）")
    if not os.path.isdir(os.path.join(work, "images", "_v3")):
        sys.exit("【止まりました】本編の絵（images/_v3）がありません（アップの後に消した回からは作れない）")
    if a.offline:
        lg = jload(os.path.join(work, "_long.json"), None) or sys.exit("【止まりました】--offline には作業フォルダの _long.json が要ります")
    else:
        lg = fetch_long(work)
        json.dump(lg, open(os.path.join(work, "_long.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    pl = plan(work, lg)
    print(f"本編：{lg['privacy']}・{lg['when'] or '日が未定'} → ショート {pl}", flush=True)
    res = jload(os.path.join(work, "shorts_result.json"), {})
    pending = [n for n in pl if not os.path.exists(os.path.join(work, n, "uploaded.json"))]
    ready, fixes = [], {}
    for rnd in range(2):  # 1回目：書く。2回目：落ちた物だけ理由を渡して書き直す
        todo = [n for n in pending if fixes.get(n) or not os.path.exists(os.path.join(work, n + ".json"))]
        if todo:
            write(work, pl, lg, todo, {n: fixes[n] for n in todo if n in fixes})
        fixes = {}
        for n in pending:
            if not os.path.exists(os.path.join(work, n + ".json")):
                fixes[n] = ["台本が書かれていない"]
                continue
            code, out = sh([os.path.join(ROOT, "pipeline", "make_short_spi.py"), work, "--check", "--offline", "--name", n])
            if code:
                fixes[n] = [x.strip()[3:] for x in out.splitlines() if x.startswith("  NG ")] or [out[-300:]]
                continue
            code, out = sh([os.path.join(ROOT, "pipeline", "make_short_spi.py"), work, "--offline", "--name", n])
            print(f"[{n}] 組み立て：{out.splitlines()[-1] if out else ''}", flush=True)
            if code or not os.path.exists(os.path.join(work, n, "short.mp4")):
                fixes[n] = [f"組み立てで止まった：{out[-300:]}"]
                continue
            bad = look(work, n, pl[n])
            print(f"[{n}] 見た目：{'合格' if not bad else '不合格 ' + ' ／ '.join(bad)}", flush=True)
            if bad:
                fixes[n] = bad
                shutil.rmtree(os.path.join(work, n), ignore_errors=True)  # 落ちた動画を残さない（書き直したら作り直す）
                continue
            ready.append(n)
        pending = list(fixes)
        if not pending:
            break
    for n, why in fixes.items():
        res[n] = {"kind": pl[n], "結果": "上げない（2回とも落ちた）", "理由": why}
        print(f"【メモ】{n}（{pl[n]}）は上げません：{' ／ '.join(why)[:300]}", flush=True)
    order = {"teaser": 0, "after": 1, "solo": 2}  # 予告の枠（本編の直前）を、先に solo が取らないように
    for n in [] if a.offline else sorted(ready, key=lambda x: order[pl[x]]):
        code, out = sh([os.path.join(ROOT, "pipeline", "upload_short_spi.py"), work, "--name", n] + (["--dry"] if a.dry else []))
        line = next((x for x in reversed(out.splitlines()) if x.startswith(("上げました", "（--dry", "【止"))), out[-200:])
        print(f"[{n}] {line}", flush=True)
        res[n] = {"kind": pl[n], "結果": line, "video_id": jload(os.path.join(work, n, "uploaded.json"), {}).get("video_id")}
    json.dump(res, open(os.path.join(work, "shorts_result.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    up = sum(1 for n in pl if os.path.exists(os.path.join(work, n, "uploaded.json")))
    print(f"ショート：{up}/{len(pl)}本を上げました")
    if a.offline:
        print(f"（--offline なので上げません。上げられる物：{ready}）")
    sys.exit(0 if a.dry or a.offline or up == len(pl) else 1)


if __name__ == "__main__":
    main()
