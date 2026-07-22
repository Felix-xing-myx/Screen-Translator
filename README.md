# Screen Translator

一个面向 Windows 的屏幕区域翻译 MVP：框选屏幕区域，识别其中的英文，再调用免费的 MyMemory 接口翻译成中文。也支持 LibreTranslate 兼容接口。

## 运行环境

- Windows 10/11
- Python 3.11 或更高版本
- Tesseract OCR（需要额外安装）
- 网络连接；默认使用 MyMemory 免费翻译接口

## 安装和运行

1. 安装 Python，并在安装界面勾选 `Add Python to PATH`。
2. 安装 Tesseract OCR。安装后如果命令 `tesseract` 不在 PATH 中，在程序的“设置”里填写 `tesseract.exe` 的完整路径。
3. 在本目录打开 PowerShell，运行：

   ```powershell
   .\run.ps1
   ```

也可以手动运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## 使用方式

1. 点击“截图翻译”，或按全局热键 `Ctrl+Shift+T`。
2. 在屏幕上拖动鼠标框选英文区域。
3. 等待 OCR 和翻译结果。
4. 在设置中可以修改翻译接口地址、API key 和 Tesseract 路径。

也可以点击“开始持续监控”，选择监控主显示器全屏或进入多区域框选模式，并设置扫描间隔。多区域模式下可以连续框选多个区域；程序会分别 OCR，只有某个区域的文字发生变化时才调用翻译接口，结果会统一显示在置顶窗口中。

持续翻译窗口固定为默认大小，可以在解锁状态下拖动位置；锁定、解锁和停止监控统一由主界面控制。监控运行中点击“管理监控区域”可以新增、移动、调整大小、删除或启用/停用区域，按 Enter 应用，按 Esc 取消。翻译窗口会统一显示各区域译文，长文本会自动滚动。

当前界面使用深色半透明主题。主界面可以分别调整窗口背景、翻译文字和文字蒙版的不透明度，以及翻译字体大小；翻译窗口使用自定义标题栏、圆角卡片和阴影效果。

默认翻译接口地址是 `https://api.mymemory.translated.net/get`。MyMemory 有使用限制，且不适合发送密码、隐私资料或大量文本。

如果需要更稳定的服务，可以在设置中换成自己的 LibreTranslate 服务器或其他兼容接口。

## 当前版本的边界

- 默认全局热键为 `Ctrl+Shift+T`，可以在“设置”中点击热键输入框后录入新的组合键；如果新组合键被其他程序占用，程序会恢复旧热键。
- 持续监控支持主显示器全屏或多个指定区域，默认每 2 秒检查一次；MyMemory 等免费接口可能有请求频率和文本长度限制。
- 持续翻译窗口的锁定/鼠标穿透效果受 Windows、全屏模式和游戏权限影响；独占全屏或反作弊程序不保证能覆盖显示。
- 当前默认处理主显示器；截图改用 mss，通常比 Qt 截图更适合无边框全屏程序。
- 独占全屏 DirectX 游戏、管理员权限程序和反作弊保护程序，可能阻止桌面截图或全局热键，这是 Windows 权限限制。
- OCR 依赖本机 Tesseract，翻译依赖网络接口。
- 不会自动保存截图；截图只保存在内存中并传给 OCR。
