# 会议同声传译（AI Interpreter）

基于阿里qwen3.8-livetranslate-flash-realtime实时语音翻译（WebSocket）的桌面同传工具。同时采集**我的麦克风**与**系统扬声器环回（对方声音）**两路音频，实时翻译成目标语言，以悬浮字幕显示，并落盘保存录音与双语字幕。

## 功能

- 双通道实时翻译：麦克风（我说的）→ 目标语言；扬声器环回（对方说的）→ 目标语言
- 悬浮字幕窗：打字机效果、双语/仅原文/仅译文、字号/颜色/透明度可调、鼠标穿透、全屏、左右拖拽/缩放
- 实时字幕预览（主窗口左右两栏）
- 硬件自检：麦克风 / 扬声器采集电平测试
- 自动重连（指数退避）、VAD 断句、按 Turn 成对输出字幕
- 结束时保存：两路 WAV、合并 WAV、单通道 SRT、合并会议纪要 SRT

## 目录结构

```text
.
├── src/ai_interpreter/        # 应用包
│   ├── app.py                 # 应用入口 / 全局调度（ConferenceInterpreter、main）
│   ├── config.py              # 配置读写、鉴权头、目标语言表
│   ├── live_session.py        # WebSocket 实时翻译会话
│   ├── turn_tracker.py        # Turn 归属状态机（item_id + FIFO 配对）
│   ├── text_utils.py          # 字幕整句切分 / 原文译文对齐
│   ├── audio/                 # 音频层
│   │   ├── mic.py             # 麦克风采集（sounddevice）
│   │   ├── loopback.py        # 扬声器环回采集（PyAudioWPatch）
│   │   ├── utils.py           # 重采样 / 峰值 / WAV 混音
│   │   ├── recorder.py        # 线程安全 WAV 写入
│   │   └── subtitles.py       # 字幕时序记录与 SRT 落盘
│   ├── ui/                    # Qt 界面层
│   │   ├── main_window.py     # 主控制台（深色仪表盘）
│   │   ├── lyric_window.py    # 悬浮字幕窗 + 控制栏
│   │   ├── settings_dialog.py # 模型设置对话框
│   │   ├── theme.py           # 深色主题样式表
│   │   ├── widgets.py         # 圆形聆听动效、滑动开关
│   │   ├── bridge.py          # 后台事件 → Qt 信号桥
│   │   └── hw_test_worker.py  # 硬件自检 worker（QThread）
│   └── tools/                 # 命令行诊断
│       ├── hw_test.py         # 通道链路 / VAD / 事件字段诊断
│       └── probe.py           # 最小 WebSocket 握手探针
├── tests/                     # pytest 测试
├── assets/                    # 界面预览图
├── main.py                    # 直接运行入口（免安装，自动加入 src 路径）
├── config.example.json        # 配置示例（不含真实密钥）
├── pyproject.toml             # 打包、依赖与 pytest 配置
├── requirements.txt           # 运行时依赖（pip 便捷安装）
├── CHANGELOG.md
└── README.md
```

## 安装

需要 Windows（环回采集依赖 WASAPI）。Python 3.9+。

```powershell
# 方式一：只装依赖，直接运行
python -m pip install -r requirements.txt
python main.py

# 方式二：作为包安装（推荐）
python -m pip install -e ".[dev]"
python -m ai_interpreter
```

## 配置

首次运行后在「系统设置」里填写 **API Key**（必填）、**Workspace ID**（按服务商要求）、**模型**、**WebSocket URL**，点击保存后写入：

- 首选 `%APPDATA%\ConferenceInterpreter\config.json`
- 回退 `~/.conference_interpreter/config.json`
- 再回退 `./user_config/config.json`

也可以复制示例文件后直接填写：

```powershell
copy config.example.json "%APPDATA%\ConferenceInterpreter\config.json"
```

示例文件 `config.example.json` 的字段如下（`api_key` 为占位符，需替换为自己的密钥）：

```json
{
  "api_key": "sk-ws-REPLACE_WITH_YOUR_API_KEY",
  "workspace_id": "ws-f2u9w7cxffmu7t9h",
  "model": "qwen3.8-livetranslate-flash-realtime",
  "ws_url": "wss://ws-f2u9w7cxffmu7t9h.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime"
}
```

> 源码里不保存任何密钥。命令行探针通过环境变量 `DASHSCOPE_API_KEY` 读取。`config.example.json` 可安全提交；真实的 `config.json` 已被 `.gitignore` 忽略。

## 运行

```powershell
python main.py
```

1. 选择「麦克风输入」与「扬声器环回」设备（可先点「测麦克风 / 测扬声器」自检）
2. 设置两路各自的目标语言
3. 点「开始翻译」；中途可「暂停」；结束后点「停止并保存」——保存/混音在后台进行，界面会显示「保存中…」，完成后自动恢复

诊断脚本（需先 `pip install -e .`，或设置 `PYTHONPATH=src`）：

```powershell
python -m ai_interpreter.tools.hw_test    # 通道链路 + VAD + 事件字段诊断
python -m ai_interpreter.tools.probe      # 最小 WebSocket 握手探针（需 DASHSCOPE_API_KEY）
```

## 开发与测试

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m pyflakes src tests main.py
```

## 输出

保存到 `record/`：

- `user_mic_<时间戳>.wav` / `participant_loopback_<时间戳>.wav`：两路原始录音（16kHz 单声道）
- `meeting_merged_audio_<时间戳>.wav`：两路混音
- `user_subtitles_*.srt` / `participant_subtitles_*.srt`：单通道字幕
- `meeting_merged_*.srt`：按时间合并的会议纪要

## 实现要点

- **停止后台收尾**（`app.ConferenceInterpreter.stop`）：点击「停止」立即返回界面，停采集、存字幕、混音在后台线程完成，完成后通过 `UiBridge.stopped` 信号回报；关闭窗口/改配置时用 `stop(blocking=True)` 确保落盘完成。
- **录音防崩溃损坏**（`audio.recorder.WavRecorder`）：自行写 RIFF 头并每约 1 秒回填长度字段，进程被强杀后 WAV 仍可播放（最多丢最后约 1 秒）。
- **Turn 归属消除错配**（`turn_tracker.TurnTracker`）：优先用服务端 `item_id` 绑定，译文按 FIFO 与“最早待配对的原文 Turn”配对，迟到译文不再记到下一句名下；断线/停止时 flush 剩余 Turn。
- **WAV 混音流式化**（`audio.utils.mix_wav_files`）：峰值内存与录音时长无关。
- **环回采集关闭时排空队列**：先停生产者再让工作线程处理完剩余帧，停止时不丢尾音。
- **字幕切分**（`text_utils.split_aligned`）：按**整句**切分并让原文/译文**整句对齐**，两边句数不同时只合并相邻整句；SRT、全屏字幕、预览统一使用。
- **全屏平滑上滚**：历史区只在内容变化时重建，16ms 定时器逐帧缓动上滚，消除闪屏。
- **全屏阅读停留**：一句说完后按句长停留 `500ms + 30ms/字`（限制 800–2200ms）再推入历史，符合阅读习惯。
- **UI**：深色仪表盘布局，左侧导航为 实时字幕 / 历史记录 / 系统设置；中央圆形聆听动效由实时电平驱动；深色主题覆盖控制台、模型设置与取色窗。

## 已知限制与后续建议

- 音频后端仍为 `sounddevice`（麦克风）+ `PyAudioWPatch`（环回）两套，可考虑统一，但需真机回归验证。
- 若服务端事件不带 `item_id`/`response_id`，译文只能按 FIFO 猜测配对；建议保持服务端返回 item_id。
- 关闭窗口时会阻塞等待保存（`stop(blocking=True)`），长会议可能等待数秒。
- 当前只请求**文本**译文（`output_modalities: ["text"]`），不接收/播放翻译后的音频；如需双向语音同传，需要输出音频或接入 TTS，并配合虚拟声卡做音频路由。

## 许可证

尚未指定开源许可证；发布到 GitHub 前请按需补充 `LICENSE`。

## 免责声明

本项目仅供学习与个人使用。请遵守所用语音服务商的条款，并注意会议录音的隐私与授权要求。
