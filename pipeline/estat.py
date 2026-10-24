# e-Stat API の呼び出し（設計書 §4・編集方針の出典の決まり）
#   python -X utf8 pipeline\estat.py list "<検索語>" [--code 統計コード]   … 表を探す
#   python -X utf8 pipeline\estat.py meta <表ID>                           … 表の項目を見る
# ・キー（ESTAT_APP_ID）は keys.env から読む。画面・ファイル・エラー文に出さない
import json, os, sys
import requests

SEC = os.environ.get("YT_SECRETS_DIR", r"C:\yt-auto-secrets")
BASE = "https://api.e-stat.go.jp/rest/3.0/app/json/"
NOTE = "このサービスは、政府統計総合窓口(e-Stat)のAPI機能を使用していますが、サービスの内容は国によって保証されたものではありません。"


def _app_id():
    v = os.environ.get("ESTAT_APP_ID")
    if v:
        return v
    with open(os.path.join(SEC, "keys.env"), encoding="utf-8-sig") as f:
        for line in f:
            if line.startswith("ESTAT_APP_ID="):
                return line.split("=", 1)[1].strip()
    sys.exit("【止まりました】ESTAT_APP_ID が keys.env にありません。")


def call(endpoint, **params):
    params["appId"] = _app_id()
    try:
        r = requests.get(BASE + endpoint, params=params, timeout=120)
    except requests.RequestException as e:
        # エラー文に URL（キー入り）が出ないよう、種類だけ出す
        sys.exit(f"【止まりました】e-Stat につながりません（{type(e).__name__}）")
    if r.status_code != 200:
        sys.exit(f"【止まりました】e-Stat が {r.status_code} を返しました")
    return r.json()


def _list(word, code=None):
    p = {"searchWord": word, "limit": 100}
    if code:
        p["statsCode"] = code
    d = call("getStatsList", **p)
    res = d["GET_STATS_LIST"]["RESULT"]
    if res["STATUS"] not in (0, 1):
        sys.exit(f"【止まりました】{res['ERROR_MSG']}")
    tables = d["GET_STATS_LIST"].get("DATALIST_INF", {}).get("TABLE_INF", [])
    if isinstance(tables, dict):
        tables = [tables]
    for t in tables:
        title = t.get("TITLE")
        title = title.get("$", "") if isinstance(title, dict) else title
        print(t["@id"], "|", t.get("SURVEY_DATE"), "|", t.get("STATISTICS_NAME"), "|", title)


def _meta(sid):
    d = call("getMetaInfo", statsDataId=sid)
    cls = d["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    for c in cls:
        items = c["CLASS"] if isinstance(c["CLASS"], list) else [c["CLASS"]]
        print(f"[{c['@id']}] {c['@name']}（{len(items)}）")
        for it in items[:80]:
            print("   ", it["@code"], it["@name"], it.get("@unit", ""))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "list":
        code = sys.argv[sys.argv.index("--code") + 1] if "--code" in sys.argv else None
        _list(sys.argv[2], code)
    elif len(sys.argv) >= 3 and sys.argv[1] == "meta":
        _meta(sys.argv[2])
    else:
        print(__doc__ or "使い方は先頭のコメントを見てください")
