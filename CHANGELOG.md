# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构，版本号采用 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0]

### Added

- 双通道实时翻译：麦克风与系统扬声器环回两路采集。
- 悬浮字幕窗：打字机、双语/单语、字号/颜色/透明度、鼠标穿透、全屏、拖拽缩放。
- 主控制台：深色仪表盘布局、实时电平与计时、硬件自检、字幕双栏预览。
- Turn 归属状态机（`turn_tracker`），按服务端 `item_id` + FIFO 配对原文/译文。
- 字幕整句切分与原文/译文对齐（`text_utils`）。
- 录音与字幕落盘：两路 WAV、合并 WAV、单通道/合并 SRT。
- 配置示例 `config.example.json`（字段与 `config.py` 一致，不含真实密钥）。
- 停止后台收尾、崩溃日志容错、WAV 头定期回填。

### Changed

- 工程结构重构为 `src/` 布局与 `ai_interpreter` 包，按 `audio` / `ui` / `tools` 分层。
- 原根目录脚本迁移：`main.py` → `ai_interpreter/app.py`（根目录保留免安装启动器），`ui_main.py` → `ui/main_window.py` 等。
- 依赖与 pytest 配置统一到 `pyproject.toml`，新增 `tests/` 测试目录。
- 全屏字幕增加阅读停留与平滑上滚；取色窗、模型设置统一为深色主题。

### Fixed

- 修复环回设备被占用导致“设备未就绪”以及“开始翻译”失败的问题：硬件测试无论成功失败都会释放设备；打开失败时等待后重试一次；设备索引失效时回退默认环回；启动等待时间从 3s 提升到 6s 并处理超时竞态。
- 传译进行中禁止设备自检、设备自检进行中禁止开始翻译，避免同一环回设备被重复打开。
- 启动失败时恢复按钮状态，可直接重试。

### Security

- 移除源码中硬编码的 API Key，命令行探针改用 `DASHSCOPE_API_KEY` 环境变量。
