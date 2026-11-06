# -*- coding: utf-8 -*-
"""音频工具：PCM 重采样、峰值计算、WAV 混音。

对外接口：
    resample_pcm(pcm_bytes, src_rate, dst_rate, channels) -> bytes
    pcm_peak(pcm_bytes) -> int
    pcm_rms(pcm_bytes)  -> int
    mix_wav_files(file1, file2, out_file) -> bool
"""

import os
import wave

import numpy as np


# ============================================================
# PCM 基础处理
# ============================================================
def resample_pcm(pcm_bytes: bytes, src_rate: int, dst_rate: int,
                 channels: int = 1) -> bytes:
    """把 16-bit PCM 从 src_rate 重采样到 dst_rate，并混成单声道。

    - channels > 1 时先多声道平均为单声道
    - src_rate == dst_rate 且 channels == 1 时原样返回（零开销快路径）
    - 使用线性插值，语音/ASR 场景足够；若需要更高质量可换
      scipy.signal.resample_poly（会引入 scipy 依赖，体积大幅增加）
    """
    if not pcm_bytes:
        return b""

    # 通道数为 0 或负数时视为单声道，避免除零
    if channels is None or channels <= 0:
        channels = 1

    # 快路径：已是目标格式
    if src_rate == dst_rate and channels == 1:
        return pcm_bytes

    arr = np.frombuffer(pcm_bytes, dtype=np.int16)
    if arr.size == 0:
        return b""

    # 多声道 -> 单声道
    if channels > 1:
        usable = (arr.size // channels) * channels
        if usable == 0:
            return b""
        arr = arr[:usable].reshape(-1, channels)
        # 用 int32 中间量防止求和溢出
        arr = arr.astype(np.int32).mean(axis=1)
        arr = np.clip(arr, -32768, 32767).astype(np.int16)

    if src_rate == dst_rate:
        return arr.tobytes()

    src_len = arr.size
    dst_len = int(round(src_len * float(dst_rate) / float(src_rate)))
    if dst_len <= 0:
        return b""

    # 线性插值重采样
    x_src = np.linspace(0.0, 1.0, src_len, endpoint=False)
    x_dst = np.linspace(0.0, 1.0, dst_len, endpoint=False)
    resampled = np.interp(x_dst, x_src, arr.astype(np.float32))
    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
    return resampled.tobytes()


def pcm_peak(pcm_bytes: bytes) -> int:
    """返回 16-bit PCM 的绝对峰值（0–32768）。空数据返回 0。"""
    if not pcm_bytes:
        return 0
    arr = np.frombuffer(pcm_bytes, dtype=np.int16)
    if arr.size == 0:
        return 0
    # 先转 int32，避免 -32768 取 abs 溢出
    return int(np.max(np.abs(arr.astype(np.int32))))


def pcm_rms(pcm_bytes: bytes) -> int:
    """返回 16-bit PCM 的 RMS 电平（0–32768）。空数据返回 0。"""
    if not pcm_bytes:
        return 0
    arr = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    if arr.size == 0:
        return 0
    return int(np.sqrt(np.mean(arr * arr)))


# ============================================================
# WAV 混音
# ============================================================
# 混音时每次读写的帧数：限制峰值内存，长会议（数小时）也不会整段载入。
_MIX_BLOCK_FRAMES = 16384


def mix_wav_files(file1: str, file2: str, out_file: str) -> bool:
    """将两个参数相同的 WAV 文件逐样本叠加（混音）。

    参数必须一致：nchannels / sampwidth / framerate。
    以较短一路的长度为准截断后混音，避免越界。
    采用分块流式读取/写入，峰值内存与文件时长无关（不再整段 load 进内存）。
    """
    if not os.path.exists(file1) or not os.path.exists(file2):
        print(f"[audio_utils] 混音失败：源文件不存在 {file1} 或 {file2}")
        return False

    try:
        with wave.open(file1, "rb") as w1, wave.open(file2, "rb") as w2:
            p1 = w1.getparams()
            p2 = w2.getparams()

            if (p1.nchannels != p2.nchannels
                    or p1.sampwidth != p2.sampwidth
                    or p1.framerate != p2.framerate):
                print("[audio_utils] 混音失败：音频参数不匹配 "
                      f"({p1.nchannels}ch/{p1.sampwidth * 8}bit/{p1.framerate}Hz "
                      f"vs {p2.nchannels}ch/{p2.sampwidth * 8}bit/{p2.framerate}Hz)")
                return False

            total_frames = min(w1.getnframes(), w2.getnframes())
            if total_frames <= 0:
                print("[audio_utils] 混音失败：音频帧数为 0")
                return False

            out_dir = os.path.dirname(out_file)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

            frame_bytes = p1.sampwidth * p1.nchannels
            with wave.open(out_file, "wb") as w_out:
                w_out.setnchannels(p1.nchannels)
                w_out.setsampwidth(p1.sampwidth)
                w_out.setframerate(p1.framerate)

                remaining = total_frames
                while remaining > 0:
                    n = min(_MIX_BLOCK_FRAMES, remaining)
                    data1 = w1.readframes(n)
                    data2 = w2.readframes(n)
                    if not data1 or not data2:
                        break

                    frames_read = min(len(data1), len(data2)) // frame_bytes
                    if frames_read <= 0:
                        break

                    arr1 = np.frombuffer(data1, dtype=np.int16)
                    arr2 = np.frombuffer(data2, dtype=np.int16)
                    # 以较短一路为准对齐（理论上一路已截断，防御性处理）
                    k = min(arr1.size, arr2.size)
                    if k == 0:
                        break
                    mixed = np.clip(
                        arr1[:k].astype(np.int32) + arr2[:k].astype(np.int32),
                        -32768, 32767).astype(np.int16)
                    w_out.writeframes(mixed.tobytes())
                    remaining -= frames_read

        print(f"[audio_utils] 混音完成: {out_file}")
        return True
    except Exception as e:
        print(f"[audio_utils] 混音过程发生异常: {e}")
        return False