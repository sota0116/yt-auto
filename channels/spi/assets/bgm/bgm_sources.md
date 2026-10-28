# 千年こよみ BGM の出どころ（手順書 §6）

| ファイル | 出どころ | 作り方 | 使ってよい範囲 | 使った回 |
|---|---|---|---|---|
| koyomi_bgm_01_seed7.wav | 自作（外部の音源は使っていない） | `OneDrive\ClaudeBackup\tools\bgm\make_bgm.py --seed 7 --key A`（Python だけで音を合成。無料） | 制限なし（自作のため。クレジット不要） | 001 次の最強開運日は12月16日 |
| amacha/kamigaminoyadorubasho.mp3（神々の宿る場所） | 甘茶の音楽工房 https://amachamusic.chagasi.com/music_kamigaminoyadorubasho.html （2026-10-27 取得） | MP3 128kbps そのまま | 商用OK・クレジット任意。禁止：音楽だけの販売や配布／作曲者を偽る／JASRAC等への登録／**Content ID 登録**／YouTube のポリシー違反の動画。規約 https://amachamusic.chagasi.com/terms.html | 001 v3 |
| amacha/yukyunotokie.mp3（悠久の時へ） | 甘茶の音楽工房 https://amachamusic.chagasi.com/music_yukyunotokie.html （2026-10-27 取得） | 同上 | 同上 | 001 v3 |
| amacha/ouun.mp3（桜雲） | 甘茶の音楽工房 https://amachamusic.chagasi.com/music_ouun.html （2026-10-27 取得） | 同上 | 同上 | 001 v3 |
| koyomi_bgm_02_amacha3.wav | 上の甘茶3曲をつないだもの | 神々の宿る場所→悠久の時へ→桜雲（重ね3秒・ffmpeg acrossfade）。−2.2dB で −14.4 LUFS（01 と同じ大きさ。long_koyomi_v2.py の --bgm-volume 0.03 がそのまま使える）。7分02秒、組み立てでくり返す | 甘茶の規約どおり。概要欄に「BGM：甘茶の音楽工房」を入れる（任意だが入れる） | 001 v3 |

選んだ理由（2026-10-27）：本人の指摘「BGMの引き弱すぎ」。DOVA-SYNDROME（2026-09-15 から OpenTracks）は禁止事項2に「音源を政治・宗教その他のイデオロギーに関する制作物・コンテンツで使用すること」があり、神社と神の話をするこのチャンネルでは外した。甘茶の規約には宗教の禁止は無い。和風・アジアの24曲の中から8曲を測り、声の帯域（300〜3000Hz）の音が少なく、低音と打点がある3曲にした（声の帯域：悠久の時へ 53%・桜雲 58%・神々の宿る場所 63%。01 の自作は 71%）。
