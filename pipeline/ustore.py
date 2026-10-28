# 上げた動画の記録（history\<ch>\uploaded.json）の読み書き（2026-10-29 アナザー日本紀を毎日の制作に入れた時に足した）
# ・ふつうのチャンネル（job・psy・spi）：history\<ch>\uploaded.json の1ファイル。load／save はそれと同じ動きをする（今までと変わらない）
# ・profile.json に "uploaded_files" があるチャンネル（nihongi）：記録が複数のファイルに分かれている。
#   手で上げた分は shorts_uploaded.json（ショート）と long_uploaded.json（横動画）に、毎日の制作が上げる分は uploaded.json に入る。
#   load は全部をつなげて返し（どの動画がどのファイルかを "_file" に持つ）、save は元のファイルへ分けて書き戻す（"_file" は書かない）。
#   "uploaded_files_ro" に書いたファイルは読むだけ（書き戻さない）。手元の道具（upload_nihongi.py など）と同じファイルを
#   クラウドの見張りが書き換えて commit がぶつかるのを避けるため。読み取り専用の分は、見張りが毎回 YouTube から状態を読み直すので困らない
# ・種類（ショートか横動画か）は kind_of(e) で見る：e["kind"]（毎日の制作が書く）→ e["format"]（手で上げた分）→ 作業フォルダの名前（S… はショート）
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _jload(p, default):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def files(ch):
    """(書き込める記録のファイル名の並び, 読むだけのファイル名の並び)。先頭が新しい記録の置き場"""
    pf = _jload(os.path.join(ROOT, "channels", ch, "profile.json"), {})
    rw = pf.get("uploaded_files") or ["uploaded.json"]
    return rw, pf.get("uploaded_files_ro") or []


def load(ch):
    rw, ro = files(ch)
    out = []
    for name in rw + ro:
        rows = _jload(os.path.join(ROOT, "history", ch, name), [])
        if len(rw) + len(ro) > 1:
            rows = [{**r, "_file": name} for r in rows if isinstance(r, dict)]
        out += rows
    return out


def save(ch, up):
    rw, ro = files(ch)
    d = os.path.join(ROOT, "history", ch)
    os.makedirs(d, exist_ok=True)
    if len(rw) + len(ro) == 1:
        _dump(os.path.join(d, rw[0]), up)
        return
    by = {name: [] for name in rw}
    for r in up:
        name = r.get("_file") or rw[0]
        if name in by:
            by[name].append({k: v for k, v in r.items() if k != "_file"})
    for name, rows in by.items():
        p = os.path.join(d, name)
        if rows or os.path.exists(p):
            _dump(p, rows)


def _dump(p, d):
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def kind_of(e):
    """"short" か "long"。分からない時は "long"（仕事・心理学・千年こよみは長尺が本体）"""
    k = e.get("kind") or e.get("format")
    if k in ("short", "long"):
        return k
    return "short" if re.match(r"S\d", e.get("work") or "") else "long"
