### かくれ神語り（key kakure）
このチャンネルだけ、1回の制作で **横動画1本とショート2本** を作る。共通の「1本だけ」は横動画のこと。ショートは毎日19:00・横動画は2日に1本なので、横1本につきショート2本で枠が埋まる。横動画の upload.json を先に置く。ショートが失敗しても横動画は止めない。

#### 置き場
- チャンネルのフォルダ：channels/kakure（以下 K）
- 作業フォルダ：K/videos。横動画は <3桁の通し番号>_<神や題>（今ある番号の次）、ショートは S<3桁の通し番号>_<種類>_<題>（例 S001_切出_えびす）
- 人物のポーズは K/videos/_chara_<番号>_<神>、サムネの絵は K/videos/_thumb_<番号>_<神>。どちらも upload.json を置かない
- _auto_run.md は横動画のフォルダに1つだけ置き、ショートの工程もそこへ書く。「## 完了」はショート2本の後で書く。ショートのフォルダには置かない
- 上げ終えた回は、動画・声・組み立ての途中物を消してある（script.json・config.json・thumb.json などは残っている）。新しい2本の横動画の images だけ残っている

#### 最初に全文読む
- 看板が正本：agent_shared/設計/チャンネル看板_かくれ神語り_v*.md のいちばん新しい版
- K/記録.md・K/改善ログ.md・K/ネタ帳_v*.md のいちばん新しい版
- agent_shared/調査/競合_神話_2026-10-29.md
- youtube-video-maker スキル（agent_shared/skill/SKILL.md、references の 03・04・07・14・15・16_見る人の指摘で直したこと）
- 手本：K/videos/001_ヒルコ の script.json・config.json・thumb.json・upload.json、K/videos/_chara_001_ヒルコ/script.json、K/videos/_thumb_001_ヒルコ/script.json、K/調査/ヒルコ_原典と説_2026-10-29.md
- ショートの手本：agent_shared/手本/okinu_S008/script.json（横の絵を縦に置き直した形）

#### ネタ
- 横動画：ネタ帳の横動画の表で、状態が「未」のいちばん上。前の回の次回予告と必ず一致させる。
- ショート：1本目は切り出し。2本目は、前回が図鑑なら格付け、前回が格付けか無しなら図鑑（ネタ帳の順）。
- 使ったらネタ帳の「状態」を書き換える。題・問い・1文目を過去の回と重ねない。

#### 横動画の作り方（この順）
1. 調べる：WebSearch・WebFetch で原典と説を調べ、K/調査/<神や題>_原典と説_<今日の日付>.md に書く。形はヒルコの調査メモと同じ（確認済み／二次／未確認の凡例・出どころのURL・先に知っておくべき点）。調べられなかった所は「未確認」と書き、台本では断定しない。
2. 台本：K/videos/<番号_題>/script.json。看板 §3・§4 を守る。キーは 001 と同じ（title・promise・playlist・format・desc・tags・style・avoid・era_en・voices・bgm・cuts）。"playlist" は型の名前（物語・謎・元ネタ）。説明文 desc には、使う声全部の「VOICEVOX:名前」と AI を使っている1文を書く。終わりの次回予告は、ネタ帳で次に来るネタを言う。
   - 目安の長さは10〜15分だが、話が言い切れた所で終える。15分は超えない。
   - 改善ログの「次に上げること」を必ず入れる。今の1つ目：画面の変化を平均2秒以下にする（check_script の数字で確かめる）。人物のポーズ差し替え・吹き出しを増やす。
   - 声：語りは 14（冥鳴ひまり）。神のセリフは別の声（台本の "voices"。No.7 は使わない）。同じ神は回をまたいで同じ声にする（001 は father 53・mother 16・hiruko 52）。新しい声を使う時は、その声の規約が商用可でクレジット表記だけで済むかを確かめ、確かめられなければ使わない。有料の声は使わない。
   - 点検：`python -X utf8 agent_shared/skill/scripts/check_script.py <作業フォルダ>` の NG 0。長さ・字数の NG と、看板 §3 で直さないと決めた伏線の注意は残ってよい（理由を記録に書く）。
3. 新しい神の絵：出てくる神が K/characters/characters.json に無ければ足す。上書きの前に characters_v<版>_<内容>_<日付>.json として前の版を残す。desc_en は看板どおり古墳時代の服で書く（世界の神話の回は、その土地の時代の服に合わせる）。
   - ポーズは _chara_<番号>_<神>/script.json に書く（手本 _chara_001_ヒルコ の文をそのまま使う。背景は真っ白・全身）。主役は6種、脇役は3種。すでに K/characters/cut にあるポーズは作らない。
   - 作る：`python -X utf8 pipeline/agent_images.py <ポーズの作業フォルダ> --par 4` → `python -X utf8 K/道具/make_chara.py <ポーズの作業フォルダ> K/characters/cut`。何人も並んだ絵は `--pick <id>=<番号>`。切り抜いた絵を一覧で見て確かめる。
4. 声：`python -X utf8 agent_shared/skill/scripts/make_voice.py <作業フォルダ> --engine voicevox --yomi K/yomi.json`。そのあと `python -X utf8 pipeline/yomi_auto.py <作業フォルダ> --speaker 14 --yomi K/yomi.json` の食い違いを1語ずつ見て直す（神の名は間違えやすい。全カットに効く物は K/yomi.json に1行足す）。
5. 絵：背景は45〜50枚ほど（同じ場所は "same_as" で使い回す）。`python -X utf8 pipeline/agent_images.py <作業フォルダ> --par 4`。途中で止まっても `images/_lovart.json` から続きを受け取れるので、同じコマンドをもう一度動かす。
6. 動く絵：章ごとに1つ以上＋見どころ（peak）。`bash pipeline/agent_motion.sh <作業フォルダ> <id,id>` をバックグラウンドで動かす（できた絵から順に頼み、上限で落ちたら3分待つ）。取れなかった物は止まった絵のままでよい。枠が付いた絵は agent_shared/tools/frame_crop.py で切る。
7. 組み立て：作業フォルダに写す物＝前回の横動画の config.json（K/config.json は古いので使わない）・K/素材/bgm/amacha3.wav を bgm_amacha3.wav という名前で・K/素材/sfx/ の wav を sfx/ に。`python -X utf8 agent_shared/skill/scripts/build_long.py <作業フォルダ>` をバックグラウンドで動かす。全カットの1コマを並べた一覧（check/ に置く）を目で見て、絵とセリフのずれ・切れた文字・偽の文字を直す。
8. 音量：`python -X utf8 agent_shared/tools/loudnorm2.py long.mp4 long_final.mp4`。測った LUFS を記録する。gate_video.py はこのチャンネルでは使わない。7 の一覧と LUFS・3秒以上の無音が無いことの確認で代える（無音は ffmpeg の silencedetect=n=-45dB:d=3）。
9. サムネ：_thumb_<番号>_<神>/script.json で T1・T2 を作り（手本どおり。上下の4分の1はあける）、良い方を thumb_bg.png にする。thumb.json（手本どおり size long・shade both・2段の字）を書き、`python -X utf8 agent_shared/skill/scripts/make_thumb.py <作業フォルダ>`。点検 NG 0 と thumb_small.jpg が1秒で読めるかを見る。タイトルと同じ言葉をくり返さない。
10. 上げる準備：`python -X utf8 pipeline/agent_run.py title kakure "題"` が OK なら、upload.json を `{"video": "long_final.mp4", "format": "long", "thumb": "thumb.jpg"}` で置く。この実行の後の段が upload_kakure.py で上げ、次の空き枠に入れる（横動画は2日おきの20:00）。

#### ショート2本の作り方
- 形：1080x1920・59.5秒以内・1本200〜280字ほど。問いと答えをショートの中で完結させ、ひっくり返る一言で終える（看板 §6）。切っただけのショートは出さない。
- 図鑑は看板の「図鑑の決まり」を守る。原典に無い性格・セリフを足さない。"playlist": "図鑑" を書き、題に番号を付ける。切り出し・格付けは "playlist" を書かない。
- 説明文 desc：VOICEVOX のクレジットと AI の1文、#shorts。元の横動画が公開済みなら「本編：URL」を入れる（URL は K/videos/<横の作業フォルダ>/uploaded.json）。
- 台本：format short。手本 S008 と同じく hook（1カット目。1行5字・2行まで）・subs・highlight と "subs_bottom": true、看板 §6 の "banner"、見た人の得を1文で書く "promise"。"peak" を1つ。最後はコメントの呼びかけ1文で終えてよい（ひっくり返る一言の後）。
- 絵：横の絵（16:9）を作り、`python -X utf8 agent_shared/tools/landscape_to_portrait.py <横の絵のフォルダ> <ショートの images> <id> ... --cx <id>=0.5` で縦に置き直す。切り出しは元の横動画の images を使い、新しく作らない。図鑑・格付けで足りない絵だけ agent_images.py で作る（1本5枚まで）。
- 動く絵：1カット目と見どころの2つ。その2カットに "anim": "kling" を書く（無いと check_script が NG で止まる）。agent_motion.sh はカットの id と同じ名前の絵を動かすので、動かすカットは id を絵の名前と同じにして "shots" を省き、"image" に場面の説明を書く。縦に置き直した後の絵を動かす。取れなければ止まった絵でよい（build_short の【NG】は理由を記録に書いて進める）。
- 作る：前回の config.json を写して "tempo_short": 1.2 を足す。bgm_amacha3.wav と sfx/ を写す。4 と同じ make_voice.py、yomi_auto.py の順。`python -X utf8 agent_shared/skill/scripts/check_script.py <作業フォルダ> --short` の NG 0。`python -X utf8 agent_shared/skill/scripts/build_short.py <作業フォルダ>` → loudnorm2.py で short_final.mp4 → safezone_check.png を目で見る。
- 上げる準備：upload.json を `{"video": "short_final.mp4", "format": "short"}` で置く。この実行の後の段が1本ずつ上げ、次の空き枠（毎日19:00）に入れる。

#### 詰まった時
- 横動画は、次の枠に間に合わなくても品質の線を下げない。次の空いた枠に入る。
- 絵や動く絵が1回の実行で終わらなければ、_auto_run.md に残りを書いて終える（次の実行が続ける）。「## 中止」は、事実が確かめられず話が成り立たない時だけにする。
- 横動画の upload.json まで済んで、ショートの工程で進めなくなったら、_auto_run.md に理由を書いて「## 完了」とする。横の枠の方が大事。
