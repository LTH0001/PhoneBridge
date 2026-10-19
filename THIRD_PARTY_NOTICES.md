# 来源与第三方组件

0.8.0 离线中文语音输入使用 [Vosk API 0.3.45](https://github.com/alphacep/vosk-api) 及 [vosk-model-small-cn-0.22](https://alphacephei.com/vosk/models)，Apache-2.0。模型来源、下载摘要及许可保存在 `vendor/vosk-model-small-cn-0.22`；默认手机录音仅发送至用户自己的电脑识别，不调用云端语音服务。Vosk wheel 内的原生组件及依赖许可在开发包中一并保留，公开分发前仍需完整复核其原生依赖。

1. Android App 初始 Java 源码与 PB01 协议来自作者提供的既有工程，在此基础上修复生命周期、权限、H.264 SPS/PPS、传感器多维值与独立采集线程。公开发布前须由作者确认既有工程的权利来源；本说明不以文件位置推断版权归属。
2. [Genymobile/scrcpy](https://github.com/Genymobile/scrcpy)：使用官方 4.1 Windows 成品作为独立屏幕控制进程；Apache-2.0，许可附在 `vendor/scrcpy/LICENSE.txt`。随包的 ADB、FFmpeg、SDL 等各有自己的许可；发布整包前需逐项保留对应声明。
3. [tshino/softcam](https://github.com/tshino/softcam)：参考公开 Sender API（BGR24、scCreateCamera/scSendFrame/scDeleteCamera）与 DirectShow 注册机制；上游源码 MIT，开发参考检出位于 `vendor/softcam-source`。当前运行的 DLL 来自用户原工程、名称为 AWC Virtual Cam，尚未确认该修改版本的对应源码。原工程的 Android-Webcam-Project 参考仓库主体为 GPL-3.0；本次没有复制其 Rust/JS 主体代码。当前 DLL 不纳入 Git；公开分发前应用有可核对源码和构建记录的 Softcam 版本替换，不能直接把此修改二进制断言为无条件 MIT。
4. [UmerCodez/SensorServer](https://github.com/UmerCodez/SensorServer)：参考按类型订阅、多客户端向电脑提供原始传感器数据的设计。没有复制其源码；PhoneBridge 使用自己的二进制头与 JSON 事件载荷。
5. [VCamdroid](https://github.com/darusc/VCamdroid)、[Nexora](https://github.com/akashlenvo/Nexora)、[VoiceMic](https://github.com/Andrey917393dj/voicemic)：调研了虚拟设备输出架构，没有直接合并源码。公开说明的功能和发行版成熟程度与实测能力分开对待；本次选择复用可验证的原工程模块。
6. PyAV、NumPy、sounddevice、Pillow、OpenCV：通过 pip 安装，版本固定在 requirements.txt，各组件的 LICENSE 随安装包保留。PyAV/OpenCV 的 FFmpeg 构建配置与相关许可证需要在分发时再次核对。
7. [VB-CABLE](https://vb-audio.com/Cable/)：VB-Audio 的 Donationware 商用二进制前置依赖。官网签名包位于本机 vendor/vb-cable；本工程提供的是用户自主安装入口，不与产品自动安装流程集成。官方来源与 Donationware 信息必须保留；打包分发前按照当前官网许可处理。
8. [VirtualDrivers/Virtual-Display-Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver)：已集成签名 UMDF/IddCx 显示后端，MIT。官方源代码完整检出位于 `vendor/vdd-source`；25.7.23 官方签名发行包位于 `vendor/vdd-package`。发行 ZIP SHA256 为 `a701f2272e9fcf382849b24f913c6dd07597b3b1116525f2e90182f019609154`，已与 GitHub 发行页核对。DevCon 为发行包附带的 Microsoft 签名工具，用于安装项目单个 root-enumerated 显示设备。仅安装显示后端，没有安装该发行包中的虚拟音频组件；未导入第三方证书到可信根，也未修改 Secure Boot/测试签名。官方配置示例仅作为 schema 参考；本项目提供了独立的配置与管理脚本。

本项目自有代码采用根目录 LICENSE 中的 MIT 许可证；该许可不覆盖第三方代码、库、驱动、模型及媒体内容，也不会改变其原有许可证。原始代码权利来源和各二进制的分发要求仍需在公开发布前复核，不承诺所有二进制可直接闭源分发。当前是本机开发与实测，尚未公开发布。

控制面板新增 psutil 7.2.2（BSD-3-Clause）和 PyWinRT 3.2.1（MIT）；许可随本机安装包保留。NVIDIA NVML 来自电脑既有 NVIDIA 驱动，PhoneBridge 只调用其查询 API，不复制/重新分发驱动或修改显卡设置。音乐控制调用 Windows 内置 SMTC，不复制 QQ 音乐的程序、音频、封面或歌词。

0.3 播放设备与系统音量通过 [Pycaw 20260927](https://github.com/AndreMiras/pycaw)（MIT）和 comtypes 1.4.17（MIT）调用 Windows Core Audio。端点切换使用 PolicyConfig ABI，是 Windows 未正式公开的接口；异常时报告错误并尽量恢复原角色，不保证未来系统版本不变。

原生摄像头架构参考 [microsoft/Windows-Camera VirtualCamera](https://github.com/microsoft/Windows-Camera/tree/master/Samples/VirtualCamera) 和 [smourier/VCamSample](https://github.com/smourier/VCamSample)（MIT）。参考仓库保留在 `vendor/mf-camera-reference`，提交 `58b6d4b0e0c2c97fdffd66d23e7c8da6b89f570d`。本项目的 `native/mf-camera` 是自己的 CPU 像素源、COM 生命周期和注册工具，不直接运行原示例的图案相机。Windows 11 ABI 来自 [Microsoft win32metadata](https://github.com/microsoft/win32metadata) 的 SDK 头文件，固定提交 `76c04c2021ef4a831a6f1e06d9566002d746139b`，mfvirtualcamera.h SHA256 `acf37cdd4bfea8fcf2b84adbdeb450351ee1211b0ed00f779f0acffc9dfdf2fc`。编译采用本机已有 MinGW-w64 UCRT/GCC；其运行库与例外条款应在正式分发前复核。

同步歌词可经用户确认调用 [LRCLIB](https://github.com/tranxuanthang/lrclib) 的公开查询 API，不合并其服务器代码，不向服务提交音频、账户或歌词投稿。歌词数据仍属于各自权利人，个人界面显示不意味着可以随软件分发歌词库；本项目不下载整库，也不把歌词写入对外文档。用户自己导入的 LRC 仅保存在本地运行目录。

CPU 温度使用 [LibreHardwareMonitor 0.9.6](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/tag/v0.9.6)，MPL-2.0，未修改其库；官方 ZIP SHA256 `086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001`。完整对应源码在本机 `vendor/lhm-source`（提交 `3d331e3370efb858411f19511373eff65a218701`）；库及其依赖的许可见该源码的 LICENSE/THIRD-PARTY-NOTICES.txt，以及 `vendor/temperature-licenses`。

[PawnIO 2.2.0](https://github.com/namazso/PawnIO.Setup/releases/tag/2.2.0) 是独立的官方签名驱动前置依赖，安装器 SHA256 `1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032`，签名主体 `namazso.eu`。只用官方签名版，不用 unrestricted 版。其驱动源码使用 GPL-2.0-or-later 并有附加链接例外，具体以 [官方 COPYING](https://github.com/namazso/PawnIO/blob/master/COPYING) 为准；本项目不修改驱动，仅经用户 UAC 确认安装。当前仍仅本机开发，正式打包分发前须复核全部依赖和驱动发行许可。

独立副屏 DPI 的 ABI 信息参考 [lihas/windows-DPI-scaling-sample](https://github.com/lihas/windows-DPI-scaling-sample) 的 DpiHelper（Unlicense，源码与许可保留在 `vendor/dpi-reference`）。PhoneBridge 使用自己的 ctypes 实现，仅允许调整项目的非主显示器，验证 Windows 返回范围，绝不修改全局自定义缩放。这部分使用未公开的 DisplayConfig 参数 -3/-4；不承诺未来 Windows 版本兼容，异常时拒绝应用。
## 0.6.0 无线配对依赖

- ZXing core 3.5.3，Apache-2.0：仅使用二维码核心解码库，不依赖已停止维护的 Barcode Scanner Android App。来源 https://github.com/zxing/zxing 与 Maven Central。二进制 `vendor/zxing/core-3.5.3.jar` SHA-256 `8d8064c1636fdaef7189dd9055c7d59950a8940a12f2293956446ec3c109fd82`；构建脚本校验摘要，LICENSE / NOTICE 保存在同目录，APK 分发应附带本项目第三方许可材料。
- Python cryptography 50.0.2，Apache-2.0 / BSD-3-Clause，生成短期本地 TLS 证书；qrcode 8.2，BSD，用于电脑端配对二维码。锁定版本见 requirements.txt，许可随依赖分发。

## 0.7.0 USB 外设依赖

- PyUSB 1.3.1（BSD-3-Clause）、libusb-package 1.0.30.0（Apache-2.0 包装，所带 libusb 为 LGPL-2.1-or-later）和 importlib_resources 7.1.0（Apache-2.0）。当前通过 requirements.txt 安装；若分发 Windows 成品，须附带各包许可及 libusb 对应源码获取/替换说明，不能将整个依赖链一概标为 BSD。
- USB 接口安装辅助程序使用 Windows 自带 SetupAPI / Newdev 与微软内置 WinUSB。当前本机维护脚本不重新分发微软驱动，也不代表通用设备驱动安装器已经完成。

本地 EXE 构建使用 PyInstaller 6.22.3（GPL-2.0-or-later 并有官方 bootloader 分发例外；具体以随包许可证为准）。构建脚本收集已安装 Python 分发包的许可文本与版本清单，不意味着许可证审计或对应源码提供义务已全部完成。当前只生成本机测试产物，不公开分发；未确认来源的旧 Softcam DLL 不进入 EXE 包，系统摄像头输出优先使用本项目原生 MF 后端。

