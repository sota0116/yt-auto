# ③台本（千年こよみ spi・2026-10-29 新設）：Claude（claude -p）に、手順書と見本（001）から script.json を書かせる
#   python -X utf8 pipeline/write_script_spi.py <作業フォルダ> --ch spi [--fix]
# ・作業フォルダには neta.json と facts.json（暦の欄 "koyomi" 入り）が先にあること（pick_neta_spi.py が置く）
# ・日付・曜日・六曜・選日・重なり・回数は、facts.json の "koyomi"（koyomi_spi.py が暦の固定ファイルだけから作った値）だけを使わせる。
#   Claude に暦の計算をさせない（手順書 §8）。書いたあとに "koyomi" の欄はプログラムが作り直して上書きする（書き手が変えても戻る）
# ・由来・行事の言い伝えの出典は、Claude が WebSearch・WebFetch で調べて facts.json の "sources" に書く（手順書 §4 の事実の決まり）
# ・見本 001（channels/spi/golden）は形だけを借りる（項目名・カードの形・カットの長さ）。中身の場面・言い回しは写さない
# ・書く前に読ませる物：手順書（全部）・学び.md（あれば全部）・改善ログのいちばん下の「次に上げること」・競合メモ（あれば）
# ・書く作業には鍵を渡さない（write_script.py と同じ。子のプロセスから鍵の場所と鍵の環境変数を消して動かす）
# ・Claude は書いたあと check_spi_script.py を自分で回し、NG が0件になるまで直す。最後にここでもう一度回して確かめる
# ・--fix：gate_script.json（台本ゲートの不合格）を読ませて、不合格の所だけ直させる（書き直しは2回まで。run_daily.py が数える）
# ・モデルは環境変数 CLAUDE_WRITER_MODEL（無ければ opus）
# ・決まった値（型・骨組み・公開日・つかみの型・案内文の番号・画風・描かない物・声・速さ）は、書いたあとにプログラムが入れる
import argparse, json, os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_script import ROOT, DOCS, SECRET_ENV, doc, levelup, levelup_add, LEVELUP_ASK  # noqa: E402
from write_script_psy import recent  # noqa: E402
import koyomi_spi as KS  # noqa: E402

CH_DIR = os.path.join(ROOT, "channels", "spi")
GOLDEN = os.path.join(CH_DIR, "golden", "script_001.json")
GOLDEN_FACTS = os.path.join(CH_DIR, "golden", "facts_001.json")
LEVELUP_CH = os.path.join(CH_DIR, "改善ログ.md")  # 手で作った回の改善ログ（2026-10-28 から）。自動の回は history/spi/改善ログ.md に足す
STYLE = "淡い水彩と和紙の風合い、朱と金と生成りの配色、やわらかい光、日本の四季の暮らし"  # 手順書 §6
AVOID = "読める文字、実在の神社の社名の額と紋、実在の神職や僧侶、有名なキャラクターに似た顔、仏像の顔の大写し、語り手の姿"  # 手順書 §6（語り手の姿は 001 と同じく足す）
BGM_CREDIT = "BGM：甘茶の音楽工房 https://amachamusic.chagasi.com/"


def extra_docs(ch):
    """あれば全部読む物：学び（weekly.py が毎週書く）・競合メモ（research.py が毎日書く）・改善ログ（2か所）"""
    out = []
    for p, what in ((os.path.join(ROOT, "history", ch, "学び.md"),
                     "学び（うちの回の数字から週報が書いた物。全部読む。手順書とぶつかる時は手順書が勝つ）"),
                    (os.path.join(ROOT, "history", ch, "competitors", "競合メモ.md"),
                     "競合メモ（毎日の競合リサーチ。型と「次の回で試すこと」を、手順書の決まりの中で1つ取り入れてよい。文・題は写さない）"),
                    (LEVELUP_CH, "改善ログ（手で作った回の分）"),
                    (levelup(ch), "改善ログ（自動で作った回の分）")):
        if os.path.exists(p):
            out.append((p, what))
    return out


def prompt(work, ch, fix):
    rel = lambda p: os.path.relpath(p, ROOT).replace("\\", "/")
    more = "".join(f"\n{i}. {rel(x)}（{what}）" for i, (x, what) in enumerate(extra_docs(ch), 9))
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8"))
    p = f"""あなたは YouTube チャンネル「千年こよみ」（暦・吉日・しきたりの解説。50〜60代の女性が家事の合間に耳で聞く）の台本の書き手です。
作業フォルダ {rel(work)} に script.json を書き、facts.json の "sources" と "quotes" に出典を書き足してください。

## 先に全部読むファイル（部分読み禁止。手順書は最後の行まで）
1. {rel(doc(ch, '手順書.md'))}（このチャンネルの決まりの正本。§1〜§14 を全部読む）
2. {rel(os.path.join(work, 'neta.json'))}（この回の題・型・骨組み・公開日・つかみの型・案内文の番号。ネタ選びが決めた値。書き換えない）
3. {rel(os.path.join(work, 'facts.json'))}（"koyomi" の欄が、この回で使ってよい日付・曜日・六曜・選日・重なり・回数の全部）
4. {rel(GOLDEN)}（1本目の台本。形と密度の見本。項目名・カードの形・1カットの長さ・決まった文の置き方・tts_text の付け方を借りる。中身の場面・言い回し・つかみは写さない）
5. {rel(GOLDEN_FACTS)}（1本目の出典台帳。一次資料と二次資料の分け方の見本）
6. {rel(os.path.join(CH_DIR, 'profile.json'))}（チャンネルの設定）
7. {rel(os.path.join(CH_DIR, '禁止表現.txt'))}（使わない言葉。台本ゲートでも照らす）
8. {rel(os.path.join(CH_DIR, 'characters', 'characters.json'))}（絵に出る人。chars に書けるのはこの id だけ）{more}

## この回（neta.json の要点）
題：{neta.get('題')}／型：{neta.get('type')}／骨組み：{neta.get('frame')}／公開日：{neta.get('pub_date')}（{neta.get('pub_wd', '')}）／つかみの型：{neta.get('hook_type')}
LINE の案内文の番号：{neta.get('line_copy')}／登録の呼びかけの番号：{neta.get('sub_copy')}／向ける人の手がかり：{neta.get('target')}

## 直近の回（同じつかみ・同じ場面・同じ言い回しを使わない材料）
数字がある回は、平均視聴率（averageViewPercentage）とクリック率（ctr）の高い回の、つかみの形・章の引き・タイトルとサムネの言葉の型を参考にする。
「直す所」（見る人が離れた所）と同じ作りは避ける。数字が2本に満たない時は、数字で決めつけない。
{json.dumps(recent(ch), ensure_ascii=False, indent=1)}

## 暦の値の決まり（いちばん大事）
- 台本・タイトル・サムネ・カードに出す日付・曜日・六曜・干支・選日・重なり・回数は、facts.json の "koyomi" の欄にある値だけを使う。
  自分で暦を数えたり計算したりしない。欄に無い値が要る時は、その話をやめて欄にある値で組み立てる。
- 日付を声で言う時は、"声で言う形"（「12月16日、水曜日」）のように、曜日と一緒に読点で区切る。年が変わる日付は「2027年」を足す。
- calendar カードの marks は "月ごと" の "カレンダーの印" から選ぶ（lab は略称「天赦」「万倍」「寅」「己巳」「巳」を「・」でつなぐ形のまま）。
- next_table カード（「次の重なり」の表。どの回にも1枚）の rows は "次の重なり_公開日から近い順"（この回の重なりが主役の回は "この回の重なり" の "公開日から近い順"）の
  頭から3つまでを、date（「12月16日」）・wd（「水」）・names（"天赦日 × 一粒万倍日" の形）のまま写す。1行目の日付を、どこかのカットで曜日つきで声で言う。
- tally カードの数は "月ごと" の "数" か "年ごと" の値。title は「2027年の〜」「2027年3月の〜」のように年（と月）から始める。
- 「最強開運日」と呼ぶのは "最強開運日_天赦日と一粒万倍日が重なる日" の日付だけ。
- facts.json の "koyomi" の欄は書き換えない（あとでプログラムが作り直して上書きする）。

## 出典の決まり（由来・言い伝え・行事）
- 由来・言い伝え・行事の説明は、出典のある物だけ。"koyomi" の "行事の出典" にある物はそのまま使い、足りない時は WebSearch・WebFetch で
  国立国会図書館「日本の暦」・国立天文台 暦計算室・神社本庁・各神社や自治体の公式サイトを先に探す（観光・情報サイトは二次資料として分けて書く）。
- 読めた範囲から外れることは書かない。二次資料しか無い説明は、声で「〜と言い伝えられてきました」「〜とされています」の形にとどめる。
- facts.json の "sources" に {{"key": {{"name", "url", "kind"（一次／二次）, "used_for"（使ったカットの id の配列）}}}} の形で書き足す。
  原文を quote カードや tate で出す時は "quotes" に {{"cut", "text", "source"（sources の key）}} を書く。
- 昔の場面（"era"）の道具・服・建物は、出典のある物だけを描かせる（sources の used_for にそのカットの id を入れる）。

## script.json の形（001 の形との違いに気をつける）
- 一番上の項目：target（この回は誰に向けるか1行）・titles（3案。§7）・thumb・thumb_bg（"THUMB"）・desc・tags（10個前後）・cuts。
  type・frame・pub_date・window・target_month・hook_type・line_copy・sub_copy・style・avoid・card_theme・voice・tempo・gap・title は、
  書かなくてよい（書いたあとにプログラムが neta.json と profile.json の値で入れる）。
- cuts の1つ：id（"A01" のような英字1つ＋数字2つ。全カットで別々）・narration・（読みを直す時だけ）tts_text・（聞き手を入れる回だけ）speaker。
  - 章の頭のカットに "chapter": "章の名前"（001 の yt_chapter の代わり。目次と点検が使う）と、001 と同じ chapter_title のカードを付ける。
  - 図のカット："card" に 001 と同じ形のカード（big_text・quote・rules・calendar・next_table・tally・timeline・kgrid・two_cards・chapter_title）。
    型と項目は 001 で使っている物だけにする（描く道具 motion_cards_spi.html がその形しか描けない）。
  - 場面の絵のカット：card を付けない。"image" に、絵を作るAIへの頼み方を日本語で書く（季節・時間帯・場所・人が何をしているか・表情。手順書 §6）。
    人は "chars": ["kazue"] のように characters.json の id で（1カット2人まで）。人のいない絵は "nobody": true（場面の絵の3割まで）。
    写真の上に出す札は "photo": {{"pop": {{"small", "big", "side"}}, "tag", "tag_sub", "tate": {{"text", "by"}}}}（001 の photo カードの pop・tag・tate と同じ形）。
    昔の場面は "era": "江戸" のように時代の名前（画面の右上に「再現イメージ」が出る）。
    001 の image_en・img_src・"card": {{"type": "photo"}} は手で作った時の形なので使わない。
  - 動く場面："motion": true を、場面の絵のカットの1〜2割に付ける（Kling で5秒動かす。card の無いカットだけ）。
  - 同じ絵を続けて使うカットは "same_as": "前のカットの id"（全体の1割まで）。
  - 見どころ：山場のカット1つ以上に "peak": true と "strong": true を書き、動くカード（図のカードか motion）と言葉の札（big_text・pop）で目立たせる。締めの3カットには付けない。
  - どの章にも、図のカードか motion の場面を1つ以上置く（紙芝居にしない。§6）。
- サムネの背景のカット：cuts の最後に {{"id": "THUMB", "image": "…", "chars": [...]}}（narration は書かない）。§7 の「サムネの絵の頼み方」の①〜⑤を image に入れる。
- thumb：{{"top": "上の段（何の話か）12字まで", "big": "下の段（答え）8字まで", "hl": ["色を変える1語"], "tag": "（任意）左下の札。例 12/16（水）"}}。
  「AI」「PR」「ランキング」「人気」は入れない。日付は "koyomi" の値だけ。
- desc（概要欄）：001 の形に合わせる。1行目は「{{特典の名前}}を、LINEで無料で受け取れます。」（特典は手順書 §4 の表のこの型の行）、2行目は {{LINE_URL}}。
  出典の一覧（facts.json の sources の名前と url）・「{BGM_CREDIT}」・§4 の AI の行（1つ目の文をそのまま1行で）・{{CHAPTERS}}（目次。アップの時に置き換わる）・
  「{(json.load(open(os.path.join(CH_DIR, 'profile.json'), encoding='utf-8')).get('voicevox') or {}).get('credit', '音声：VOICEVOX:玄野武宏')}」を入れる。PR の文字は入れない。

## やること
1. 上の8つ（と足したファイル）を全部読む。改善ログは2つの「いちばん下の行」の日付を比べ、新しい方の「次に上げること」をこの回に入れる。
2. 出典を調べて facts.json の sources・quotes に書き足す（"koyomi" の欄は触らない）。
3. 手順書 §3（この型と骨組み）・§4・§6・§7 の決まりを全部守って script.json を書く（3,000〜3,800字・95〜110カット・つかみ〜前置き240〜420字・
   LINE の案内は40〜45%・登録の呼びかけは65%・決まった文は neta.json の番号の文そのまま・締めにコメントへの問いかけ・メタと先送りの言い方を使わない）。
4. 終わる前に必ず `python -X utf8 pipeline/check_spi_script.py {rel(work)}` を回し、NG が0件になるまで直す（注意は、直せる物は直す）。
5. 最後に、語りの字数・カット数・章の名前・LINE の案内と登録の呼びかけの位置（%）・使った出典の数を1行ずつ書いて終える。

{LEVELUP_ASK}
## 台本ゲートの採点（書いたあと、別のAIがこの線で見る）
- 家事の合間に耳だけで聞く50〜60代の女性として10点満点。最初の30秒が7点以上、全部の章が5点以上で合格。
- 最初の30秒は、つかみの型（日付・場面・問い）で、いちばん驚く日付か由来を言い切る。各章の終わりの1文で、次の章で分かることを中身で引く。
- 画面を見ないと分からない言い方（「この表」「ここに書いてある」）はしない。日付は耳だけで分かる形で言う。
- 事実の点検：facts.json の暦の欄と sources に無い日付・数・由来を言い切っていないか。具体的な結果の保証と、病気・健康への効果を言っていないか。
"""
    if fix:
        g = json.load(open(os.path.join(work, "gate_script.json"), encoding="utf-8"))
        bad = {k: v for k, v in g.items() if isinstance(v, dict) and v.get("合格") is False}
        p += f"""
## 今回は書き直し
台本ゲート（別のAIの点検）で、次の項目が不合格でした。不合格の所だけを直し、ほかは変えないでください。
点検の「直すなら」は案です。手順書の決まりとぶつかる案は採らず、決まりの中で同じ狙いを達する直し方にしてください。
「出典なし」「暦と違う」と言われた時は、facts.json の暦の欄か sources にある値に直すか、その文を消してください（暦の欄は書き換えない）。
直したら check_spi_script.py をもう一度回し、NG 0件にしてから終えてください。
{json.dumps(bad, ensure_ascii=False, indent=1)}
"""
    return p


def finish(work):
    """決まった値を入れ、facts.json の暦の欄を作り直す（書き手が変えても、暦の固定ファイルの値に戻る）"""
    sp, fp = os.path.join(work, "script.json"), os.path.join(work, "facts.json")
    neta = json.load(open(os.path.join(work, "neta.json"), encoding="utf-8"))
    prof = json.load(open(os.path.join(CH_DIR, "profile.json"), encoding="utf-8"))
    s = json.load(open(sp, encoding="utf-8"))
    b, vv = prof.get("build") or {}, prof.get("voicevox") or {}
    s.update({"format": "long", "channel": "spi", "card_theme": "koyomi", "style": STYLE, "avoid": AVOID,
              "tempo": b.get("tempo", 1.25), "gap": b.get("gap", 0.25)})
    for k in ("type", "frame", "pub_date", "window", "target_month", "hook_type", "line_copy", "sub_copy"):
        if neta.get(k) is not None:
            s[k] = neta[k]
    s.setdefault("card_data", {})
    s.setdefault("thumb_bg", "THUMB")
    if s.get("titles"):
        s["title"] = s["titles"][0]
    voice = {"engine": "voicevox", "narrator": vv.get("narrator", {"name": "玄野武宏", "style": "ノーマル"}),
             "credit": vv.get("credit", "音声：VOICEVOX:玄野武宏")}
    if any(c.get("speaker") == "listener" for c in s.get("cuts", [])) and vv.get("listener"):
        voice["listener"] = vv["listener"]
        voice["credit"] += f"、VOICEVOX:{vv['listener']['name']}"
    s["voice"] = voice
    for c in s.get("cuts", []):
        if c.get("narration"):
            c.setdefault("speaker", "narrator")
    json.dump(s, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    f = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else {}
    if f.get("koyomi") != json.loads(json.dumps(KS.facts(neta), ensure_ascii=False)):
        print("【メモ】facts.json の暦の欄が作り直した値と違ったので、暦の固定ファイルの値に戻しました")
    f["koyomi"] = KS.facts(neta)
    f.setdefault("sources", {})
    f.setdefault("quotes", [])
    json.dump(f, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default="spi")
    a.add_argument("--fix", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    if not os.path.exists(os.path.join(work, "neta.json")):
        sys.exit("【止まりました】neta.json がありません（pick_neta_spi.py で作業フォルダを作る）")
    tools = ["Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch",
             "Bash(python -X utf8 pipeline/check_spi_script.py:*)", "Bash(python -X utf8 pipeline/koyomi_spi.py:*)"]
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV + ("YT_TOKEN_PSY", "YT_TOKEN")}
    env["YT_SECRETS_DIR"] = os.path.join(ROOT, "_no_secrets_here")  # 書く作業から鍵の場所を見えなくする
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_WRITER_MODEL", "opus"),
           "--allowedTools", *tools, "--permission-mode", "acceptEdits", "--output-format", "json"]
    if os.path.isdir(DOCS):  # 手元だけ（クラウドには OneDrive が無いので、repo の channels/spi/手順書.md を読む）
        cmd += ["--add-dir", DOCS]
    r = subprocess.run(cmd, cwd=ROOT, env=env, input=prompt(work, a.ch, a.fix), capture_output=True, text=True, encoding="utf-8", timeout=5400)
    open(os.path.join(work, "_write.log"), "a", encoding="utf-8").write(r.stdout + "\n" + r.stderr + "\n")
    out = {}
    try:
        out = json.loads(r.stdout)
        print(out.get("result", "")[-1500:])
        print(f"（Claude：{out.get('num_turns')}手・{out.get('duration_ms', 0) / 60000:.1f}分）")
    except json.JSONDecodeError:
        print(r.stdout[-1500:], r.stderr[-800:])
    sp = os.path.join(work, "script.json")
    if r.returncode != 0 or not os.path.exists(sp):
        sys.exit("【止まりました】台本を書けませんでした（_write.log を見る）")
    finish(work)
    if not a.fix:
        levelup_add(a.ch, work, out.get("result", ""))
    chk = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "pipeline", "check_spi_script.py"), work],
                         capture_output=True, text=True, encoding="utf-8")
    print("\n".join(chk.stdout.strip().splitlines()[-8:]))
    sys.exit(0 if chk.returncode == 0 else 1)


if __name__ == "__main__":
    main()
