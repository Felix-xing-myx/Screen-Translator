# Screen Translator

Screen Translator 是一个面向 Windows 的桌面翻译工具，当前版本为 1.0.3。
它把本地 OCR、屏幕区域监控和实时音频翻译组合在一个轻量的 Qt 浮窗工作流中。

## 功能

- 截图翻译：框选屏幕区域，使用本机 Tesseract OCR 后翻译。
- 持续监控：监控多个屏幕区域，检测文字变化后自动识别和翻译。
- 音频翻译：捕获系统声音、指定进程声音或麦克风，调用 DashScope Gummy 实时翻译。
- 结果浮窗：支持透明度、字体、拖动、调整大小、锁定和鼠标穿透。
- 系统托盘：关闭主窗口后驻留托盘，左键打开，右键打开主窗口或退出。
- 单实例运行：重复启动不会创建第二个程序进程。

## 运行要求

- Windows 10/11。
- Python 3.11-3.14，仅开发运行需要 Python。
- 网络连接，用于在线翻译和 DashScope 音频翻译。
- 截图 OCR 使用项目内置的 Tesseract Windows runtime。
- 进程级音频捕获需要 Windows 10 Build 20348 或更高版本。

正式用户不需要安装 Python、PySide6、Tesseract 或 PyInstaller；直接使用
发布的安装包即可。

## 开发环境

项目采用标准 Python src-layout：

~~~text
pyproject.toml
  -> uv.lock
  -> .venv
  -> editable install of src/screen_translator
~~~

推荐使用 uv 管理环境。项目根目录就是 E:\translate，不能把
src\screen_translator 单独作为工作区打开。

### 初始化环境

在项目根目录执行：

~~~powershell
.\scripts\bootstrap.ps1
~~~

该脚本会同步 pyproject.toml 中的依赖，创建或更新项目根目录下的 .venv，
并以 editable mode 安装当前源码。

如果已经安装 uv，也可以直接执行：

~~~powershell
uv sync --extra dev
~~~

没有 uv 时，bootstrap.ps1 会自动回退到 Python venv 和 pip。

### 启动和测试

~~~powershell
.\scripts\run.ps1
.\scripts\test.ps1
~~~

等价的直接命令：

~~~powershell
uv run --extra dev python -m screen_translator
uv run --extra dev python -m pytest -q
uv run --extra dev ruff check src tests
~~~

正常开发不需要设置 PYTHONPATH，也不需要手动执行 main.py。

## 配置

设置中心可以配置：

- 截图翻译、持续监控和音频翻译的独立热键。
- Qwen-MT、MyMemory 或自定义翻译接口。
- Tesseract 路径、语言、音频来源和目标语言。
- VAD 灵敏度、句尾静音阈值和历史记录数量。
- 翻译浮窗和音频浮窗的大小、位置、透明度和锁定状态。

用户设置保存于：

~~~text
%APPDATA%\ScreenTranslator\settings.json
~~~

API Key 不写入源码、安装包或构建配置。也可以使用环境变量：

~~~powershell
$env:DASHSCOPE_API_KEY = "your-api-key"
.\scripts\run.ps1
~~~

MyMemory 仅建议用于小规模测试。发送敏感内容或大量文本前，应使用自己的
翻译服务并确认服务商的商业和隐私条款。

## 构建

### PyInstaller 目录版

~~~powershell
.\scripts\build.ps1
~~~

输出：

~~~text
dist\ScreenTranslator\
~~~

该目录可以直接作为绿色版程序目录。正式构建要求存在：

~~~text
vendor\tesseract\tesseract.exe
vendor\tesseract\tessdata\eng.traineddata
~~~

### Windows 安装版和免安装版

先安装 Inno Setup 6，然后执行：

~~~powershell
.\scripts\package.ps1
~~~

输出：

~~~text
dist\installer\ScreenTranslator-Setup-v1.0.3.exe
dist\portable\ScreenTranslator-Portable-v1.0.3.zip
~~~

如果只需要目录版，不需要安装 Inno Setup，执行 build.ps1 即可。

## 项目结构

~~~text
ScreenTranslator/
├── src/screen_translator/       应用源码
│   ├── application.py           Qt 应用入口
│   ├── config.py                设置读写
│   ├── models.py                共享数据对象
│   ├── capture.py               截图选择和监控区域
│   ├── screen_capture.py        屏幕捕获 adapter
│   ├── ocr.py                   Tesseract adapter
│   ├── translator.py             文本翻译 adapter
│   ├── audio_capture.py         音频采集 adapter
│   ├── windows_loopback.py       Windows Application Loopback
│   ├── audio_translation.py      音频会话和翻译 workflow
│   ├── workers.py                后台任务
│   ├── vad.py                    语音活动检测
│   ├── hotkeys.py                全局热键
│   └── ui/                       主窗口、设置、浮窗和组件
├── tests/                        自动化测试
├── scripts/                      环境、运行、测试和构建入口
├── packaging/                    Inno Setup 配置和安装器语言文件
├── vendor/tesseract/             随程序分发的 OCR runtime
├── docs/                         架构和设计资料
├── pyproject.toml                依赖、构建和工具配置
├── uv.lock                       可复现依赖解析结果
├── AGENTS.md                     agent 工作区和环境说明
└── CONTRIBUTING.md               开发约定
~~~

生成目录 build、dist、tmp、.venv 和缓存目录不属于源码，已加入 Git 忽略规则。

更详细的模块职责和运行流程见 docs\architecture.md；开发命令见
CONTRIBUTING.md。

## 限制和兼容性

- 在线翻译和音频翻译受网络、API 配额、延迟和服务商条款影响。
- 独占全屏 DirectX、管理员权限程序和反作弊保护程序可能阻止截图、浮窗、
  鼠标穿透或全局热键。
- 目标进程必须实际输出音频，进程级捕获才有有效结果。
- 音频 VAD 在 Python 3.14 下使用 Energy VAD 回退实现。
- API Key、OCR 文本和音频可能发送到第三方服务，请在商业发布时提供清晰的
  隐私政策和第三方服务说明。

## 许可证和发布

项目依赖的 Qt/PySide6、Tesseract、Pillow、requests、DashScope SDK、
PyAudioWPatch 等组件各自遵循其许可证。商业发布前应随安装包提供完整的
第三方许可证和 NOTICE 文件，并确认翻译 API 的商业使用条款。
