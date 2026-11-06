# -*- coding: utf-8 -*-
"""直接运行入口：把 ``src`` 加入 ``sys.path`` 后启动应用（无需先安装）。

安装后也可以使用 ``ai-interpreter`` 命令或 ``python -m ai_interpreter``。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from ai_interpreter.app import main  # noqa: E402  (需先设置 sys.path)

if __name__ == "__main__":
    sys.exit(main())
