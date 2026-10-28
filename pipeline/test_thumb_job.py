# サムネの文字の照らし合わせの回帰テスト（006_a_sekokan が「？」と「?」の違いで3回止まった。2026-10-26）
#   python -X utf8 -m pytest pipeline\test_thumb_job.py
# ・thumb_lines と thumb_text は全角・半角をそろえて（NFKC）照らす。表記の違いだけなら通し、文言の違い・行の数の超過は止める
# ・320px の読み取り検査（check）は Gemini／Claude を呼ばず、読めた文字を差し替えて試す
# ・描画は手元のフォントで本当に描き、描いた文字がそろえた後の行と同じかを見る
import json
import sys
import types
import unicodedata
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_thumb_job as mt  # noqa: E402

N = lambda s: unicodedata.normalize("NFKC", s)
STOPPED = ["年収54万円差", "時間では？"]  # 実際に止まった並び（history/job/last_run.json 10/26 7:13・10:07）
TEXT = "年収54万円差時間では？"


# ── two_lines（サムネA・B） ──
def test_two_lines_fullwidth_question():
    lines, hi = mt.two_lines(N(TEXT), STOPPED)
    assert lines == ["年収54万円差", "時間では?"]
    assert hi == 0  # 数字のある行を大きく


def test_two_lines_fullwidth_digits_in_lines():
    lines, _ = mt.two_lines(N("年収54万円差時間では?"), ["年収５４万円差", "時間では?"])
    assert lines == ["年収54万円差", "時間では?"]


def test_two_lines_plain_japanese():
    lines, hi = mt.two_lines("介護の給料", ["介護の", "給料"])
    assert lines == ["介護の", "給料"] and hi == 1  # 数字が無ければ最後の行


def test_two_lines_single_line():
    assert mt.two_lines(N("年収54万円"), ["年収５４万円"])[0] == ["年収54万円"]


def test_two_lines_auto_split():
    assert mt.two_lines(N(TEXT))[0] == ["年収", "54万円差時間では?"]


def test_two_lines_different_words_stop():
    with pytest.raises(SystemExit):
        mt.two_lines(N(TEXT), ["年収45万円差", "時間では？"])


def test_two_lines_missing_char_stop():
    with pytest.raises(SystemExit):
        mt.two_lines(N(TEXT), ["年収54万円差", "時間では"])


def test_two_lines_too_many_lines_stop():
    with pytest.raises(SystemExit):
        mt.two_lines(N(TEXT), ["年収", "54万円差", "時間では？"])


# ── d_lines（サムネD。行の数の上限は無い） ──
def test_d_lines_fullwidth():
    lines, hi = mt.d_lines(N("給料３０年の謎？"), ["給料", "３０年", "の謎？"])
    assert lines == ["給料", "30年", "の謎?"] and hi == 1


def test_d_lines_different_words_stop():
    with pytest.raises(SystemExit):
        mt.d_lines(N("給料30年の謎"), ["給料", "20年", "の謎"])


# ── 描画まで（サムネA の A-1） ──
@pytest.fixture
def work_a(tmp_path):
    s = {"type": "A", "frame": "A-1", "thumb_text": TEXT, "thumb_lines": STOPPED}
    f = {"職業": "施工管理", "棒グラフ": {"棒": [{"物差し": "年収_万円", "施工管理": 600.0, "全産業の平均": 545.6}]}}
    (tmp_path / "script.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "facts.json").write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _drawn(monkeypatch):
    drawn = []
    orig = ImageDraw.ImageDraw.text
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", lambda self, xy, s, *a, **k: (drawn.append(s), orig(self, xy, s, *a, **k))[1])
    return drawn


def test_make_a_draws_normalized_lines(work_a, monkeypatch):
    drawn = _drawn(monkeypatch)
    out = mt.make(str(work_a), "a")
    assert Image.open(out).size == (1280, 720)
    assert Image.open(out.replace(".jpg", "_320.jpg")).size == (320, 180)
    assert "年収54万円差" in drawn and "時間では?" in drawn  # 照らした行と同じ文字を描く
    assert "時間では？" not in drawn


def test_make_a_different_words_stop(work_a):
    s = json.loads((work_a / "script.json").read_text(encoding="utf-8"))
    s["thumb_lines"] = ["年収45万円差", "時間では？"]
    (work_a / "script.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit):
        mt.make(str(work_a), "a")


def test_make_a_too_long_text_stop(work_a):
    s = json.loads((work_a / "script.json").read_text(encoding="utf-8"))
    s["thumb_text"], s["thumb_lines"] = "年収54万円差は時間では？", ["年収54万円差は", "時間では？"]  # 13字
    (work_a / "script.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit):
        mt.make(str(work_a), "a")


# ── 320px の読み取り検査（check） ──
def _check(monkeypatch, got, n=2, t=TEXT):
    fake = types.ModuleType("gemini")
    fake.ask = lambda *a, **k: (json.dumps({"読めた文字": got}, ensure_ascii=False), {})
    monkeypatch.setitem(sys.modules, "gemini", fake)
    return mt.check("w", [f"thumb_{v}.jpg" for v in "ab"[:n]], t)


@pytest.mark.parametrize("got", [
    ["年収54万円差時間では?", "年収54万円差時間では?"],      # 実際に読めた文字（10/26 15:12）
    ["年収54万円差時間では？", "年収５４万円差 時間では？"],  # 全角・空白入り
])
def test_check_notation_difference_passes(monkeypatch, got):
    assert _check(monkeypatch, got) is True


@pytest.mark.parametrize("got", [
    ["年収45万円差時間では?", "年収54万円差時間では?"],  # 1枚だけ数字が違う
    ["年収54万円差時間では", "年収54万円差時間では"],    # 字が欠けた
    ["年収5?万円差時間では?", "年収54万円差時間では?"],  # 読めない字（？）
])
def test_check_real_difference_stops(monkeypatch, got):
    assert _check(monkeypatch, got) is False


@pytest.mark.xfail(strict=True, reason="未修正：読めた文字が枚数より少ないと、zip と all で残りを照らさずに通る（2026-10-26 に見つけた。直すかは相談）")
def test_check_fewer_answers_than_images_stops(monkeypatch):
    assert _check(monkeypatch, []) is False
