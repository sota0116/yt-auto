# 鍵が本当に使えるかの試し（準備手順書 B8 の3）：読むだけ・お金なし。keytest.yml から手で動かす
#   python -X utf8 pipeline\test_keys_cloud.py job [spi]
# ・出すのは「使える／だめ」と、だめな時の種類だけ。鍵の中身・URL（鍵入り）は出さない
# ・試すのは、毎日の制作が使う物だけ：YouTube のログイン・Claude・Lovart・e-Stat・VOICEVOX・動画スキル
#   Gemini（前払い残高0・今は使わない）・OpenAI・UTAGE（まだつながない）は試さない
import json, os, shutil, subprocess, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def youtube(ch):
    import yt_auth
    d = json.load(urllib.request.urlopen(urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
        headers={"Authorization": "Bearer " + yt_auth.access_token(ch)}), timeout=60))
    return d["items"][0]["snippet"]["title"]


def claude():
    r = subprocess.run([shutil.which("claude") or "claude", "-p", "--model", "haiku", "--output-format", "json"],
                       input="「OK」とだけ答えてください", capture_output=True, text=True, encoding="utf-8", timeout=300)
    d = json.loads(r.stdout)
    if d.get("is_error"):
        raise RuntimeError("Claude がエラーを返しました")
    return "返事あり"


def lovart():
    import importlib.util
    spec = importlib.util.spec_from_file_location("agent_skill", os.environ.get(
        "LOVART_SKILL", os.path.join(ROOT, "vendor", "lovart", "agent_skill.py")))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    s = m.AgentSkill(base_url="https://lgw.lovart.ai", access_key=os.environ["LOVART_ACCESS_KEY"],
                     secret_key=os.environ["LOVART_SECRET_KEY"], timeout=60)
    if not s.validate_project(os.environ.get("LOVART_PROJECT", "2o6natm73im8")):
        raise RuntimeError("プロジェクトが見つかりません")
    return "プロジェクトに入れる"


def estat():
    import estat as e
    d = e.call("getStatsList", searchWord="賃金構造基本統計調査", limit=1)
    return f"表 {d['GET_STATS_LIST']['DATALIST_INF']['NUMBER']}件"


def voicevox():
    url = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")
    return "版 " + urllib.request.urlopen(url + "/version", timeout=30).read().decode().strip('"')


def skill():
    p = os.path.join(ROOT, "vendor", "youtube-video-maker", "scripts", "build_long.py")
    if not os.path.exists(p):
        raise RuntimeError("動画スキルがありません（VENDOR_SKILL_B64）")
    return "ある"


def main():
    tests = [(f"YouTube（{ch}）", lambda ch=ch: youtube(ch)) for ch in sys.argv[1:] or ["job"]]
    tests += [("Claude", claude), ("Lovart", lovart), ("e-Stat", estat), ("VOICEVOX", voicevox), ("動画スキル", skill)]
    bad = 0
    for name, f in tests:
        try:
            print(f"{name}：使える（{f()}）", flush=True)
        except SystemExit as e:
            bad += 1; print(f"{name}：だめ（{e}）", flush=True)
        except Exception as e:  # 中身（鍵・URL）が出ないよう、種類だけ出す
            bad += 1; print(f"{name}：だめ（{type(e).__name__}）", flush=True)
    print("→ 全部使えます" if not bad else f"→ だめが {bad}個")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
