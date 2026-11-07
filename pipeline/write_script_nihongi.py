# ③台本（アナザー日本紀・2026-10-29 新設。千年こよみ write_script_spi.py と同じ形）：Claude（claude -p）に、手順書と見本から script.json を書かせる
#   python -X utf8 pipeline/write_script_nihongi.py <作業フォルダ> --ch nihongi [--fix]
# ・作業フォルダには neta.json（pick_neta_nihongi.py が置く。kind が short か long）が先にあること
# ・書く前に読ませる物：手順書（制作ルール v2.5。全部）・neta.json・見本（ショート S010／横動画 L002）・characters.json・禁止表現・改善ログ（2か所の最後の行）・
#   直近の回・競合メモ（あれば）・学び（あれば）・元のショートの台本（横動画の時）
# ・史実は書き手が WebSearch・WebFetch で調べて "facts" に出どころ付きで書く（手順書 §4）。ずらしたルールは "fiction": true・"world_rules"・"world_terms" に書く
# ・書く作業には鍵を渡さない（write_script.py と同じ。子のプロセスから鍵の場所と鍵の環境変数を消して動かす）
# ・書いたあと動画スキルの check_script.py（--short／--long）を自分で回し、NG が0件になるまで直す。最後にここでもう一度回して確かめる
# ・--fix：gate_script.json（台本ゲートの不合格）を読ませて、不合格の所だけ直させる（書き直しは2回まで。run_daily.py が数える）
# ・モデルは環境変数 CLAUDE_WRITER_MODEL（無ければ opus）
# ・決まった値（format・style・avoid・voicevox・characters_dir・tempo・voices・image・motion・shots の補い）は、書いたあとにプログラムが入れる（finish）
# ・2026-11-05：1カット目の1文目は『ずらしたルールと、史実の誰・何がひっくり返るか』（見て何が見られるか）。年・場所の場面は2文目から（gate の BENEFIT_GATE）
import argparse, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_script import DOCS, doc, levelup, levelup_add, LEVELUP_ASK, HOOK_ASK, IMAGE_ASK, THUMB_TEXT_ASK  # noqa: E402
from nihongi_common import (ROOT, CH, CDIR, HIST, VENDOR, jload, characters, kind_of_work, past_works, claude_env, vendor_ok,  # noqa: E402
                            SHORT_STYLE, LONG_STYLE, AVOID, AI_LINE, FIXED_END)

GOLDEN = {"short": os.path.join(CDIR, "golden", "script_short_S010.json"), "long": os.path.join(CDIR, "golden", "script_long_L002.json")}
LEVELUP_HAND = os.path.join(CDIR, "改善ログ.md")  # 手で作った回の分があれば（無ければ history/nihongi/改善ログ.md だけ）
rel = lambda p: os.path.relpath(p, ROOT).replace("\\", "/")


def extra_docs():
    out = []
    for p, what in ((os.path.join(HIST, "学び.md"), "学び（週報が書いた、うちの回の数字から。全部読む。手順書とぶつかる時は手順書が勝つ）"),
                    (os.path.join(HIST, "competitors", "競合メモ.md"), "競合メモ（毎日の競合リサーチ。型・構成・フック1行目だけを取り入れてよい。文・題は写さない）"),
                    (os.path.join(CDIR, "competitors.json"), "競合の一覧（看板・横動画上位。型の参考。写さない）"),
                    (LEVELUP_HAND, "改善ログ（手で作った回の分）"),
                    (levelup(CH), "改善ログ（毎日の制作の分。いちばん下の『次に上げること』をこの回に入れる）")):
        if os.path.exists(p):
            out.append((p, what))
    return out


def recent_text(kind):
    past = [x for x in past_works() if x["kind"] == kind][-9:]
    hist = os.path.join(HIST, "scripts")
    rows = []
    for x in past:
        s = jload(os.path.join(hist, f"{x['work']}.json"), None) or next(
            (jload(os.path.join(hist, f), {}) for f in sorted(os.listdir(hist)) if f.startswith(str(x["no"]) + "_")), {}) if os.path.isdir(hist) else {}
        c0 = ((s.get("cuts") or [{}])[0])
        rows.append({"番号": x["no"], "企画": x.get("企画"), "ずらし方": x.get("distort"), "時代": x.get("era"), "史実の主役": x.get("fact_main"),
                     "題": s.get("title"), "帯": s.get("banner"), "hook": s.get("hook") or c0.get("hook"), "1文目": c0.get("narration")})
    return json.dumps(rows, ensure_ascii=False, indent=1)


SHORT_FORM = f"""## script.json の形（ショート。見本は S010 の台本。新しく必須になった項目を足す）
一番上：format（"short"）・title（「もしも〜。〜 #もしも #日本史 #<時代>」の形）・promise（見た人が持ち帰れる物を1文）・desc・tags（7個前後）・banner・fiction（true）・world_rules・world_terms・voices・facts・cuts。
- banner：["アナザー日本紀", "<意外な結果 10字まで>"]（例「光秀だけ99%」）。大きい文字は固定。
- 題と帯（2026-11-04 競合の型から）：題の頭は誰でも知っている人物か出来事にし、知らない人物・用語だけを主役にしない。帯は題を写さず『誰に何が起きたか』の驚きを1つ。帯が「〜は」「〜の」で終わる言いさしにしない。
- 題の後ろ半分（2026-11-07 本人「わかりづらくなってる」）：「もしも〜。」のあとは、目に浮かぶ結果にする（「〜、町の半分が焼け残った」「〜、光秀だけ99%」の形）。「〜の本当の理由」「〜が見たもの」のような謎かけ・言いさしで終えない。歴史にくわしくない人が題だけで何が起きる動画か言えるかを確かめる。
- desc：1行目「あなたなら、どこで歴史を変える？ コメントで教えてください。」、空行のあと「※<ずらしたルール>は作り話です。<史実の事実>は史実をもとにしています。」、
  次の行「{AI_LINE}」。最後の「音声：VOICEVOX:…」の行は、声を作ったあとにプログラムが全員分で書くので書かなくてよい。
- facts：本当にあった出来事（年・人・場所）を1文ずつ、出どころ（URL か資料名）を付けて。説・逸話は「といわれる」と書く。作り話の行は最後に「〜は作り話」と1行。
- world_rules：誰に何が見えるか・誰が何を知っているか、を1行ずつ。world_terms：決まりに出る言葉の配列（check_script.py がその語のあるカットを全部出す）。
  語り手の文と人物の文を分け、その人が見られない・知らないことを話さないように、出た一覧を1つずつ照らす（手順書 §4）。
- voices：{{"<characters.json の id>": <voice の番号>}}（セリフを言う人物だけ。characters.json の voice を写す）。
- cuts：13カット前後。1カット＝絵1枚。id は n01, n02…。各カット：
  narration（1文27字まで）・image_en（絵を作るAIへの英語の場面。1〜2文。絵の中に文字を描かせない。人物が characters.json にいる時は chars に id を入れ、顔の描写は繰り返さない。
  いない人は、同じ人なら毎回同じ見た目の説明を image_en に書く）・shots（["n01","n01@close"] のように寄り @close／@face／@left／@right を足す。1〜2秒ごとに絵が変わるよう、長いカットは2つ以上）・chars（[] か id の配列）。
  1カット目だけ "hook"（1行5字・2行まで。何をずらしたか）。highlight（字幕で色を変える語の配列）。読みを直すカットだけ tts_text。
  "anim": "kling" を1カット目と見どころのカットに。見どころ1つに "peak": true（多くはオチか『1人だけ異常値』の場面。highlight か寄りを足す）。
  人物のセリフは、セリフだけのカットにして "voice": "<id>"（掛け合いは入れない）。
  実際の画像を1〜2カット：本当にあった物を見せるカット（古地図・屏風・浮世絵・古文書・城や寺の古写真）に "real": "<Wikimedia Commons を探す英語の語。例 Sekigahara folding screen／Edo 1844 map／Honnoji ukiyo-e>" を書く
  （WebSearch で見つけた画像の URL そのままでもよい）。image_en も書いておく（取れない時はその絵になる）。chars・anim・peak・voice・hook のカットには付けない。real_src はプログラムが書く。
- 字数 250〜330字（声にして30〜45秒）。名乗らない・『この動画では』などのメタ文を書かない・『答えは最後に』のような中身の無い引っ張りを書かない。
  1文目（hook の次の声）：「もしも＜ずらしたルール＞たら、＜史実の誰・何＞はどうなったか。」か結果の言い切りのように、ずらしたルールと、何がひっくり返るかを1文に入れる（例「もしも江戸で白いご飯が禁止されたら、江戸わずらいはどうなったか。」）。
  ルールだけで終わる1文目（「もしも江戸で、白いご飯が禁止されたら。」）は、何が見られるかが分からないので不合格になる。オチの中身（数字・正体）は伏せてよい。
  構成：1秒目 hook → 1文目 → 場面を3つ前後（どの場面にも本当にあった出来事を1つ）→ オチ（ずらしたルールのせいで史実が少しだけひっくり返る）→ 最後のカットは一字一句 「{FIXED_END}コメントで教えて。」
  わかりやすさ（2026-11-07 から。手順書 §3）：
  - 流れは1本道。作り話の世界を最後まで通し、本当にあった出来事は背景として同じ語り口で言う（「1657年、明暦の大火。」）。途中で「本当は」「実際の歴史では」「史実では」と現実に戻ってまた作り話へ、を繰り返さない。現実に戻るのは、オチのあとの「実際は〜」1文だけ（無くてもよい）。
  - オチは、絵を見れば分かる結果を1つ（誰が何をした・何が残った・何人が助かった）。和歌・辞世の句・遺言・史料の一文を知らないと分からないオチにしない（使うなら意味をその場で言い、それ無しでも結果が分かる形に）。オチを2つ3つ重ねない。
  - 固有名詞や数字の量は今までどおりでよい（減らさない）。
"""

LONG_FORM = f"""## script.json の形（横動画。見本は L002 の台本。ショートの企画を1本の話にした物）
一番上：format（"long"）・title（「【もしも歴史】<ずらしたルール>｜<意外な結果>」の形）・promise・desc・tags（10個前後）・thumb・fiction（true）・world_rules・world_terms・voices・facts・cuts。
- 元のショートと『ずらしたルール』は同じ。ショートで言えなかった史実を章ごとに足す。伏線の問いは問いだけを書く（先送りの文は書かない）。
- わかりやすさ（2026-11-07 から。手順書 §7）：作り話の世界を章をまたいで通し、本当にあった出来事は背景として同じ語り口で言う。「実際の歴史では〜」と現実に戻るのは章の終わりに1文まで（1章に1回まで）。章の中で行き来しない。各章の終わりは絵で分かる出来事1つで閉じる（史料や和歌を知らないと分からない閉じ方にしない）。
  題の「｜」のあと（意外な結果）は、目に浮かぶ結果にする。「〜の本当の理由」「〜が見たもの」のような謎かけ・言いさしにしない。
- 長さ：約3100字（声にして8〜15分）・95〜110カット・章は8〜10。章の頭のカットに "chapter": "章の名前"。場面の見出しは "label"（左の真ん中。大事な時は "strong": true で赤）。
- cuts の各カット：id（章ごとに A01, A02… B01…）・narration（1文40字まで）・image_en（横長の絵の英語の場面。人物は『真ん中より少し右』に置かせる：文末に "Place the main person slightly right of center."）・chars・label・
  "anim": "kling"（章ごとに1つ以上と見どころ。最初の2カットも）・"peak": true（1本に1つ以上）。同じ絵を使い回す時は "same_as": "<前のカットの id>"（全体の1割まで）。
  人物のセリフは "voice": "<id>" のセリフだけのカット。
- 実際の画像を8〜12カット（全体の1割ほど・章に1つ前後）：史実の証拠を見せるカット（古地図・屏風・浮世絵・古文書・城や寺の古写真・当時の道具）に
  "real": "<Wikimedia Commons を探す英語の語。例 Sekigahara folding screen／Edo 1844 map／Honnoji ukiyo-e>" を書く（WebSearch で見つけた画像の URL そのままでもよい）。
  AI の絵が続く中に本物を挟み、見た目の単調さを崩すためのもの。image_en も書いておく（取れない時はその絵になる）。chars・anim・peak・voice・same_as のカットには付けない。real_src はプログラムが書く。
- 途中（30〜70%）で「チャンネル登録」の呼びかけを1回、軽く（形は見本 L002 の D17 と同じ。『行く先が気になったら』のように物語の続きで登録を促さない）。最後は一字一句 「{FIXED_END}コメントで教えてください。」のあとに「それでは、また次の世界線で。」。
- 先頭の A01 は最初の1文から『ずらした結果』で引く。A01 の1文目は、ずらしたルールと意外な結果を1文で言う（例「信長に裏切る確率が見えたら、光秀だけ99%でした。」「明暦の大火の江戸に今の消防士が1人いたら、町の6割は焼けずに済んだのか。」）。
  年・場所から入る1文目は、何が見られる動画かが分からないので台本ゲートで不合格になる（2026-11-05 全チャンネル共通の決まり）。結果の中身は言い切っても、問いの形で伏せてもよい。サムネの背景にする見どころのカットの id を thumb.bg に書く。
- 最初の30秒は、その1文目のあと、見本 L002 の A01〜A05 の順にする：年・場所と目に見える出来事 → その出来事の重さ → ずらした物が場面に現れる → 足すルールを1文 → 作り話の範囲。
  ルールの説明は A04 の1文だけにし、それより前に設定の説明（『〜には心があった』など）を書かない（台本ゲートの『最初の30秒』で、設定の説明が先に来た回が3回とも6点で落ちた。2026-10-29）。
- 作り話の場面（ずらした物が史実の戦や出来事に居合わせた、など）を書いたら、desc の「※<作り話の部分>は作り話です」にもその場面を入れる（語り手が史実と同じ調子で言い切ると、史実の点検で落ちる）。
- thumb：{{"top": "ずらしたルール（例 信長に「裏切る確率」が見えたら。横幅の6割以上）", "big": "意外な結果（例 光秀だけ99%。1行で横幅いっぱい）", "hl_top": "上の段の中で黄にする語", "hl_big": "下の段の中で赤にする語", "bg": "<cut id>"}}。
  『AI』『PR』『ランキング』は入れない。数字が見える人・知っている人の食い違いを作らない（手順書 §4）。
- 題とサムネの競合の型（2026-11-04 本人「サムネとタイトルが意味わからないの多い」。競合の伸びた回から。上の題の形と thumb の決まりの中で使う）：
  - 題の頭は、誰でも知っている人物か出来事（信長・家康・本能寺・関ヶ原・ペリー来航など）。知らない人物・役職・用語だけを主役にしない（出す時は有名な人や出来事と一緒に）。
  - 題とサムネの役を分ける。題＝ずらしたルールと結果の筋。サムネ＝『誰に何が起きたか』の一番の驚き（数字・1人だけ・正体）を1つ。題の言葉をサムネに写さない。
  - 形の例（言葉は写さない）：top「信長に裏切る確率が見えたら」・big「光秀だけ99%」。top にずらしたルール（誰に・何が）、big に結果を短い1行で。
  - 史実の証拠を足すと強い（『記録にゼロ件』『宣教師だけが見た』のように、本当にある記録との食い違い）。言いさし（big が「〜は」「〜の」で終わって続きが無い）にしない。
  - 書いたら3つを確かめる：字だけで分かるか（歴史にくわしくない人が読んでも）／誰に何が起きたかが分かるか／題とサムネで役が分かれているか。
- desc：1行目にずらしたルールの説明（見た人が持ち帰れる物）、「あなたなら、どこで歴史を変える？ コメントで教えてください。」、「※<作り話の部分>は作り話です。<史実>は史実をもとにしています。」、
  「{AI_LINE}」。目次（chapters.txt）と『音声：VOICEVOX:…』の行は、アップの時にプログラムが足す。
"""


def prompt(work, fix):
    neta = jload(os.path.join(work, "neta.json"), {})
    kind = neta.get("kind", kind_of_work(work))
    ex = extra_docs()
    more = "".join(f"\n{i}. {rel(p)}（{what}）" for i, (p, what) in enumerate(ex, 8))
    src = ""
    if kind == "long":
        sp = os.path.join(ROOT, neta.get("short_script", ""))
        src = (f"\n- 元のショート（{neta.get('from_short')}）の台本：{rel(sp)}（ずらしたルール・人物・見どころを引き継ぐ。1文目・hook・帯の言葉は写さず、横動画としての1文目を作る）"
               if os.path.exists(sp) else f"\n- 元のショート（{neta.get('from_short')}）の台本ファイルは無い。題「{neta.get('from_short_title')}」からずらしたルールを読み取る")
    p = f"""あなたは YouTube チャンネル「アナザー日本紀【もしも歴史】」（江戸・戦国・幕末の史実に、ありえないルールを1つだけ足して、史実が少しだけひっくり返る様子を見せる）の台本の書き手です。
作業フォルダ {rel(work)} に script.json を書いてください（今回は{'ショート' if kind == 'short' else '横動画'}）。

## 先に全部読むファイル（部分読み禁止。手順書は最後の行まで）
1. {rel(doc(CH, '手順書.md'))}（制作ルール v2.5。このチャンネルの決まりの正本。§0〜§11 を全部読む。ショートは §2〜§6 と §10、横動画は §2〜§4・§5・§7・§10）
2. {rel(os.path.join(work, 'neta.json'))}（この回の企画・ずらし方・時代・『へえ』の主役の史実。ネタ選びが決めた値。書き換えない）
3. {rel(GOLDEN[kind])}（見本の台本。形・密度・1カットの長さ・image_en の書き方・決まった文の置き方を借りる。中身の場面・言い回しは写さない）
4. {rel(os.path.join(CDIR, 'characters', 'characters.json'))}（絵に出る人物と声。chars に書けるのはこの id だけ）
5. {rel(os.path.join(CDIR, '禁止表現.txt'))}（使わない言葉。台本ゲートでも照らす）
6. {rel(os.path.join(CDIR, 'yomi.json'))}（声の読みの表。読み違いやすい語は tts_text に読みを書く）
7. {rel(os.path.join(CDIR, 'profile.json'))}（チャンネルの設定）{more}{src}

## この回（neta.json の要点）
企画：{neta.get('企画')}／ずらし方：{neta.get('distort')}／時代：{neta.get('era')}／『へえ』の主役の史実：{neta.get('fact_main')}
メモ：{neta.get('note', '')}

## 直近の回（同じずらし方・同じ史実・同じ hook／帯／題を使わない材料）
{recent_text(kind)}

{SHORT_FORM if kind == 'short' else LONG_FORM}
## やること
1. 上のファイルを全部読む。改善ログは2つの『いちばん下の行』の日付を比べ、新しい方の『次に上げること』をこの回に入れる。
2. 『へえ』の主役の史実を WebSearch・WebFetch で確かめ、出どころ（一次資料や公的な解説を先に）を facts に書く。読めた範囲から外れることは書かない。説・逸話は『〜といわれる』『〜と伝わる』。
3. 手順書の決まりを全部守って script.json を書く。ずらすルールは1つだけ。置いた結果、史実の何が変わるかまで書く（道具を置くだけで終わらせない）。
4. 終わる前に必ず `python -X utf8 vendor/youtube-video-maker/scripts/check_script.py {rel(work)} --{kind}` を回し、NG が0件になるまで直す（注意は直せる物は直し、残す物は理由を考える）。
   出る『決まりと照らすカット』の一覧は1つずつ読み、その人が見られない・知らないことを言っていないか確かめる。
5. 最後に、語りの字数・カット数・使った史実の出どころ・ずらしたルールを1行ずつ書いて終える。

{HOOK_ASK}
{IMAGE_ASK}
{THUMB_TEXT_ASK}
{LEVELUP_ASK}
## 台本ゲートの採点（書いたあと、別のAIがこの線で見る）
- 雑学が好きで、見終わったあと『へえ』と言いたい人として10点満点。最初の30秒（ショートは最初の1文と hook）が7点以上、全部の場面・章が5点以上、見どころが6点以上で合格。
- 1カット目の1文目で、この動画で何が見られるか（ずらしたルールと、史実の誰・何がひっくり返るか）を言っていない回は、最初の30秒を6点以下にされ不合格になる。
- 事実の点検：年・人・場所・出来事が facts の出どころと合っているか。説・逸話を言い切っていないか。ずらした作り話と史実を概要欄で分けているか。world_rules と食い違う文が無いか。
- わかりやすさ（手順書 §3・§10 の6）：作り話と「本当は」を途中で行き来していないか／オチが前知識なしで絵で分かる結果1つか／題の後ろ半分が目に浮かぶ結果か。ここが崩れると場面・見どころの点が下がる。
- 電子ゴミの線（手順書 §10）：持ち帰れる『へえ』が無い場面・前の回と同じずらし方／史実／hook／帯／題・中身の無い引っ張りは出さない。
"""
    if fix:
        g = jload(os.path.join(work, "gate_script.json"), {})
        bad = {k: v for k, v in g.items() if isinstance(v, dict) and v.get("合格") is False}
        p += f"""
## 今回は書き直し
台本ゲート（別のAIの点検）で、次の項目が不合格でした。不合格の所だけを直し、ほかは変えないでください。
点検の『直すなら』は案です。手順書の決まりとぶつかる案は採らず、決まりの中で同じ狙いを達する直し方にしてください。
『出典なし』『史実と違う』と言われた時は、facts の出どころを調べ直して合う形に直すか、その文を消してください。
直したら check_script.py をもう一度回し、NG 0件にしてから終えてください。
{json.dumps(bad, ensure_ascii=False, indent=1)}
"""
    return p


def finish(work):
    """決まった値を入れ、書き手の書き漏れを補う（書き手が変えても、決まった値に戻る）"""
    sp = os.path.join(work, "script.json")
    neta = jload(os.path.join(work, "neta.json"), {})
    kind = neta.get("kind", kind_of_work(work))
    s = json.load(open(sp, encoding="utf-8"))
    chars, style_en = characters()
    pf = jload(os.path.join(CDIR, "profile.json"), {})
    b = pf.get("build") or {}
    s.update({"format": kind, "style": SHORT_STYLE if kind == "short" else LONG_STYLE, "avoid": AVOID, "bgm": None,
              "characters_dir": "../../characters", "tempo": b.get("tempo_short", 1.35) if kind == "short" else b.get("tempo_long", 1.15),
              "voicevox": {"speaker": 13, "name": "青山龍星（ノーマル）", "credit": "VOICEVOX:青山龍星"}})
    s["style_en"] = style_en
    s["fiction"] = True
    # 画風は characters.json の英語をそのまま使う（make_images_lovart.py は style_en があれば翻訳しない）
    voices = dict(s.get("voices") or {})
    for c in s.get("cuts", []):
        if c.get("voice") and c["voice"] in chars and chars[c["voice"]].get("voice") is not None:
            voices[c["voice"]] = chars[c["voice"]]["voice"]  # 声の番号は characters.json の値に戻す
    s["voices"] = {k: v for k, v in voices.items() if any(c.get("voice") == k for c in s.get("cuts", []))}
    last = None
    for c in s.get("cuts", []):
        c.setdefault("chars", [])
        if c.get("image_en") and not c.get("image"):
            c["image"] = c["image_en"]  # make_images_lovart.py は image のあるカットの絵を作る（英語の場面は翻訳を通さずそのまま使う）
        if c.get("anim") == "kling":
            c["motion"] = True  # make_motion_psy.py が読む印
        if kind == "short" and c.get("image_en") or kind == "short" and c.get("same_as"):
            if not c.get("shots"):
                base = c.get("same_as") or c["id"]
                c["shots"] = [c["id"], c["id"] + "@close"] if not c.get("same_as") else [base + "@close"]
        last = c
    if kind == "short":
        s["banner"] = ["アナザー日本紀"] + [x for x in (s.get("banner") or [])[1:2]]
    d = s.get("desc") or ""
    if "AIを使って作っています" not in d:
        d = d.rstrip() + "\n" + AI_LINE
    s["desc"] = d
    if s.get("titles"):
        s["title"] = s["titles"][0]
    try:  # 実際の画像（2026-11-04 本人の決定）。"real" のあるカットに古地図・屏風・浮世絵などを置き、そのカットは AI の絵を作らない。失敗しても回は止めない
        import real_images
        real_images.apply(work, s, CH, kind)
    except Exception as e:
        print(f"（実画像は入れずに進む：{type(e).__name__}: {e}）")
    json.dump(s, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--ch", default=CH)
    a.add_argument("--fix", action="store_true")
    a = a.parse_args()
    work = os.path.abspath(a.work)
    if not os.path.exists(os.path.join(work, "neta.json")):
        sys.exit("【止まりました】neta.json がありません（pick_neta_nihongi.py で作業フォルダを作る）")
    bad = vendor_ok()
    if bad:
        sys.exit(f"【止まりました】{bad}")
    kind = kind_of_work(work)
    tools = ["Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch", "Bash(python -X utf8 vendor/youtube-video-maker/scripts/check_script.py:*)"]
    cmd = [shutil.which("claude") or "claude", "-p", "--model", os.environ.get("CLAUDE_WRITER_MODEL", "opus"),
           "--allowedTools", *tools, "--permission-mode", "acceptEdits", "--output-format", "json"]
    if os.path.isdir(DOCS):  # 手元だけ（クラウドには OneDrive が無いので、repo の channels/nihongi/手順書.md を読む）
        cmd += ["--add-dir", DOCS]
    r = subprocess.run(cmd, cwd=ROOT, env=claude_env(), input=prompt(work, a.fix), capture_output=True, text=True, encoding="utf-8", timeout=5400)
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
    chk = subprocess.run([sys.executable, "-X", "utf8", os.path.join(VENDOR, "check_script.py"), work, f"--{kind}"],
                         capture_output=True, text=True, encoding="utf-8")
    print("\n".join(chk.stdout.strip().splitlines()[-8:]))
    sys.exit(0 if chk.returncode == 0 else 1)


if __name__ == "__main__":
    main()
