# -*- coding: utf-8 -*-
"""系统环回（扬声器输出）采集。使用音频处理队列解耦回调，防止阻塞。"""
import threading
import time
import queue
import pyaudiowpatch as pyaudio
from ai_interpreter.audio.utils import resample_pcm, pcm_peak


def list_loopback_devices():
    results = []
    with pyaudio.PyAudio() as p:
        for info in p.get_loopback_device_info_generator():
            name = info["name"].replace(" [Loopback]", "")
            results.append((info["index"], name))
    return results


class LoopbackCapture:
    def __init__(self, on_pcm, recorder=None, target_sample_rate=16000,
                 loopback_index=None, chunk_ms=100, on_level=None):
        self.on_pcm = on_pcm
        self.recorder = recorder
        self.target_sr = target_sample_rate
        self.loopback_index = loopback_index
        self.chunk_ms = max(20, chunk_ms)
        self.on_level = on_level
        self._running = False
        self._paused = False
        self._thread = None
        self._stream = None
        self._buffer = bytearray()
        self._buffer_target = int(self.target_sr * chunk_ms / 1000) * 2  # int16
        self._started_event = threading.Event()
        self._start_error = None
        
        # 引入队列解耦
        self._raw_queue = queue.Queue(maxsize=50) 
        self._worker_thread = None
        # 关闭时先停生产者再排空队列，避免丢掉末尾音频
        self._worker_stop = threading.Event()

    @property
    def stream(self):
        return self._stream

    def start(self):
        if self._running:
            return
        self._running = True
        self._paused = False
        self._started_event.clear()
        self._start_error = None
        self._worker_stop.clear()
        if self.recorder:
            self.recorder.open()
            
        self._worker_thread = threading.Thread(target=self._process_worker, daemon=True)
        self._worker_thread.start()
        
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # 首次打开 WASAPI 设备可能较慢；超时后终止本次启动并记录错误，
        # 避免“线程稍后才打开成功、调用方却已判定失败”的竞态。
        if not self._started_event.wait(timeout=6.0):
            self._start_error = self._start_error or "打开音频设备超时"
            self._running = False

    def _process_worker(self):
        """独立的工作线程，负责重采样和分块。

        关闭时不是立即退出，而是把队列里剩余的帧处理完再退出，
        这样最后一秒左右的尾音不会被丢掉。
        """
        while True:
            # 收到停止信号后，继续处理直到队列排空
            if self._worker_stop.is_set() and self._raw_queue.empty():
                break
            try:
                in_data, src_rate, channels = self._raw_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if self._paused:
                continue

            try:
                pcm = resample_pcm(in_data, src_rate, self.target_sr, channels)
                if pcm:
                    if self.on_level:
                        try:
                            self.on_level(pcm_peak(pcm))
                        except Exception:
                            pass
                    self._buffer.extend(pcm)
                    while len(self._buffer) >= self._buffer_target:
                        chunk = bytes(self._buffer[:self._buffer_target])
                        del self._buffer[:self._buffer_target]
                        self.on_pcm(chunk)
                        if self.recorder:
                            self.recorder.write(chunk)
            except Exception as e:
                print(f"[loopback] 工作线程处理异常: {e}")

    def _run(self):
        try:
            if not self._running:
                return
            with pyaudio.PyAudio() as p:
                try:
                    if self.loopback_index is not None:
                        try:
                            dev = p.get_wasapi_loopback_analogue_by_index(self.loopback_index)
                        except (OSError, LookupError, ValueError):
                            # 设备热插拔后序号可能失效，回退默认环回设备
                            dev = p.get_default_wasapi_loopback()
                    else:
                        dev = p.get_default_wasapi_loopback()
                except OSError as e:
                    self._start_error = str(e)
                    self._running = False
                    return

                src_rate = int(dev["defaultSampleRate"])
                channels = dev["maxInputChannels"]

                def cb(in_data, frame_count, time_info, status):
                    if self._running and not self._paused:
                        try:
                            # 只做拷贝和入队，保证回调迅速返回
                            self._raw_queue.put_nowait((bytes(in_data), src_rate, channels))
                        except queue.Full:
                            pass # 队列满时丢弃当前帧，防止阻塞
                        except Exception as e:
                            print(f"[loopback] 回调异常: {e}")
                    return (in_data, pyaudio.paContinue)

                # 同一环回设备同一时刻只能被一路打开（否则 -9999）。
                # 若上一路刚释放，稍等后重试一次。
                stream, last_err = None, None
                for attempt in range(2):
                    if not self._running:
                        return
                    try:
                        stream = p.open(format=pyaudio.paInt16, channels=channels,
                                        rate=src_rate, input=True,
                                        input_device_index=dev["index"],
                                        frames_per_buffer=1024,
                                        stream_callback=cb)
                        break
                    except OSError as e:
                        last_err = e
                        if attempt == 0:
                            print(f"[loopback] 设备占用/打开失败，重试: {e}")
                            time.sleep(0.4)
                            continue
                        self._start_error = str(e)
                        self._running = False
                        return

                if stream is None:
                    self._start_error = str(last_err) if last_err else "打开音频设备失败"
                    self._running = False
                    return

                with stream:
                    self._stream = stream
                    self._started_event.set()
                    print(f"[loopback] 捕获: {dev['name']}, "
                          f"{src_rate}Hz, {channels}ch -> {self.target_sr}Hz mono")
                    while self._running:
                        time.sleep(0.1)
        except Exception as e:
            self._start_error = str(e)
            print(f"[loopback] 打开失败: {e}")
        finally:
            self._started_event.set()
            self._stream = None

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        # 1) 先停生产者（_run 线程 / 音频回调），确保不再有新帧入队
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        # 2) 再通知工作线程把队列排空后退出，尾音不会被截断
        self._worker_stop.set()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None

        # 冲刷不足一个 chunk 的剩余样本
        if self._buffer:
            chunk = bytes(self._buffer)
            self._buffer.clear()
            try:
                self.on_pcm(chunk)
            except Exception:
                pass
            if self.recorder:
                try:
                    self.recorder.write(chunk)
                except Exception:
                    pass

        if self.recorder:
            self.recorder.close()