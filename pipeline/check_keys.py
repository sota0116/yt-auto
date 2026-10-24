# 鍵ファイルの「名前の行に値が入っているか」だけを数える（準備手順書 A5 の確かめ・B5 の前）
#   python -X utf8 pipeline\check_keys.py            … 前半（A5）の4つ
#   python -X utf8 pipeline\check_keys.py --all      … 後半（B5）の前。全部の名前
# ・値は画面に出さない。長さも出さない。出すのは「入っている／空」と、書き方の間違いだけ
# ・鍵の置き場は環境変数 YT_SECRETS_DIR（無ければ C:\yt-auto-secrets）
import argparse, os, sys

SEC = os.environ.get("YT_SECRETS_DIR", r"C:\yt-auto-secrets")
KEYS = os.path.join(SEC, "keys.env")
PART_A = ["GEMINI_API_KEY", "OPENAI_API_KEY", "ESTAT_APP_ID", "UTAGE_API_KEY"]
PART_B = ["CLAUDE_CODE_OAUTH_TOKEN", "HC_PING_DAILY_JOB", "HC_PING_DAILY_SPI", "HC_PING_WATCH"]
FILES_A = ["client_secret.json", "token_job.json", "token_spi.json"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true")
    a = p.parse_args()
    if not os.path.exists(KEYS):
        sys.exit(f"【止まりました】{KEYS} がありません。")
    filled, problems, seen = {}, [], set()
    with open(KEYS, encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            s = line.rstrip("\r\n")
            if not s.strip() or s.lstrip().startswith("#"):
                continue
            if "=" not in s:
                problems.append(f"{n}行目：「=」がありません")
                continue
            name, val = s.split("=", 1)
            if name != name.strip():
                problems.append(f"{n}行目：名前の前後に空白があります")
            name = name.strip()
            if name in seen:
                problems.append(f"{name}：同じ名前の行が2つあります")
            seen.add(name)
            if val != val.strip():
                problems.append(f"{name}：「=」の後ろか行の終わりに空白があります")
            if val.strip()[:1] in ('"', "'"):
                problems.append(f"{name}：値が「\"」で囲まれています。囲みを外してください")
            if name == "ANTHROPIC_API_KEY":
                problems.append("ANTHROPIC_API_KEY の行は書かないでください（準備手順書 B5）")
            filled[name] = bool(val.strip())
    want = PART_A + (PART_B if a.all else [])
    for k in want:
        print(f"{k}：{'入っている' if filled.get(k) else ('空' if k in filled else '行がない')}")
    if not a.all:
        for fn in FILES_A:
            print(f"{fn}：{'ある' if os.path.exists(os.path.join(SEC, fn)) else 'まだない'}")
    for pr in problems:
        print("【直す所】" + pr)
    ok = all(filled.get(k) for k in want) and not problems
    print("→ そろっています" if ok else "→ まだそろっていません")


if __name__ == "__main__":
    main()
