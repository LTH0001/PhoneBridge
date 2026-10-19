# 架构与边界

Android App 负责权限、摄像头/麦克风/传感器采集、视频显示、触控与语音交互。Windows 主程序负责传输调度、解码/编码、系统输入与可选虚拟设备输出。

```text
Android App ← PB01 数据与控制 → Windows Bridge
                                  ├─ 本地 API / 桌面控制中心
                                  ├─ 视频、音频、传感器
                                  ├─ 桌面捕获与输入回传
                                  └─ 系统遥测、音乐控制、离线语音
```

- `core.py` 管理连接与功能生命周期；`proto.py` 定义 PB01。
- `transport.py`、`accessory.py`、`usb_setup.py`、`wireless.py` 负责各传输路径；当前推荐已授权 ADB。
- `mf_camera.py` 与原生 `native/mf-camera` 处理原生摄像头输出；其他媒体模块按名称分工。
- `phone.html` 为控制面板；`setup.html` 为网页安装/引导界面，和桌面程序共用受限接口，不是公开远程管理服务。
- `remote_input.py`、`music_window.py` 等处理受限系统输入和窗口操作；手机获得的是明确功能入口，不是无限制命令终端。
- `telemetry.py`、`performance.py`、`system_info.py` 等查询资源；温度依赖独立的可选系统采集器，不是修改硬件的超频工具。
- `speech.py` 使用本地 Vosk；歌词服务仅在用户同意后查询曲名/歌手，不发送音频或账户。

API 默认监听 `127.0.0.1:8765`。运行目录内的 API 令牌、无线配对材料、导入歌词等是私有数据，不要放入仓库。源码运行数据在项目目录；冻结 EXE 使用 `%LOCALAPPDATA%/PhoneBridge`。不要将 API 改为公网监听，也不要通过防火墙对公网放行。

手机权限由 Android 决定，首次授权和用户撤回不可绕过；Windows 注册摄像头、安装显示/传感器驱动各需独立确认。实验 AOA 只对已支持的 USB ID 尝试模式切换，设备不明确时停止，不应泛化为自动重装所有手机驱动。
