# -*- coding: utf-8 -*-
"""最小连通性探针：验证 DashScope 实时接口握手。

API Key 不再硬编码在源码里，改为从环境变量读取，避免密钥进入版本库：
    PowerShell:  $env:DASHSCOPE_API_KEY = "sk-ws-..."
"""
import os

import websocket

# 从环境变量读取，避免把密钥提交进版本库
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen3.8-livetranslate-flash-realtime"


def on_open(ws):
    print("握手成功")
    ws.close()


def on_error(ws, err):
    print(f"错误: {err}")


def main():
    print(f"Key前缀: {API_KEY[:10] if API_KEY else 'None（未设置 DASHSCOPE_API_KEY）'}")
    if not API_KEY:
        raise SystemExit("请先设置环境变量 DASHSCOPE_API_KEY，例如："
                         '$env:DASHSCOPE_API_KEY = "sk-ws-..."')
    ws = websocket.WebSocketApp(
        URL, header=[f"Authorization: Bearer {API_KEY}"],
        on_open=on_open, on_error=on_error)
    ws.run_forever()


if __name__ == "__main__":
    main()