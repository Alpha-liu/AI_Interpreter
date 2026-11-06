# -*- coding: utf-8 -*-
"""设置对话框：编辑 API_KEY / WORKSPACE_ID / MODEL / WS_URL，并测试连通性。"""
import json
import time
import threading

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QLabel, QDialogButtonBox, QCheckBox,
)
from PySide6.QtCore import QObject, Signal

from ai_interpreter import config
import websocket
from ai_interpreter.ui.theme import DARK_QSS


class _TestWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, api_key, workspace_id, model, ws_url):
        super().__init__()
        self.api_key = api_key
        self.workspace_id = workspace_id
        self.model = model
        self.ws_url = ws_url

    def run(self):
        ws = None
        try:
            headers = config.build_auth_headers(self.api_key, self.workspace_id)
            
            # 【关键修复】在建立连接前，强制将模型名拼接到 URL 中
            base_url = self.ws_url.split("?")[0]
            connect_url = f"{base_url}?model={self.model}"
            print(f"[测试] 正在连接: {connect_url}")
            
            ws = websocket.create_connection(connect_url, header=headers, timeout=10)
        except Exception as e:
            self.finished.emit(False, f"连接失败: {e}")
            return

        try:
            # 1) 等 session.created
            deadline = time.time() + 8
            created = False
            while time.time() < deadline:
                try:
                    ws.settimeout(max(0.5, deadline - time.time()))
                    msg = ws.recv()
                except Exception as e:
                    self.finished.emit(False, f"等待 session.created 超时/失败: {e}")
                    return
                if not msg:
                    continue
                try:
                    evt = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                t = evt.get("type", "")
                if t == "error":
                    self.finished.emit(False, f"服务端错误: {evt}")
                    return
                if t == "session.created":
                    created = True
                    break
            if not created:
                self.finished.emit(False, "未收到 session.created")
                return

            # 2) 发 session.update (模型名已通过 URL 传递，此处不再包含 model 字段)
            update = {
                "type": "session.update",
                "session": {
                    "output_modalities": ["text"],
                    "translation": {"language": "zh"},
                    "audio": {"input": {
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.0,
                            "silence_duration_ms": 500,
                        },
                    }},
                },
            }
            ws.send(json.dumps(update))

            # 3) 等 session.updated 或 error
            deadline = time.time() + 8
            while time.time() < deadline:
                try:
                    ws.settimeout(max(0.5, deadline - time.time()))
                    msg = ws.recv()
                except Exception as e:
                    self.finished.emit(False, f"等待 session.updated 失败: {e}")
                    return
                if not msg:
                    continue
                try:
                    evt = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                t = evt.get("type", "")
                if t == "error":
                    self.finished.emit(False, f"配置被拒绝: {evt}")
                    return
                if t == "session.updated":
                    self.finished.emit(True, "连接成功，会话配置被接受")
                    return
            self.finished.emit(False, "未收到 session.updated")
        except Exception as e:
            self.finished.emit(False, f"测试过程异常: {e}")
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("模型设置")
        self.setMinimumWidth(540)
        self.setStyleSheet(DARK_QSS)
        self._worker = None
        self._thread = None
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.edit_api_key = QLineEdit()
        self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.cb_show_key = QCheckBox("显示")
        self.cb_show_key.toggled.connect(
            lambda c: self.edit_api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        key_row = QHBoxLayout()
        key_row.addWidget(self.edit_api_key, 1)
        key_row.addWidget(self.cb_show_key)
        form.addRow("API Key:", key_row)

        self.edit_workspace = QLineEdit()
        self.edit_workspace.setPlaceholderText("可选，按服务商要求填写")
        form.addRow("Workspace ID:", self.edit_workspace)

        self.edit_model = QLineEdit()
        self.edit_model.setPlaceholderText("如 qwen3-asr-flash-realtime")
        form.addRow("模型:", self.edit_model)

        self.edit_ws_url = QLineEdit()
        form.addRow("WebSocket URL:", self.edit_ws_url)

        layout.addLayout(form)

        tip = QLabel(f"配置文件: {config.get_config_file()}")
        tip.setStyleSheet("color: #64748b; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.lbl_test = QLabel("")
        self.lbl_test.setWordWrap(True)
        self.lbl_test.setStyleSheet("color: #94a3b8;")
        layout.addWidget(self.lbl_test)

        btn_row = QHBoxLayout()
        self.btn_test = QPushButton("测试连通性")
        self.btn_test.clicked.connect(self._on_test)
        btn_row.addWidget(self.btn_test)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_values(self):
        self.edit_api_key.setText(config.API_KEY)
        self.edit_workspace.setText(config.WORKSPACE_ID)
        self.edit_model.setText(config.MODEL)
        self.edit_ws_url.setText(config.WS_URL)

    def _on_test(self):
        api_key = self.edit_api_key.text().strip()
        workspace = self.edit_workspace.text().strip()
        model = self.edit_model.text().strip()
        ws_url = self.edit_ws_url.text().strip()
        if not api_key:
            self._show_test_result(False, "请先填写 API Key")
            return
        if not model:
            self._show_test_result(False, "请填写模型名称")
            return
        if not ws_url:
            self._show_test_result(False, "请填写 WebSocket URL")
            return

        self.btn_test.setEnabled(False)
        self.btn_test.setText("测试中…")
        self.lbl_test.setText("正在连接…")
        self.lbl_test.setStyleSheet("color: #94a3b8;")

        self._worker = _TestWorker(api_key, workspace, model, ws_url)
        self._worker.finished.connect(self._on_test_finished)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._thread.start()

    def _on_test_finished(self, ok, msg):
        self.btn_test.setEnabled(True)
        self.btn_test.setText("测试连通性")
        self._show_test_result(ok, msg)

    def _show_test_result(self, ok, msg):
        self.lbl_test.setText(("✓ " if ok else "✗ ") + msg)
        self.lbl_test.setStyleSheet(
            "color: #34d399;" if ok else "color: #f87171;")

    def _on_save(self):
        cfg = {
            "api_key": self.edit_api_key.text().strip(),
            "workspace_id": self.edit_workspace.text().strip(),
            "model": self.edit_model.text().strip() or config.DEFAULT_MODEL,
            "ws_url": self.edit_ws_url.text().strip() or config.DEFAULT_WS_URL,
        }
        if not cfg["api_key"]:
            self._show_test_result(False, "API Key 不能为空")
            return
        if config.save_config(**cfg):
            config.reload()
            self.accept()
        else:
            self._show_test_result(False, "保存失败，请查看控制台日志")