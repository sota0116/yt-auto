# script.json を、人が読む用の Markdown にする（タイトル・サムネの文字・章・話し手・図のしるし・字数と見込みの長さ）
#   python -X utf8 pipeline\script_to_md.py <作業フォルダ> <出力.md>
import json, os, sys

CPS = 6.0


def main():
    work, out = sys.argv[1], sys.argv[2]
    s = json.load(open(os.path.join(work, "script.json"), encoding="utf-8"))
    name = {"narrator": "ミナト", "listener": s.get("listener_name", "ユイ")}
    chars = sum(len(c.get("narration", "")) for c in s["cuts"])
    L = [f"# 台本（{s.get('frame', '')}）", "",
         f"字数 {chars:,}字・{len(s['cuts'])}カット・見込み約{chars / CPS / 60:.1f}分（{CPS:g}字/秒で計算）", "", "タイトル3案"]
    L += [f"{i + 1}. {t}" for i, t in enumerate(s["titles"])]
    L += ["", "サムネの文字：" + "／".join(x for x in (s.get("thumb_top"), s.get("thumb_text"), s.get("thumb_band")) if x), ""]
    for c in s["cuts"]:
        if c.get("chapter"):
            L += ["", f"## {c['chapter']}", ""]
        mark = " 〔図〕" if c.get("chart") else (" 〔絵の使い回し〕" if c.get("same_as") else "")
        if c.get("quiz"):
            mark += " 〔クイズ・2秒の間〕"
        L.append(f"- {name.get(c.get('speaker', 'narrator'), 'ミナト')}：{c['narration']}{mark}")
    L += ["", "## 概要欄", "", s["desc"], ""]
    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(out)


if __name__ == "__main__":
    main()
