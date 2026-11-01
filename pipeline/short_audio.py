# 仕事チャンネルのショートの音（手順書 §12。2026-11-02）：声＋BGM＋効果音を1本の wav にする
# ・BGM は channels/job/assets/bgm の自作の曲（外部の音源ではない。出どころは bgm_sources.md）。声が鳴っている間は BGM を自動で下げる
# ・効果音は ffmpeg で計算して作る音（素材の権利もお金もかからない）。スマホのスピーカーで鳴る高さを主にする
#   hit：1カット目の頭／tick：時刻のカード、新しい棒／coin：年収のカード／peak：見どころ
# ・声の聞き取りを優先する。BGM は声より約9dB下に置き、声が鳴っている間はさらに下げる。最後の音量そろえは組み立て側の loudnorm が行う
# ・BGM のファイルが無い時も止めず、声と効果音だけで作る
import glob, hashlib, json, os
from common import run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BGM_DIR = os.path.join(ROOT, "channels", "job", "assets", "bgm")
BGM_GAIN = 0.45   # 曲は -16 LUFS。声（-16 LUFS）より約7dB下
DUCK = "threshold=0.06:ratio=2.5:attack=15:release=280"  # 声の間はさらに約6dB下げる。声との差は実測で約12dB（2026-11-02）
SFX_GAIN = 0.55
SFX = {"hit": ("0.7*sin(2*PI*(170+520*exp(-34*t))*t)*exp(-8*t)+0.3*random(0)*exp(-24*t)", 0.6),
       "tick": ("0.5*sin(2*PI*1480*t)*exp(-70*t)+0.3*random(0)*exp(-55*t)", 0.14),
       "coin": ("0.5*sin(2*PI*1319*t)*lt(t,0.07)+0.55*sin(2*PI*1760*t)*gte(t,0.07)*exp(-9*(t-0.07))", 0.5),
       "peak": ("0.45*sin(2*PI*523*t)*exp(-4*t)+0.35*sin(2*PI*784*t)*exp(-4*t)+0.4*sin(2*PI*130*t)*exp(-10*t)", 0.9)}


def pick_bgm(work, want=None):
    """回の名前で曲を決める（同じ回を作り直しても同じ曲）。want は名前の一部（1日の流れは夜の曲を外す等の絞り込み）"""
    files = sorted(glob.glob(os.path.join(BGM_DIR, "*.m4a")))
    if want:
        files = [f for f in files if any(w in os.path.basename(f) for w in want)] or files
    if not files:
        return None
    k = int(hashlib.sha256(os.path.basename(os.path.abspath(work)).encode()).hexdigest(), 16) % len(files)
    return files[k]


def mix(work, voice, t, hits, out, bgm):
    """voice＋bgm＋効果音 {種類: [秒]} を out に書く。返り値は使った曲の名前"""
    b = os.path.dirname(out)
    ins, fc, outs = ["-i", voice], "[0:a]aresample=48000,loudnorm=I=-16:LRA=9:TP=-2,aresample=48000,asplit=2[v1][v2];", ["[v1]"]
    if bgm:
        ins += ["-stream_loop", "-1", "-i", bgm]
        fc += (f"[1:a]atrim=0:{t:.3f},aresample=48000,aformat=channel_layouts=mono,volume={BGM_GAIN},afade=t=out:st={max(0, t - 0.6):.3f}:d=0.6[b0];"
               f"[b0][v2]sidechaincompress={DUCK}[bg];")
        outs.append("[bg]")
    else:
        fc += "[v2]anullsink;"
    k, sx = 1 + bool(bgm), []
    for kind, ts in hits.items():
        ts = [x for x in ts if x < t - 0.05]
        if not ts:
            continue
        expr, d = SFX[kind]
        p = os.path.join(b, f"sfx_{kind}.wav")
        run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d={d}", "-ac", "1", p)
        ins += ["-i", p]
        fc += f"[{k}:a]asplit={len(ts)}" + "".join(f"[{kind}{j}]" for j in range(len(ts))) + ";"
        for j, st in enumerate(ts):
            fc += f"[{kind}{j}]adelay={int(st * 1000)}:all=1[{kind}d{j}];"
            sx.append(f"[{kind}d{j}]")
        k += 1
    if sx:
        fc += "".join(sx) + (f"amix=inputs={len(sx)}:duration=longest:normalize=0,volume={SFX_GAIN}[sx];" if len(sx) > 1 else f"volume={SFX_GAIN}[sx];")
        outs.append("[sx]")
    fc += "".join(outs) + f"amix=inputs={len(outs)}:duration=first:normalize=0,alimiter=limit=0.92[a]"
    run("ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, "-map", "[a]", "-t", f"{t:.3f}", "-ar", "48000", "-ac", "1", out)
    return os.path.basename(bgm) if bgm else None


def note(work, sc, bgm_name):
    """使った曲と編集の版を script.json に残す（run_shorts.py が記録し、short_learn.py が前後を比べる）"""
    sc["編集の版"], sc["bgm"] = 2, bgm_name
    json.dump(sc, open(os.path.join(work, "script.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
