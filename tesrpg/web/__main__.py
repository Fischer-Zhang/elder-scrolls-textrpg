"""python3 -m tesrpg.web [port] —— 啟動本機 Web 版。"""

import sys

from .server import launch

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    no_browser = "--no-browser" in sys.argv
    launch(port=port, open_browser=not no_browser)
