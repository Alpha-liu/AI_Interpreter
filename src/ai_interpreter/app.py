# -*- coding: utf-8 -*-
"""应用入口 + 全局调度。加入了崩溃拦截日志。"""
import os
import sys
import time
import threading
import traceback
import faulthandler
from datetime import datetime


def _open_crash_log():
    """打开崩溃日志文件；项目目录不可写时回退到系统临时目录。

    曾经的写法直接 open("crash_log.txt", "w")，一旦该文件被杀软占用或只读，
    整个应用会在启动瞬间因 PermissionError 崩溃。这里改为容错：任一成功即可，
    全都失败则退化为只输出到 stderr。
    """
    candidates = [
        os.path.join(os.getcwd(), "crash_log.txt"),
        os.path.join(
            os.environ.get("TEMP") or os.environ.get("TMP") or os.getcwd(),
            "ai_interpreter_crash_log.txt"),
    ]
    for path in candidates:
        try:
            return open(path, "w", encoding="utf-8")
        except Exception:
            continue
    return None


# 启用 C 层崩溃捕获；日志文件不可写时不影响启动
log_file = _open_crash_log()
try:
    if log_file is not None:
        faulthandler.enable(file=log_file)
    else:
        faulthandler.enable()
except Exception:
    pass

try:
    print("=== [1/4] 正在导入依赖 ===")
    from PySide6.QtWidgets import QApplication
    from ai_interpreter.config import SubtitleConfig
    from ai_interpreter.live_session import TranslationSession
    from ai_interpreter.audio.mic import MicCapture
    from ai_interpreter.audio.loopback import LoopbackCapture
    from ai_interpreter.audio.recorder import WavRecorder
    from ai_interpreter.audio.utils import mix_wav_files
    from ai_interpreter.audio.subtitles import SubtitleRecorder
    from ai_interpreter.ui.bridge import UiBridge
    from ai_interpreter.ui.main_window import ControlPanel
    print("=== [1/4] 依赖导入成功 ===")
except Exception:
    print("=== [Error] 依赖导入失败，详情查看 crash_log.txt ===")
    traceback.print_exc(file=log_file)   # log_file 为 None 时自动输出到 stderr
    if log_file is not None:
        log_file.close()
    sys.exit(1)


class ConferenceInterpreter:
    def __init__(self, my_lang="zh", participant_lang="en"):
        self.user_subtitle = SubtitleConfig(participant_lang)
        self.participant_subtitle = SubtitleConfig(my_lang)
        self.bridge = UiBridge()

        self._mic_index = None
        self._loopback_index = None
        self._started = False

        # 后台收尾（停止/保存/混音）状态
        self._stopping = False
        self._stop_lock = threading.Lock()
        self._stop_thread = None
        self._teardown_done = threading.Event()
        self._teardown_done.set()

        self._user_wav_path = ""
        self._part_wav_path = ""

        self.user_session = None
        self.participant_session = None
        self.user_recorder = None
        self.participant_recorder = None
        self.user_sub_recorder = None
        self.participant_sub_recorder = None
        self.mic = None
        self.loopback = None

    def set_audio_devices(self, mic_index=None, loopback_index=None):
        self._mic_index = mic_index
        self._loopback_index = loopback_index

    def start(self):
        if self._started:
            return
        if self._stopping:
            raise RuntimeError("上一场会议仍在保存，请稍候再开始")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_base = time.time()

        self.user_sub_recorder = SubtitleRecorder("user", "我", base_ts=session_base)
        self.participant_sub_recorder = SubtitleRecorder("participant", "参会者", base_ts=session_base)
        
        self._user_wav_path = f"record/user_mic_{timestamp}.wav"
        self._part_wav_path = f"record/participant_loopback_{timestamp}.wav"
        
        self.user_recorder = WavRecorder(self._user_wav_path)
        self.participant_recorder = WavRecorder(self._part_wav_path)

        try:
            def src_delta(ch, txt): self.bridge.emit_source_delta(ch, txt)
            def src_done(ch, iid, txt): self.bridge.emit_source_done(ch, iid, txt)
            def tgt_delta(ch, txt): self.bridge.emit_target_delta(ch, txt)
            def tgt_done(ch, iid, txt): self.bridge.emit_target_done(ch, iid, txt)
            def mic_level(peak): self.bridge.emit_level("user", peak)
            def spk_level(peak): self.bridge.emit_level("participant", peak)

            self.user_session = TranslationSession("user", self.user_subtitle, src_delta, src_done, tgt_delta, tgt_done, self.user_sub_recorder)
            self.participant_session = TranslationSession("participant", self.participant_subtitle, src_delta, src_done, tgt_delta, tgt_done, self.participant_sub_recorder)

            self.mic = MicCapture(on_pcm=self.user_session.feed_audio, recorder=self.user_recorder,
                                  device_index=self._mic_index, on_level=mic_level)
            self.loopback = LoopbackCapture(on_pcm=self.participant_session.feed_audio, recorder=self.participant_recorder,
                                            loopback_index=self._loopback_index, on_level=spk_level)

            self.user_session.connect()
            self.mic.start()
            if self.mic.stream is None:
                raise RuntimeError(f"麦克风启动失败: {self.mic._start_error}")

            self.participant_session.connect()
            self.loopback.start()
            if self.loopback.stream is None:
                raise RuntimeError(f"环回启动失败: {self.loopback._start_error}")

            self._started = True
            self._stopping = False
            self._teardown_done.clear()
        except Exception as e:
            print(f"[main] 启动失败: {e}")
            self._cleanup_partial_start()
            raise

    def _cleanup_partial_start(self):
        for obj in (self.mic, self.loopback):
            try:
                if obj: obj.stop()
            except Exception: pass
        for obj in (self.user_session, self.participant_session):
            try:
                if obj: obj.close()
            except Exception: pass
        self._started = False
        self._stopping = False
        self._teardown_done.set()

    def pause(self):
        if not self._started: return
        if self.mic: self.mic.pause()
        if self.loopback: self.loopback.pause()
        if self.user_session: self.user_session.pause()
        if self.participant_session: self.participant_session.pause()

    def resume(self):
        if not self._started: return
        if self.mic: self.mic.resume()
        if self.loopback: self.loopback.resume()
        if self.user_session: self.user_session.resume()
        if self.participant_session: self.participant_session.resume()

    def set_subtitle(self, channel: str, show_source=None, show_target=None, target_lang=None):
        cfg = (self.user_subtitle if channel == "user" else self.participant_subtitle)
        if show_source is not None: cfg.show_source = show_source
        if show_target is not None: cfg.show_target = show_target
        if target_lang is not None:
            cfg.target_lang = target_lang
            sess = (self.user_session if channel == "user" else self.participant_session)
            if sess: sess.update_target_language(target_lang)

    def stop(self, blocking: bool = False):
        """停止传译并在后台保存文件（阻塞式线程安全）。

        blocking=False：立即返回，保存/混音在后台线程完成，完成后发 stopped 信号。
        blocking=True ：等到落盘结束才返回（关闭窗口 / 改配置时使用）。
        反复调用是安全的。
        """
        with self._stop_lock:
            if not self._started:
                need = False
            else:
                self._started = False
                self._stopping = True
                need = True
        if not need:
            if blocking:
                self._teardown_done.wait()
            return

        if blocking:
            try:
                self._teardown()
            finally:
                with self._stop_lock:
                    self._stopping = False
                self._teardown_done.set()
            return

        t = threading.Thread(target=self._teardown_async, daemon=True)
        self._stop_thread = t
        t.start()

    def _teardown_async(self):
        try:
            self._teardown()
        except Exception as e:
            print(f"[main] 后台保存异常: {e}")
        finally:
            with self._stop_lock:
                self._stopping = False
            self._teardown_done.set()
            try:
                self.bridge.emit_stopped()
            except Exception:
                pass

    def _teardown(self):
        """真正的收尾：停采集 → 关会话 → 存字幕 → 混音。"""
        if self.mic:
            try: self.mic.stop()
            except Exception as e: print(f"[main] 停止麦克风失败: {e}")
        if self.loopback:
            try: self.loopback.stop()
            except Exception as e: print(f"[main] 停止环回失败: {e}")

        # 给音频发送线程一点时间排空积压
        time.sleep(0.6)
        if self.user_session:
            try: self.user_session.close()
            except Exception as e: print(f"[main] 关闭 user 会话失败: {e}")
        if self.participant_session:
            try: self.participant_session.close()
            except Exception as e: print(f"[main] 关闭 participant 会话失败: {e}")

        try:
            user_entries = self.user_sub_recorder.save() if self.user_sub_recorder else []
            part_entries = self.participant_sub_recorder.save() if self.participant_sub_recorder else []
            SubtitleRecorder.save_merged(user_entries + part_entries)
        except Exception as e:
            print(f"[main] 保存字幕失败: {e}")

        if self._user_wav_path and self._part_wav_path:
            merged_wav_path = f"record/meeting_merged_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            print("[main] 正在合并音轨...")
            mix_wav_files(self._user_wav_path, self._part_wav_path, merged_wav_path)


def main(argv=None):
    """启动 Qt 应用并进入事件循环，返回进程退出码。"""
    argv = list(sys.argv if argv is None else argv)
    print("=== [2/4] 正在初始化 Qt 应用 ===")
    app = QApplication(argv)

    print("=== [3/4] 正在构建界面 (探测音频设备中) ===")
    try:
        interpreter = ConferenceInterpreter(my_lang="zh", participant_lang="en")
        panel = ControlPanel(interpreter, interpreter.bridge)
        panel.show()
        panel.lyric_window.show()
        print("=== [4/4] 启动成功，进入事件循环 ===")
    except Exception as e:
        print(f"界面构建异常: {e}")
        traceback.print_exc(file=log_file)
        if log_file is not None:
            log_file.close()
        return 1

    # 确保退出时关闭日志
    exit_code = app.exec()
    if log_file is not None:
        log_file.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())