# 千年こよみ（spi）の動く図解カードを、カットごとの動画にする（2026-10-29 新設。OneDrive の motion_cards_v4.py をクラウドでも動く形に写した）
#   python -X utf8 pipeline/motion_cards_spi.py --jobs <jobs.json>
#   jobs.json：{"theme": "koyomi", "data": {...}, "items": [{"id", "spec", "dur", "out", "still"(任意)}]}
# ・ふだんは build_long_spi.py が呼ぶ（カードの中身・長さ・出す場所・作り直すかどうかは、そちらが決める）
# ・型は pipeline/motion_cards_spi.html（motion_cards_v8.html の写し。字の読み込みだけを、ここで Windows と Linux に合わせて差し込む）
# ・Chrome の場所：Windows の Chrome → /usr/bin/google-chrome（GitHub の ubuntu ランナーに入っている）→ Playwright の chromium
#   Playwright の chromium の時は H.264 の動画が読めないことがあるので、build_long_spi.py が動く絵を VP9（webm）に直してから渡す（uses_bundled()）
# ・1つのカードで落ちたら、ブラウザを立ち上げ直して2回までやり直す
# ・時間で決まる描き方なので、何度作っても同じ動画になる
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HTML = HERE / "motion_cards_spi.html"
FPS = 30
CHROMES = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
           "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/opt/google/chrome/chrome"]

WIN_FONTS = (("JSerif", "NotoSerifJP-VF.ttf", "200 900"), ("JSans", "NotoSansJP-VF.ttf", "100 900"))
# Linux（fonts-noto-cjk・fonts-noto-cjk-extra）：太さごとに入っている字体の名前で読む。無い太さは近い太さに落ちる
LINUX_FONTS = {"JSans": [("Noto Sans CJK JP Light", "100 300"), ("Noto Sans CJK JP", "400"), ("Noto Sans CJK JP Medium", "500 600"),
                         ("Noto Sans CJK JP Bold", "700 800"), ("Noto Sans CJK JP Black", "900")],
               "JSerif": [("Noto Serif CJK JP Light", "200 300"), ("Noto Serif CJK JP", "400"), ("Noto Serif CJK JP Medium", "500"),
                          ("Noto Serif CJK JP SemiBold", "600"), ("Noto Serif CJK JP Bold", "700 800"), ("Noto Serif CJK JP Black", "900")]}


def chrome():
    return next((p for p in CHROMES if os.path.exists(p)), None)


def uses_bundled():
    return chrome() is None


def font_css():
    win = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f) for _, f, _ in WIN_FONTS]
    if all(os.path.exists(p) for p in win):
        return "\n".join(f"@font-face{{font-family:{fam};src:url('{Path(p).as_uri()}');font-weight:{w}}}"
                         for (fam, _, w), p in zip(WIN_FONTS, win))
    out = []
    for fam, rows in LINUX_FONTS.items():
        names = [n for n, _ in rows]
        for n, w in rows:  # 太さの字体が無い時は、普通の太さ→太字の順に代わりを探す
            src = ",".join(f"local('{x}')" for x in [n] + [y for y in names if y != n])
            out.append(f"@font-face{{font-family:{fam};src:{src};font-weight:{w}}}")
    return "\n".join(out)


def page_file():
    """字の読み込みを差し込んだ型を、一時ファイルに書く（元の型は書き換えない）"""
    t = HTML.read_text(encoding="utf-8").replace("/*@FONTS@*/", font_css(), 1)
    fd, p = tempfile.mkstemp(prefix="motion_cards_spi_", suffix=".html", dir=str(HERE.parent / "_tmp") if (HERE.parent / "_tmp").is_dir() else None)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(t)
    return Path(p)


def render(items, theme, data):
    from playwright.sync_api import sync_playwright
    html = page_file()
    done, fail = [], []
    try:
        with sync_playwright() as p:
            def start():
                kw = {"args": ["--allow-file-access-from-files", "--force-color-profile=srgb", "--disable-gpu", "--autoplay-policy=no-user-gesture-required"]}
                if chrome():
                    kw["executable_path"] = chrome()
                b = p.chromium.launch(**kw)
                pg = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
                pg.set_default_timeout(120000)
                pg.goto(html.as_uri())
                return b, pg
            b, pg = start()
            for it in items:
                for tri in range(3):
                    try:
                        one(pg, it, theme, data)
                        done.append(it["id"])
                        break
                    except Exception as e:  # noqa: BLE001  ブラウザが止まった・動画が読めない など。立ち上げ直してやり直す
                        print(f"{it['id']} 失敗（{tri + 1}回目）：{str(e)[:200]}", flush=True)
                        try:
                            b.close()
                        except Exception:  # noqa: BLE001
                            pass
                        b, pg = start()
                else:
                    fail.append(it["id"])
            b.close()
    finally:
        html.unlink(missing_ok=True)
    return done, fail


def one(pg, it, theme, data):
    spec, dur, out = it["spec"], it["dur"], it["out"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pg.evaluate("([s,d,th,da]) => setup(s,d,th,da)", [spec, dur, theme, data])
    if it.get("still"):
        pg.evaluate(f"draw({dur * 0.85:.3f})")
        pg.screenshot(path=out)
        return
    tmp = out + ".part.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
                           "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    try:
        for f in range(int(dur * FPS) + 1):
            pg.evaluate(f"draw({f / FPS:.4f})")
            ff.stdin.write(pg.screenshot(type="jpeg", quality=93))
    finally:
        ff.stdin.close()
        rc = ff.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg が {rc} で終わりました")
    os.replace(tmp, out)
    print(it["id"], f"{dur:.1f}秒", flush=True)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--jobs", required=True)
    a = a.parse_args()
    j = json.load(open(a.jobs, encoding="utf-8"))
    done, fail = render(j["items"], j.get("theme", "koyomi"), j.get("data", {}))
    print(f"カード {len(done)} 本できました" + (f"／できなかった {fail}" if fail else ""), flush=True)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
