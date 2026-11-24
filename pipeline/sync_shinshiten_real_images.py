"""shinshiten のカット別素材出典を履歴に追記する。"""
import argparse
import datetime
import json
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = re.compile(r"https?://[^\s<>）｜、）]+")


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def candidates(videos_dir):
    for script in sorted(videos_dir.glob("*/script.json")):
        court = read_json(script.with_name("court_src.json"), {})
        sources = script.with_name("sources.md")
        lines = sources.read_text(encoding="utf-8-sig").splitlines() if sources.is_file() else []
        for cut in read_json(script, {}).get("cuts", []):
            cid = cut["id"]
            src = cut.get("real_src")
            if isinstance(src, str):
                src = {"url": src}
            if not isinstance(src, dict):
                continue
            line = next((line for line in lines if re.match(
                rf"^\s*-\s+{re.escape(cid)}(?=[\s（(:：])", line) and URL.search(line)), "")
            ref = URL.search(line)
            url = src.get("url") or src.get("説明ページ") or (ref.group().rstrip(").") if ref else "")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                continue
            row = {"日": datetime.date.today().isoformat(), "回": script.parent.name,
                   "カット": cid, "種": "manual", **src, "url": url}
            for alias in re.findall(r"\bCS\d+\b", line):
                if alias in court:
                    row["法廷画"] = court[alias]
                    break
            yield row


def sync(videos_dir, history_path, dry_run=False):
    if not videos_dir.is_dir():
        raise FileNotFoundError(videos_dir)
    rows = read_json(history_path, [])
    def key(row):
        return row.get("回"), row.get("カット"), row.get("url")
    seen = {key(row) for row in rows}
    count = added = 0
    for row in candidates(videos_dir):
        count += 1
        identity = key(row)
        if identity not in seen:
            seen.add(identity)
            rows.append(row)
            added += 1
    if added and not dry_run:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=history_path.parent,
                                         delete=False) as output:
            temp = Path(output.name)
        try:
            temp.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            temp.replace(history_path)
        finally:
            temp.unlink(missing_ok=True)
    return count, added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos-dir", type=Path, default=ROOT / "channels/shinshiten/videos")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    count, added = sync(args.videos_dir, ROOT / "history/shinshiten/real_images.json", args.dry_run)
    print(f"読み取り {count}件 / {'追記予定' if args.dry_run else '追記'} {added}件")


if __name__ == "__main__":
    main()
