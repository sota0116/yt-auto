### 指名手配ボード（key shimei）
このチャンネルだけ、1回の制作で **横動画1本とショート2本** を作る。共通の「1本だけ」は横動画のこと。横動画の upload.json を先に置く。ショートが失敗しても横動画は止めない。

#### 置き場
- チャンネルのフォルダ：channels/shimei（以下 K）
- 作業フォルダ：K/videos。横動画は L<3桁の通し番号>_<題>（今ある番号の次）、ショートは S<3桁の通し番号>_<題>（今ある番号の次）
- _auto_run.md は横動画のフォルダに1つだけ置き、ショートの工程もそこへ書く。「## 完了」はショート2本の後で書く。ショートのフォルダには置かない
- 上げ終えた回は、動画・声・組み立ての途中物を消してある（script.json・config.json・thumb.json などは残っている）。新しい2本の横動画の images だけ残っている

#### 最初に全文読む
- 正本の看板：agent_shared/設計/チャンネル看板_指名手配ボード_v*.md のいちばん新しい版
- K/改善ログ.md・K/ネタ帳.md
- agent_shared/調査/research_thumb_title_import_2026-10-30.md と agent_shared/設計/輸入候補の組み込み先_v3_2026-10-30.md
- youtube-video-maker スキル（agent_shared/skill/SKILL.md、references の 03・04・07・14・15・16_見る人の指摘で直したこと）
- 手本：K/videos/L001_CIA少年 の script.json・config.json・thumb.json・thumb_bg_prompt.txt・upload.json、K/videos/S001_電話1本 の script.json・config.json・upload.json

#### ネタ
- 横動画：ネタ帳の横動画の表で、状態が「未」のいちばん上（看板 §2 の順番。保留は使わない）。
- ショート：看板 §4 の割合。今回の横動画の題材から作り直す物を1本、別の題材の単独（ネタ帳の S101〜）を1本。単独は作る前に日本語で1回検索し、結果をネタ帳に書く。山場は明かさない。
- 使ったらネタ帳の「状態」を書き換える。題・問い・1文目を過去の回と重ねない。

#### 出さない物（看板 §1。必ず守る）
- 生きている一般の人の実名と顔。未解決事件で犯人を決めつける回。政治の主張。未成年だった人は実名を出さず、名乗っていた呼び名で語る。
- 実在の企業や役所のロゴ・紋章、読める文字、国旗の細部、血（看板 §5）。

#### 横動画の作り方（この順）
1. 調べる：WebSearch・WebFetch で、裁判の記録・当時の報道・公的な発表を元に事実を確かめ、K/調査/<題材>_事実_<今日の日付>.md に書く（確認済み／二次／未確認の凡例・出どころのURL）。確かめられない所は「分かっていない」と語り、断定しない。元の動画は題材だけを借り、言い回し・章の組み立て・タイトルの角度は借りない（看板 §2）。
2. 台本：script.json。看板 §3・§3-2・§6 を守る。キーは L001 と同じ。"title_候補" に3案以上と選んだ理由を残す。説明文 desc に「VOICEVOX:雀松朱司」と AI を使っている1文を書く。話が言い切れた所で終える。15分は超えない。
   - 改善ログの「次に上げること」を必ず入れる。動く絵は最初から全部に "motion" 欄（動かす物1つ・出さない物）を書いて頼み、崩れた本数を数える。動きが必要な見どころは Kling に変化を頼まず、変化の前後の絵を2枚作って切り替える。
   - 点検：`python -X utf8 agent_shared/skill/scripts/check_script.py <作業フォルダ>` の NG 0。長さ・字数の NG だけなら理由を記録に書いて進めてよい。
3. 声：`python -X utf8 agent_shared/skill/scripts/make_voice.py <作業フォルダ> --engine voicevox`。config.json は L001 を写す（speaker 52）。そのあと `python -X utf8 K/道具/kana_list.py <作業フォルダ>` で全カットのカナを1文ずつ見て、`python -X utf8 pipeline/yomi_auto.py <作業フォルダ> --speaker 52` の食い違いを1語ずつ直す（看板 §3-2）。
4. 絵：`python -X utf8 pipeline/agent_images.py <作業フォルダ> --par 4`。絵柄は看板 §5 の白い空間のミニチュア。同じ人物は毎回同じ言葉で見た目を書く。作ったら数枚ずつの一覧で見て、読める文字・ロゴ・崩れをその場で直す。
5. 動く絵：章ごとに1つ以上＋山場。`bash pipeline/agent_motion.sh <作業フォルダ> <id,id>` をバックグラウンドで動かす（できた絵から順に頼み、上限で落ちたら3分待つ）。取れなかった物は止まった絵のままでよい。枠が付いた絵は agent_shared/tools/frame_crop.py で切る。
6. 組み立て：config.json を L001 から写す。K/素材/bgm/bgm_suspense1.wav を作業フォルダに写す（ショートも同じ）。`python -X utf8 agent_shared/skill/scripts/build_long.py <作業フォルダ>` をバックグラウンドで動かす。全カットの1コマを並べた一覧（check/ に置く）を目で見て、絵とセリフのずれ・切れた文字・偽の文字を直す。
7. 音量：`python -X utf8 agent_shared/tools/loudnorm2.py long.mp4 完成.mp4`。−14〜−16 LUFS に入れる。gate_video.py はこのチャンネルでは使わない。6 の一覧と LUFS・3秒以上の無音が無いことの確認で代える（ffmpeg の silencedetect=n=-45dB:d=3）。
8. サムネ：看板 §7。背景は `python -X utf8 K/道具/lovart_one.py <出力.png> <頼む文.txt>`（手本 L001 の thumb_bg_prompt.txt）。この道具は Lovart が無料モードの時だけ動くので、速いモードで止まったら数分おいて動かし直す。thumb.json は L001 の形。`python -X utf8 agent_shared/skill/scripts/make_thumb.py <作業フォルダ>`。点検 NG 0、thumb_small.jpg が1秒で読めるか見る。タイトルにある言葉は使わない。
9. 上げる準備：`python -X utf8 pipeline/agent_run.py title shimei "題"` が OK なら、upload.json を `{"video": "完成.mp4", "format": "long", "thumb": "thumb.jpg"}` で置く。この実行の後の段が upload_shimei.py で上げ、次の空き枠に入れる（横動画は 2日おきの 20:00）。

#### ショート2本の作り方
- 看板 §4：250〜330字・30〜45秒。1カット目は画面いっぱいの結論。問いと答えをショートの中で言い切る。切り出しは作らない。最後は「あなたなら〜？」とコメントへの問い。
- 手本 S001 と同じ script.json の形。テロップは "subs_bottom": true・"highlight"・"stamp"（1本に3つまで）。人物の頭が上の帯（縦270〜587）にかからない構図で絵を頼む。
- 絵：`python -X utf8 K/道具/make_images_short.py <作業フォルダ> --par 4`（縦の絵はこの道具。読む欄は image_en）。動く絵は1カット目と見どころの2つ。
- 組み立て：`python -X utf8 K/道具/build_short_shimei.py <作業フォルダ>` → loudnorm2.py で 完成.mp4 → safezone_check.png と全カットの一覧を目で見る。check_script.py <作業フォルダ> --short の NG 0。
- 上げる準備：upload.json を `{"video": "完成.mp4", "format": "short"}` で置く。この実行の後の段が1本ずつ上げ、次の空き枠（毎日 12:00・19:00）に入れる。

#### 詰まった時
- 横動画は、次の枠に間に合わなくても品質の線を下げない。次の空いた枠に入る。
- 絵や動く絵が1回の実行で終わらなければ、_auto_run.md に残りを書いて終える（次の実行が続ける）。「## 中止」は、事実が確かめられず話が成り立たない時だけにする。
- 横動画の upload.json まで済んで、ショートの工程で進めなくなったら、_auto_run.md に理由を書いて「## 完了」とする。
