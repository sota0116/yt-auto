"""Render the optional SPI HyperFrames cuts into the work directory."""
import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

VERSION = "0.9.19"
TEMPLATE = Path(__file__).resolve().parent / "hf" / "spi_3d_pilot"
TIMEOUT = 180


def render_html(source, cut, duration):
    card = cut.get("card") or {}
    narration = cut.get("narration") or ""
    title = cut.get("chapter") or cut.get("yt_chapter") or card.get("title") or card.get("text") or narration
    subtitle = card.get("kicker") or re.split(r"[。！？\n]", narration)[0]
    for key, value, limit in (("title", title, 20), ("sub", subtitle, 28)):
        content = " ".join(str(value).split())[:limit]
        source = re.sub(f'(?<=id="{key}-text">)[^<]*', lambda _: html.escape(content), source)
    ratio = duration / 8
    source = re.sub(r'data-(start|duration)="([0-9.]+)"',
                    lambda m: f'data-{m[1]}="{float(m[2]) * ratio:.6f}"', source)
    source = source.replace("DUR = 8;", f"DUR = {duration:.6f};")
    before, after = source.split("const tl = gsap.timeline", 1)
    animation, after = after.split("</script>", 1)
    animation = re.sub(r'(duration: |, |^        )([0-9.]+)(?=[,)\n])',
                       lambda m: f"{m[1]}{float(m[2]) * ratio:.6f}", animation, flags=re.M)
    return before + "const tl = gsap.timeline" + animation + "</script>" + after


def valid_video(path, duration):
    if not path.is_file():
        return False
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return abs(float(result.stdout.strip()) - duration) <= 0.1
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def make_clips(work, cuts, durations=None):
    selected = [c for c in cuts if c.get("narration") and c.get("hf_3d") is True
                and (c.get("chapter") or c.get("yt_chapter") or c.get("peak"))][:2]
    if not selected:
        return {}
    ready = {}
    env = dict(os.environ, HYPERFRAMES_NO_TELEMETRY="1", DO_NOT_TRACK="1",
               PRODUCER_BROWSER_GPU_MODE="software")
    cli = shutil.which("hyperframes")
    version_checked = False
    try:
        source = (TEMPLATE / "index.html").read_text(encoding="utf-8")
        dependencies = hashlib.sha256()
        inputs = [*TEMPLATE.glob("*"), *(TEMPLATE / "assets").rglob("*")]
        for path in sorted(p for p in inputs if p.is_file()):
            dependencies.update(path.relative_to(TEMPLATE).as_posix().encode())
            dependencies.update(path.read_bytes())
        dest = Path(work).resolve() / "images" / "_hf"
        dest.mkdir(parents=True, exist_ok=True)
        for cut in selected:
            cid = cut.get("id")
            if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", cid):
                print("警告: HyperFrames のカットIDが無効です", flush=True)
                continue
            try:
                duration = (durations or {}).get(cid, 8.0)
                if not math.isfinite(duration) or duration <= 0:
                    duration = 8.0
                page = render_html(source, cut, duration)
                key = hashlib.sha256(f"{VERSION}|software|{dependencies.hexdigest()}|{page}".encode()).hexdigest()
                output = dest / f"{cid}.mp4"
                stamp = dest / f"{cid}.sha256"
                if stamp.is_file() and stamp.read_bytes().strip() == key.encode("ascii") and valid_video(output, duration):
                    print(f"HyperFrames {cid}: キャッシュ", flush=True)
                else:
                    if not cli:
                        raise FileNotFoundError(f"hyperframes@{VERSION} が PATH にありません")
                    with tempfile.TemporaryDirectory(prefix="hf-", dir=dest) as temp:
                        project = Path(temp) / "project"
                        shutil.copytree(TEMPLATE, project, ignore=shutil.ignore_patterns("node_modules", ".git", "renders"))
                        (project / "index.html").write_text(page, encoding="utf-8")
                        if not version_checked:
                            version = subprocess.run([cli, "--version"], cwd=project, env=env,
                                                     capture_output=True, text=True, timeout=15, check=True).stdout
                            if not re.search(rf"(?<![\d.]){re.escape(VERSION)}(?![\d.])", version):
                                raise ValueError(f"hyperframes@{VERSION} が必要です")
                            version_checked = True
                        rendered = Path(temp) / "render.mp4"
                        result = subprocess.run(
                            [cli, "render", "--no-browser-gpu", "--output", str(rendered)],
                            cwd=project, env=env, capture_output=True, encoding="utf-8",
                            errors="replace", timeout=TIMEOUT,
                        )
                        if result.returncode:
                            raise RuntimeError((result.stderr or result.stdout).strip()[-500:])
                        if not valid_video(rendered, duration):
                            raise RuntimeError("書き出した動画の長さを確認できません")
                        new_stamp = Path(temp) / "render.sha256"
                        new_stamp.write_text(key, encoding="ascii")
                        stamp.unlink(missing_ok=True)
                        rendered.replace(output)
                        new_stamp.replace(stamp)
                    print(f"HyperFrames {cid}: {duration:.3f}秒を書き出しました", flush=True)
                ready[cid] = str(output)
            except Exception as exc:
                print(f"警告: HyperFrames {cid} をスキップ ({exc})", flush=True)
    except Exception as exc:
        print(f"警告: HyperFrames の準備をスキップ ({exc})", flush=True)
    return ready


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    script = json.loads((args.work / "script.json").read_text(encoding="utf-8"))
    make_clips(args.work, script["cuts"])


if __name__ == "__main__":
    main()
