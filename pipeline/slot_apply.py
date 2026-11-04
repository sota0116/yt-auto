# 週報の「枠の案」を、決まりに合う物だけ history/slot_plan.json に書く（2026-11-04 新設。weekly.py が Claude の後に呼ぶ）
#   本人「毎週アナリティクスの数字を取って分析して仮説を立てて修正してほしい」
#   python -X utf8 pipeline\slot_apply.py history\weekly\<日付>_枠の案.json [--dry]
# ・案の形：[{"ch": "psy", "key": "off", "to": ["12:10", "20:10"], "根拠": "...", "比べた本数": "..."}]（Claude が週報の 8 で書く）
# ・書いてよい条件（全部そろった時だけ。そろわない案は理由をつけて見送る）
#   1. key がショートの枠（on・off・extra_on・extra_off）。横の時刻と予告（late）は人が決める
#   2. 本数が今と同じ（増やす・減らすは人が決める）
#   3. 直した後の枠が day_slots.plan_problems で0件（3時間あける・2本なら昼夜・3本なら朝昼夜）
#   4. 外す時刻に、確定した縦の数字が3本以上ある（slot_stats.json。数字の無い枠を勘で動かさない）
#   5. 1チャンネルにつき1週1件まで、同じチャンネルを14日以内に直していない（結果を見てから次を動かす）
# ・書いた物は _log に残す。元に戻す時は slot_plan.json のそのチャンネルの行を消す
# ・すでに入っている予約は動かさない。効くのは次に予約する分から
import argparse, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import day_slots as ds

JST = ds.JST
MIN_ROWS = 3
COOLDOWN = 14


def load(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return d


def settled_at(ch, hm):
    st = load(os.path.join(ds.ROOT, "history", ch, "slot_stats.json"), {})
    return sum(1 for v in (st.get("videos") or {}).values() if v.get("確定") and v.get("数字") and not v.get("横") and v.get("時刻") == hm)


def check(p, ov, today, done):
    """案1件を確かめる。(書いてよいか, 理由)"""
    ch, key, to = p.get("ch"), p.get("key"), p.get("to")
    if ch not in ds.PLAN:
        return False, f"チャンネル名が違う（{ch}）"
    if key not in ds.AUTO_KEYS:
        return False, f"{key} は自動で直さない枠（横の時刻・予告は人が決める）"
    cur = ds.PLAN[ch].get(key)
    if cur is None:
        return False, f"{ch} に {key} の枠が無い（枠を増やすのは人が決める）"
    if isinstance(cur, list):
        if not isinstance(to, list) or len(to) != len(cur):
            return False, f"本数が変わる（いま {cur} → 案 {to}。本数は人が決める）"
        to = sorted(to)
    elif not isinstance(to, str):
        return False, f"形が違う（いま {cur} → 案 {to}）"
    if to == cur:
        return False, "いまと同じ"
    if ch in done:
        return False, "このチャンネルは今週もう1件直した"
    last = [x for x in (ov.get("_log") or []) if x.get("ch") == ch]
    if last and (today - datetime.date.fromisoformat(last[-1]["日付"])).days < COOLDOWN:
        return False, f"{last[-1]['日付']} に直したばかり（{COOLDOWN}日たってから。結果を見てから次を動かす）"
    probs = ds.plan_problems({**ds.PLAN[ch], key: to})
    if probs:
        return False, "決まりに合わない：" + "／".join(probs)
    gone = [t for t in (cur if isinstance(cur, list) else [cur]) if t not in (to if isinstance(to, list) else [to])]
    thin = [f"{t}（{settled_at(ch, t)}本）" for t in gone if settled_at(ch, t) < MIN_ROWS]
    if thin:
        return False, f"外す時刻の確定した数字が{MIN_ROWS}本に足りない：{'、'.join(thin)}"
    return True, f"{cur} → {to}"


def apply(path, dry=False):
    """書いた・見送った行（[文]）を返す"""
    props = load(path, None)
    if props is None:
        return ["枠の案はありませんでした（ファイルが無い）"]
    if not isinstance(props, list):
        return ["枠の案の形が違うので、何も直していません"]
    ovp = ds.OVERRIDE_PATH
    ov = load(ovp, {})
    today = datetime.datetime.now(JST).date()
    out, done = [], set()
    for p in props:
        if not isinstance(p, dict):
            continue
        ok, why = check(p, ov, today, done)
        ch, key = p.get("ch"), p.get("key")
        if not ok:
            out.append(f"見送り：{ch} {key} → {p.get('to')}（{why}）")
            continue
        to = sorted(p["to"]) if isinstance(p["to"], list) else p["to"]
        out.append(f"{'（--dry）' if dry else ''}直した：{ch} の {key} を {why}（根拠：{p.get('根拠', '')}）")
        done.add(ch)
        if dry:
            continue
        ov.setdefault(ch, {})[key] = to
        ov.setdefault("_log", []).append({"日付": today.isoformat(), "ch": ch, "key": key, "from": ds.PLAN[ch][key], "to": to,
                                          "根拠": p.get("根拠"), "比べた本数": p.get("比べた本数")})
        ds.PLAN[ch][key] = to  # 同じ実行の次の案の確かめに使う
    if done and not dry:
        tmp = ovp + ".tmp"
        json.dump(ov, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, ovp)
    return out or ["枠の案は0件でした（今週は動かさない）"]


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("path")
    a.add_argument("--dry", action="store_true")
    a = a.parse_args()
    for x in apply(a.path, a.dry):
        print(x)
