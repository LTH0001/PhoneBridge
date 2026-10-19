# 依赖清单

源码仓库不保存第三方二进制、模型、完整 SDK 或驱动。直接 Python 依赖固定于 `requirements.txt`，打包工具固定于 `requirements-build.txt`。`constraints-windows-py313.txt` 记录当前 Windows x64 / Python 3.13 测试环境的传递依赖版本，CI 使用它限制解析；它不是带 wheel 摘要的跨平台完整锁文件。使用独立虚拟环境，不从系统 Python 环境收集发行依赖。

复用经过测试的解析版本（Python 3.13）可运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints-windows-py313.txt
```

## 最小开发环境

- Windows 11 x64，Python 3.12+，桌面运行需要 Python 自带 Tk。
- [scrcpy 官方发行页](https://github.com/Genymobile/scrcpy/releases/tag/v4.1)：4.1 Windows x64，完整解压到 `vendor/scrcpy/`，确保 `adb.exe`、`scrcpy.exe` 直接位于该目录。不要只复制两个 EXE。保留包内许可；ADB、FFmpeg、SDL 各自许可另计。
- Android 构建：JDK 17+，Android SDK Build Tools 35.0.0，platforms/android-34；自行通过 Android Studio 或官方 SDK Manager 安装并接受相关条款。
- ZXing core 3.5.3（Apache-2.0）：

  ```powershell
  .\.venv\Scripts\python.exe scripts/fetch-dependencies.py zxing
  ```

下载 URL、目标路径和 SHA-256 位于 `scripts/dependencies.json`。已有文件摘要不符时脚本拒绝覆盖；不会安装或执行下载内容。ZXing 对应 [LICENSE](https://github.com/zxing/zxing/blob/zxing-3.5.3/LICENSE) 和 [NOTICE](https://github.com/zxing/zxing/blob/zxing-3.5.3/NOTICE) 应在再分发 APK 时保留。

## 可选功能

| 功能 | 依赖 / 安装方式 | 许可与发布注意 |
| --- | --- | --- |
| 离线语音输入 | Vosk 0.3.45（pip）；small-cn-0.22 模型 | Apache-2.0；模型不存入 Git |
| 原生摄像头 | MinGW-w64 UCRT C++；项目构建脚本 | 构建脚本固定微软头文件摘要；参考示例与编译运行库许可需保留 |
| 扩展桌面 | [Virtual Display Driver 25.7.23](https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/tag/25.7.23) | MIT；附带 Microsoft 工具另计；仅由用户明确选择安装 |
| 系统麦克风 | [VB-CABLE](https://vb-audio.com/Cable/) | 独立 Donationware，用户自行获取安装，不随本项目源码分发 |
| CPU 温度 | LibreHardwareMonitor 0.9.6 + PawnIO 2.2.0 | MPL-2.0 / GPL 与例外条款；保留对应源码材料 |
| GPU 数据 | 用户既有 GPU 驱动、Windows 性能接口 | 不复制或重新分发显卡驱动 |
| 联网歌词 | 用户开启后查询 LRCLIB | 歌词权利独立，不分发歌词库 |

离线模型获取：

```powershell
.\.venv\Scripts\python.exe scripts/fetch-dependencies.py vosk-model
Expand-Archive -LiteralPath vendor/vosk-model-small-cn-0.22.zip -DestinationPath vendor
```

只解压已校验的官方压缩包，不使用 `-Force` 覆盖已有模型；确保最终路径为 `vendor/vosk-model-small-cn-0.22/am/` 等目录。保留模型原始许可；语音音频默认送到你自己的电脑识别。

`scripts/setup-temperature.ps1` 可下载并校验固定温度组件，但不会代替用户安装驱动；它还会访问上游许可文本。原生摄像头构建也会访问固定的微软 SDK 头文件。最小构建不需要运行这两个可选脚本。

## 依赖分类与来源审查

`THIRD_PARTY_NOTICES.md` 区分直接使用、设计参考、系统前置依赖和未确认旧二进制。Python 版本固定不等于安全审计；发布者还应检查传递依赖、原生 FFmpeg 配置、模型、驱动以及对应源码义务。旧 Softcam DLL 不进入源码包，也不进入 Windows 构建白名单。
