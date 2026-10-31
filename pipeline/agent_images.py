# 「Claude が1本作る」チャンネルの絵（agent.yml。run_daily.py の boost と images の段を1つにした物）
#   python -X utf8 pipeline/agent_images.py <作業フォルダ> [--par 4]
# ・クレジットの失効前（lovart_boost.expiring）は、その日の上限の分を速いモードで作り、残りを無料モードで作る。失効後は無料モードだけ
# ・終了コード：0＝全部できた／1＝まだ残りがある（もう一度動かすと続きを受け取る）
import argparse, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lovart_boost as lb

HERE = os.path.dirname(os.path.abspath(__file__))


def tool(work, *a, wait=None):
    env = {**os.environ, **({"LOVART_WAIT_MAX": str(wait)} if wait else {})}
    return subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "make_images_lovart.py"), work, *a], env=env).returncode


def main():
    a = argparse.ArgumentParser()
    a.add_argument("work")
    a.add_argument("--par", default="4")
    a = a.parse_args()
    ch = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(a.work))))
    s = json.load(open(os.path.join(a.work, "script.json"), encoding="utf-8"))
    missing = [c["id"] for c in s.get("cuts", []) if c.get("image") and not c.get("same_as") and not c.get("chart")
               and not os.path.exists(os.path.join(a.work, "images", c["id"] + ".png"))]
    if lb.expiring() and missing:
        n = int(lb.left_today(ch) // lb.unit("image"))
        if n >= 1:
            pick = missing[:n]
            print(f"速いモードで {len(pick)} 枚作ります（残り {len(missing)} 枚・今日の残り {lb.left_today(ch)} クレジット）", flush=True)
            with lb.fast_mode():
                tool(a.work, "--boost", "--only", ",".join(pick), "--par", a.par, wait=45 * 60)
    sys.exit(tool(a.work, "--par", a.par, wait=int(os.environ.get("LOVART_WAIT_MAX") or 90 * 60)))


if __name__ == "__main__":
    main()
