# Windows の winreg の代わり（クラウド用）。手元の道具が先頭で読み込むので置く。鍵は環境変数から取るので、ここは「無い」と答えるだけ
HKEY_CURRENT_USER = 0


def OpenKey(*a, **k):
    raise OSError("winreg はクラウドにありません")


def QueryValueEx(*a, **k):
    raise OSError("winreg はクラウドにありません")
