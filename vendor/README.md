# 本地依赖目录

此目录仅提交本说明。二进制、模型、驱动和参考仓库不加入 Git；请见 [依赖清单](../docs/DEPENDENCIES.md) 与 [第三方声明](../THIRD_PARTY_NOTICES.md)。

- `scrcpy/`：完整官方 Windows 包，包含 adb 与 scrcpy。
- `zxing/core-3.5.3.jar`：Android 二维码解码依赖，由固定摘要下载脚本获取。
- `vosk-model-small-cn-0.22/`：可选离线中文语音模型，解压后保留原目录名。
- `vdd-package/`、`vdd-source/`：可选虚拟显示驱动与许可/对应源码。
- `librehardwaremonitor/`、`temperature-licenses/`：可选温度采集与依赖许可。
- `mf-camera-reference/`、`mfvirtualcamera.h`：原生摄像头参考许可与 SDK 头文件。

不复制旧工程或未知 DLL。旧 `softcam.dll` 来源未完成核对，不允许进入公开源码/发行包。外部下载不代表自动获得重新分发许可，发布成品时须附上相应许可与必要的对应源码材料。
