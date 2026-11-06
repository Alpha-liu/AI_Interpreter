# -*- coding: utf-8 -*-
"""
硬件链路测试脚本（独立于 UI）：
1. 音频采集峰值
2. WebSocket 会话配置是否被接受
3. VAD 是否触发
4. 原文/译文事件是否到达，completed 字段名
"""
import json
import base64
import threading
import time
from collections import deque

import websocket

from ai_interpreter.config import API_KEY, WS_URL
from ai_interpreter.audio.utils import pcm_peak

# ============ 测试配置 ============
TARGET_LANG = "zh"
DURATION = 20
CHANNEL = "test"

# ============ 统计 ============
stats = {
    "audio_packets_sent": 0,
    "speech_started": 0,
    "speech_stopped": 0,
    "source_delta": 0,
    "source_completed": 0,
    "target_delta": 0,
    "target_done": 0,
    "peak_max": 0,
}

stats_ready = threading.Event()


# ============ WebSocket 回调 ============
def on_open(ws):
    print(f"[{CHANNEL}] WebSocket 已连接")


def on_message(ws, message):
    evt = json.loads(message)
    t = evt.get("type", "")

    if t == "error":
        print(f"[{CHANNEL}] 服务端错误: {json.dumps(evt, ensure_ascii=False)}")
        return

    if t == "session.created":
        update = {
            "type": "session.update",
            "session": {
                "output_modalities": ["text"],
                "translation": {"language": TARGET_LANG},
                "audio": {"input": {
                    "input_audio_transcription": {
                        "model": "qwen3-asr-flash-realtime"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.0,
                        "silence_duration_ms": 1000,
                    },
                }},
            },
        }
        ws.send(json.dumps(update))
        print(f"[{CHANNEL}] 已发送 session.update, target={TARGET_LANG}")
        return

    if t == "session.updated":
        print(f"[{CHANNEL}] session.updated 确认，开始发送音频")
        stats_ready.set()
        return

    if t == "input_audio_buffer.speech_started":
        stats["speech_started"] += 1
        print(f"[{CHANNEL}] >>> VAD: speech_started (第 {stats['speech_started']} 次)")
        return

    if t == "input_audio_buffer.speech_stopped":
        stats["speech_stopped"] += 1
        print(f"[{CHANNEL}] <<< VAD: speech_stopped (第 {stats['speech_stopped']} 次)")
        return

    if t == "conversation.item.input_audio_transcription.delta":
        stats["source_delta"] += 1
        delta = evt.get("delta", "")
        if stats["source_delta"] % 5 == 1:
            print(f"[{CHANNEL}] 原文 delta: {delta[:50]}")
        return

    if t == "conversation.item.input_audio_transcription.completed":
        stats["source_completed"] += 1
        print(f"[{CHANNEL}] 原文 completed 完整事件:")
        print(f"  {json.dumps(evt, ensure_ascii=False)[:500]}")
        for key in ("transcript", "text", "content"):
            if key in evt:
                print(f"  >>> 字段 '{key}' 存在，值: {evt[key]}")
        return

    if t == "response.text.delta":
        stats["target_delta"] += 1
        delta = evt.get("delta", "")
        if stats["target_delta"] % 5 == 1:
            print(f"[{CHANNEL}] 译文 delta: {delta[:50]}")
        return

    if t == "response.text.done":
        stats["target_done"] += 1
        print(f"[{CHANNEL}] 译文 done 完整事件:")
        print(f"  {json.dumps(evt, ensure_ascii=False)[:500]}")
        return

    if t == "response.done":
        resp = evt.get("response", {}) or {}
        for out in resp.get("output", []) or []:
            for c in out.get("content", []) or []:
                text = c.get("transcript") or c.get("text")
                if text:
                    print(f"[{CHANNEL}] response.done 兜底译文: {text[:60]}")
                    break
        return

    if t not in ("response.created", "conversation.item.created",
                 "response.output_item.added", "response.output_item.done",
                 "response.content_part.added", "response.content_part.done"):
        print(f"[{CHANNEL}] 收到事件: {t}")


def on_error(ws, error):
    print(f"[{CHANNEL}] WebSocket 错误: {error}")


def on_close(ws, code, msg):
    print(f"[{CHANNEL}] WebSocket 关闭")


# ============ 公共发送循环 ============
def _run_common(factory):
    stats_ready.clear()
    headers = [f"Authorization: Bearer {API_KEY}"]
    ws = websocket.WebSocketApp(
        WS_URL, header=headers,
        on_open=on_open, on_message=on_message,
        on_error=on_error, on_close=on_close,
    )
    threading.Thread(target=ws.run_forever, daemon=True).start()

    print("等待会话就绪...")
    if not stats_ready.wait(timeout=10):
        print(">>> 会话 10 秒内未就绪，尝试继续发送（可能失败）")

    audio_queue = deque(maxlen=2000)

    def on_pcm(pcm):
        audio_queue.append(pcm)
        p = pcm_peak(pcm)
        if p > stats["peak_max"]:
            stats["peak_max"] = p

    capture = factory(on_pcm)
    capture.start()
    if getattr(capture, "stream", None) is None:
        print(">>> 采集器启动失败，请检查设备")
        return

    start_time = time.time()
    while time.time() - start_time < DURATION:
        if not ws.sock:
            break
        sent = 0
        while audio_queue and sent < 20:
            pcm = audio_queue.popleft()
            try:
                ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(pcm).decode("ascii"),
                }))
                stats["audio_packets_sent"] += 1
                sent += 1
            except Exception as e:
                print(f"发送失败: {e}")
                break
        if sent == 0:
            time.sleep(0.05)

    capture.stop()
    print("\n测试结束，统计:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"\n峰值最大值: {stats['peak_max']} (正常应 > 1000)")
    if stats["peak_max"] < 100:
        print(">>> 警告: 音频峰值极低，采集到的是静音！")


# ============ 环回测试 ============
def run_loopback_test():
    print("=" * 50)
    print("环回通道测试（参会者音频 → 翻译）")
    print("=" * 50)
    print("请确保会议软件/播放器正在向所选扬声器输出声音")
    print(f"测试时长: {DURATION} 秒\n")

    from ai_interpreter.audio.loopback import LoopbackCapture, list_loopback_devices

    devices = list_loopback_devices()
    print("可用环回设备:")
    for i, (idx, name) in enumerate(devices):
        print(f"  [{i}] {name} (index={idx})")

    if not devices:
        print("没有可用环回设备")
        return

    choice = input("\n选择设备编号（直接回车用第一个）: ").strip()
    try:
        loopback_index = devices[int(choice)][0] if choice else devices[0][0]
    except (ValueError, IndexError):
        loopback_index = devices[0][0]

    print(f"使用 index={loopback_index}")

    def factory(on_pcm):
        return LoopbackCapture(on_pcm=on_pcm, loopback_index=loopback_index)

    _run_common(factory)


# ============ 麦克风测试 ============
def run_mic_test():
    print("=" * 50)
    print("麦克风通道测试（我的语音 → 翻译）")
    print("=" * 50)
    print("请对着麦克风说话")
    print(f"测试时长: {DURATION} 秒\n")

    from ai_interpreter.audio.mic import MicCapture, list_input_devices

    devices = list_input_devices()
    print("可用输入设备:")
    for i, (idx, name) in enumerate(devices):
        print(f"  [{i}] {name} (index={idx})")

    if not devices:
        print("没有可用输入设备")
        return

    choice = input("\n选择设备编号（直接回车用第一个）: ").strip()
    try:
        mic_index = devices[int(choice)][0] if choice else devices[0][0]
    except (ValueError, IndexError):
        mic_index = devices[0][0]

    print(f"使用 index={mic_index}")

    def factory(on_pcm):
        return MicCapture(on_pcm=on_pcm, device_index=mic_index)

    _run_common(factory)


# ============ 入口 ============
if __name__ == "__main__":
    print("硬件链路测试")
    print("1. 环回通道（参会者音频）")
    print("2. 麦克风通道（我的语音）")
    choice = input("选择测试通道 (1/2): ").strip()

    if choice == "2":
        run_mic_test()
    else:
        run_loopback_test()

    print("\n完成。请根据上方日志判断:")
    print("- 峰值 < 100: 音频采集是静音，检查设备选择")
    print("- 峰值正常但无 speech_started: VAD 配置或音频格式问题")
    print("- speech_started 正常但 completed 字段不是 transcript: 检查服务协议")