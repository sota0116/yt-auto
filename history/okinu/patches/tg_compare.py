# 題の案を、点検プログラムと同じ相手（history_titles）・同じ線（title_guard 0.55）で比べて数字を出す（2026-11-24 S137。改善ログ「書く前に題の案3つの数字を出す」）
#   python -X utf8 history/okinu/patches/tg_compare.py 137 "案1" "案2" "案3"
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "pipeline"))
import title_guard
from check_okinu_script import history_titles

num = sys.argv[1]
others = history_titles(num)
for t in sys.argv[2:]:
    top = title_guard.similar(t, others)[:3]
    r = top[0][0] if top else 0.0
    print(f"{'NG' if r >= title_guard.LINE else 'OK'} {r:.2f} 「{t}」")
    for rr, o in top:
        print(f"    {rr:.2f} {o}")
