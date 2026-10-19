# PhoneBridge

把 Android 手机变成 Windows 电脑的摄像头、麦克风、触控板与触屏副屏。

PhoneBridge includes a Windows host, an Android companion app, and a local API. Project-owned code is licensed under MIT; third-party components retain their own licenses.

当前版本 **0.8.10 · 开发预览**。面向 Windows 11 x64 / Android 8.0+（最低 API 26）；实际完整功能只在有限设备上验证，不能视为所有机型兼容。尚未提供正式签名安装器。

## 功能与边界

| 能力 | 当前状态 / 前置条件 |
| --- | --- |
| 手机摄像头、麦克风、传感器 | 已实现；需手机明确授权，默认优先前摄 |
| Windows 系统摄像头 | 原生 Media Foundation 后端；需构建和注册，会议软件兼容性需分别验证 |
| Windows 系统麦克风 | 需用户自行安装并选择 VB-CABLE 等虚拟音频设备 |
| 手机查看和操作电脑扩展桌面 | H.264 传输与触屏回传；需独立虚拟显示驱动 |
| 手机镜像到电脑 | 调用 scrcpy 独立进程 |
| 控制面板 | CPU/GPU/内存/磁盘、音乐、播放设备、歌词与音量控制 |
| 触控板 / 数字区 / 语音输入 | 已实现；离线语音需另取 Vosk 中文模型 |
| 有线 ADB | 当前推荐连接方式；需 USB 调试、数据线与电脑授权，不需要无线调试 |
| 免调试 AOA / 无线 TLS | 实验性；存在设备枚举、驱动或网络适配问题，不承诺插线即用 |
| 文件与相册 | 受 Android 授权和传输实现限制，不意味着可获取手机全部权限 |

## 从源码运行

1. 安装 64 位 Python 3.12+（当前验证环境为 3.13）。在项目根目录运行：

   ```powershell
   powershell -NoProfile -File scripts/setup.ps1
   ```

2. 按 [依赖说明](docs/DEPENDENCIES.md) 将官方 scrcpy Windows 包完整解压到 `vendor/scrcpy/`。基础连接需要其中的 `adb.exe`；镜像还需要其余组件。
3. 按 [构建说明](docs/BUILDING.md) 构建 Android APK，将 `android/app/build/phonebridge.apk` 传到手机确认安装。
4. 手机打开 USB 调试，插入数据线并授权你自己的电脑。启动手机 PhoneBridge，再双击 `start.bat`，选择“USB 调试 · 已授权”的手机连接。

不需要一次装齐全部可选驱动。建议先验证连接和控制面板，再按需要配置摄像头、副屏和温度采集。源代码包不包含 APK、第三方驱动、模型或签名密钥。

如果遇到端口被占用，先检查是否已经运行了另一个 PhoneBridge 实例；不要直接结束未知进程。连接失败时确认数据线支持数据传输、手机授权状态和厂商 ADB 驱动。免调试 AOA 启动失败不能靠反复点击授权解决。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
powershell -NoProfile -File scripts/check-panel-gestures.ps1
.\.venv\Scripts\python.exe scripts/audit-source.py
.\.venv\Scripts\python.exe scripts/package-source.py
```

Java 手势测试需要 JDK 17+ 与 `JAVA_HOME`，不需要连接手机。Python 单元测试不等于真实 USB、摄像头或干净电脑兼容性验收。源码导出在 `dist/` 生成白名单源码目录、ZIP 和文件摘要，不提交、不上传。

## 项目结构

```text
phonebridge/       Windows 主程序、API、传输、面板与硬件查询
android/app/       Android Java 源码、资源与 Manifest
native/mf-camera/  原生 Windows 虚拟摄像头
assets/brand/      项目图标源文件
scripts/           构建、依赖获取、系统组件管理和源码检查
tests/             Python 回归及纯 Java 手势测试
docs/              架构、依赖、构建、发布说明
vendor/            本地外部依赖（不提交二进制）
runtime/           本地运行数据（不提交）
```

## 文档与许可

- [依赖和第三方资源](docs/DEPENDENCIES.md) · [构建与打包](docs/BUILDING.md)
- [架构与安全边界](docs/ARCHITECTURE.md) · [发布检查清单](docs/RELEASING.md)
- [参与贡献](CONTRIBUTING.md) · [安全与隐私](SECURITY.md) · [变更摘要](CHANGELOG.md)

本项目自有代码采用 [MIT](LICENSE)：允许使用、修改和商用，须保留版权与许可声明，软件按原样提供。第三方代码、模型、驱动、音乐和歌词不因本项目而改用 MIT，详见 [第三方声明](THIRD_PARTY_NOTICES.md)。公开发行前仍需确认原始代码权利来源；来源未确认的旧 Softcam DLL 已排除，不应随包发布。项目名称不代表与任何手机厂商或音乐软件存在合作关系。
