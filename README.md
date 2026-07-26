# Screen Translator

一个面向 Windows 的桌面翻译工具，支持：

- 截图区域 OCR 后翻译文字。
- 持续监控屏幕中的指定区域，检测文字变化后自动 OCR 和翻译。
- 读取系统声音、指定进程声音或麦克风，调用阿里云 DashScope Gummy 实时语音翻译接口。
- 使用半透明、圆角、可锁定和鼠标穿透的翻译浮窗显示结果。

## 主要功能

### 截图翻译

1. 框选屏幕上的文字区域。
2. 使用本机 Tesseract OCR 识别文字。
3. 调用 MyMemory 或 LibreTranslate 兼容接口翻译。
4. 在主界面和翻译结果窗口中显示原文与译文。

截图不会自动保存，图像只在内存中处理。

### 屏幕持续监控

- 支持连续框选多个监控区域。
- 只有检测到区域文字发生变化时才重新 OCR 和翻译。
- 支持设置扫描间隔、管理区域、启用/停用区域。
- 结果显示在置顶的半透明翻译窗口中。
- 翻译窗口支持拖动、锁定、鼠标穿透、自动滚动和透明度调整。

### 音频实时翻译

音频翻译是独立功能，不会改变原有的截图 OCR 和屏幕监控流程。

支持三种音频来源：

- 系统全局声音：使用 WASAPI Loopback 捕获默认输出设备。
- 指定进程声音：使用 Windows Application Loopback 捕获目标进程，可包含其子进程。
- 麦克风：使用普通音频输入设备。

音频处理流程如下：

~~~text
音频设备
  -> 统一转换为 16 kHz、单声道、16-bit PCM
  -> 本地 VAD 检测语音并切分
  -> 仅在检测到语音时上传音频
  -> DashScope Gummy 返回语音识别文本和翻译文本
  -> 音频翻译窗口显示当前句子和历史记录
~~~

本地 VAD 只负责检测是否有声音、保留前后缓冲和切分句子。当前显示的原文识别结果和中文译文都来自阿里云实时接口，不是本地语音识别模型。

音频窗口功能：

- 当前句子重点显示，原文和译文支持多行滚动。
- 历史记录最多保留 10 句，并自动滚动到最新结果。
- 可分别调整主背景及历史记录、当前翻译字体、当前翻译字体蒙版的不透明度。
- 支持窗口锁定、鼠标穿透和解锁后拖动。
- 音频设备或 API 临时异常时，后台线程会尝试恢复监听。

## 运行环境

- Windows 10/11。
- Python >=3.11,<3.15，支持 Python 3.14。
- 截图 OCR 功能需要额外安装 Tesseract OCR。
- 音频功能需要 PyAudioWPatch 和 DashScope API Key。
- 需要网络连接才能使用在线翻译和阿里云音频翻译接口。

进程级音频捕获使用 Windows Application Loopback API，需要 Windows 10 Build 20348 或更高版本。系统全局声音和麦克风模式不依赖该 API。

### Python 3.14 说明

webrtcvad-wheels 当前只在 Python 3.14 以下版本尝试安装。Python 3.14 环境下，项目会自动使用无额外依赖的 Energy VAD 回退实现，因此仍然可以运行音频翻译功能，但 VAD 行为和 WebRTC VAD 略有不同。

## 安装和启动

推荐使用项目提供的 PowerShell 启动脚本：

~~~powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run.ps1
~~~

脚本会自动：

1. 创建 .venv 虚拟环境。
2. 安装 requirements.txt 中的运行依赖。
3. 设置源码路径。
4. 启动程序。

也可以手动运行：

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m screen_translator
~~~

旧的开发入口仍然可用：

~~~powershell
.\.venv\Scripts\python.exe main.py
~~~

## 首次配置

### 截图翻译

在“设置”中配置：

- 截图翻译、持续监控和音频翻译分别拥有独立的热键与“启用”开关；截图翻译默认使用 Ctrl+Shift+T，持续监控和音频翻译热键默认关闭。
- 翻译接口地址，默认：

  https://api.mymemory.translated.net/get

- 翻译接口 API key（可选）。
- tesseract.exe 的完整路径。

MyMemory 适合小规模测试，不适合发送密码、隐私资料或大量文本。需要更稳定的服务时，可以配置自己的 LibreTranslate 服务器或其他兼容接口。

### 音频翻译

在“设置”中配置：

- 阿里云 DashScope API Key。
- 音频来源：系统全局声音、指定进程或麦克风。
- 音频设备。
- 目标进程和是否包含子进程。
- 音频源语言和目标语言。
- VAD 灵敏度。
- 句尾静音阈值，默认 500 毫秒。
- 历史记录数量，最多 10 句。

API Key 也可以通过环境变量提供：

~~~powershell
$env:DASHSCOPE_API_KEY = "your-api-key"
.\run.ps1
~~~

音频翻译主界面中还可以调整音频窗口的三项透明度，并使用“锁定音频窗口”按钮启用鼠标穿透。锁定后需要通过主界面按钮解锁。

## 测试

安装开发依赖：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
~~~

运行全部测试：

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
~~~

运行源码编译检查：

~~~powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
~~~

测试覆盖配置读写、文本翻译、快捷键、文本处理，以及 WebRTC VAD / Energy VAD 回退和音频切分逻辑。

## 打包

项目使用 PyInstaller 打包。先安装开发依赖，然后运行：

~~~powershell
.\scripts\build.ps1
~~~

如果项目没有完整的内置 Tesseract，可以生成依赖外部 Tesseract 的开发版：

~~~powershell
.\scripts\build.ps1 -AllowExternalTesseract
~~~

默认输出目录：

~~~text
dist\ScreenTranslator
~~~

正式发布时，建议将以下文件放入项目目录：

~~~text
vendor\tesseract\tesseract.exe
vendor\tesseract\tessdata\eng.traineddata
~~~

打包脚本会自动收集 DashScope、PyAudioWPatch，以及当前环境中可用的 WebRTC VAD 模块。旧的 dist 不会自动同步源码修改，修改音频功能后需要重新打包。

## 项目结构

~~~text
src/screen_translator/
├── application.py       # 应用入口
├── capture.py           # 截图选择和监控区域
├── ocr.py               # Tesseract OCR
├── translator.py        # 文本翻译接口
├── workers.py           # 截图翻译线程
├── audio_capture.py     # 全局声音、进程声音、麦克风采集
├── windows_loopback.py  # Windows Application Loopback API
├── vad.py               # WebRTC VAD 和 Energy VAD 回退
├── audio_translation.py # 音频切片、API 会话和重试
└── ui/
    ├── main_window.py   # 主界面和功能协调
    ├── results.py       # 截图持续翻译窗口
    ├── audio_results.py # 音频翻译窗口
    └── settings.py      # 设置窗口
~~~

配置文件默认保存在：

~~~text
%APPDATA%\ScreenTranslator\settings.json
~~~

## 当前限制

- 在线翻译和音频翻译受网络延迟、接口配额、服务端限制和 API Key 状态影响，不能保证所有句子都在固定时间内返回。
- 进程级音频捕获需要 Windows 10 Build 20348 或更高版本；目标进程必须实际输出音频。
- 独占全屏 DirectX 游戏、管理员权限程序和反作弊保护程序，可能阻止桌面截图、窗口覆盖、鼠标穿透或全局热键。
- 音频设备被其他程序独占、设备断开或系统音频格式异常时，音频线程会报告错误并尝试恢复；必要时需要重新选择设备。
- Tesseract 只用于截图 OCR，不是音频翻译的依赖。
- 音频翻译仍然依赖云端 DashScope 服务；VAD 在本地运行主要用于减少静音上传和控制句子长度。
- 半透明窗口的实际覆盖效果受 Windows 缩放比例、全屏模式、显卡驱动和窗口权限影响。
