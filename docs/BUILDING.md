# 构建与验证

所有命令从仓库根目录执行。PowerShell 脚本不会自动绕过 Windows 或手机授权。先阅读 [依赖说明](DEPENDENCIES.md)。

## Windows 主程序

```powershell
powershell -NoProfile -File scripts/setup.ps1
.\start.ps1
```

`setup.ps1 -Python <python.exe>` 可指定 Python。脚本只建立虚拟环境和安装 Python 依赖，不寻找旧工程、不复制 DLL、不改驱动。可用如下命令启动无桌面界面的本地 API：

```powershell
.\.venv\Scripts\python.exe -m phonebridge --headless
```

## Android APK

安装 JDK 17+、Android SDK platforms/android-34 与 build-tools/35.0.0，设置 `JAVA_HOME`、`ANDROID_SDK_ROOT`（或 `ANDROID_HOME`）后：

```powershell
.\.venv\Scripts\python.exe scripts/fetch-dependencies.py zxing
powershell -NoProfile -File scripts/build-android.ps1
```

支持 `-JavaHome`、`-AndroidSdk`、`-BuildToolsVersion`、`-Platform` 显式指定版本/路径。旧式组合工具链仅在显式传 `-Toolchain <目录>` 或设置 `PHONEBRIDGE_TOOLCHAIN` 时使用，不再绑定开发者磁盘。组合目录需含单个 `jdk*` 目录及 Android 命令行工具；多版本环境应使用标准 SDK 路径。

输出 `android/app/build/phonebridge.apk`，默认不安装手机。确需 ADB 安装时加 `-Install -Serial <设备序列号>`，手机仍须自行确认；不要把真实序列号写入 Issue。

这是开发签名 APK。首次构建在忽略目录生成密钥，之后复用，避免破坏本机升级兼容。当前开发签名密码是公开的，不适合正式发布；正式发行前须另行实现私有发布签名流程并安全保存密钥。密钥不能提交 Git，CI 不持有本机密钥。构建使用临时目录和路径联接，失败时临时目录可能残留，勿随源码上传。

## 原生摄像头（可选）

```powershell
powershell -NoProfile -File scripts/build-mf-camera.ps1 -Compiler <g++.exe的完整路径>
```

推荐 MinGW-w64 UCRT；也可用 PATH 中的 `g++.exe` 或 `PHONEBRIDGE_CXX`。输出 `native/mf-camera/build/`。编译不等于系统注册，注册是单独需授权的操作。Windows 11 原生虚拟摄像头及各会议应用的兼容性需要实机验证。

## 回归测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
powershell -NoProfile -File scripts/check-panel-gestures.ps1
.\.venv\Scripts\python.exe scripts/audit-source.py
```

这组测试不主动切换声音、操作真实鼠标或替换驱动。`.github/workflows/ci.yml` 执行同类检查；CI 不下载模型、不连接手机、不构建发布签名 APK、不运行驱动安装。

## 源码导出与 Windows 开发包

```powershell
.\.venv\Scripts\python.exe scripts/package-source.py
```

导出经过白名单和基本隐私扫描的源码目录、ZIP、SHA-256 文件清单到 `dist/`。保留原项目所有本地资料，不直接提交或推送。导出不是专利、权利来源或全面密钥审计。

Windows EXE 是另一条可选构建链：先准备 APK、原生相机、scrcpy、显示驱动、模型和许可等资源，再安装 `requirements-build.txt`，运行 `scripts/build-windows.py`。脚本缺少资源就会停止，不会自动安装系统驱动。它生成开发免安装包而非正式签名安装器；公开分发须先完成 [发布检查](RELEASING.md)。

## 本轮整理的本地验证（2026-10-17）

### 0.8.12 单文件 EXE

运行 `scripts/build-windows.py --onefile` 可生成带嵌入 APK、模型、工具与许可材料的单个 Windows x64 EXE。首次启动会在临时目录解压，可能比目录版慢；偏好与令牌仍写入 `%LOCALAPPDATA%/PhoneBridge`，不是临时目录。可在软件内导出 APK。构建不会提交或发布 GitHub Release，也不生成可信发布签名。第三方资源分发审查与干净电脑实测要求不变，见 RELEASING.md。

- Windows x64 / Python 3.13：177 项 Python 测试通过；导出的不含 vendor 二进制的源码目录中再次通过，使用同一 Python 依赖环境，不冒称干净电脑安装验收。
- JDK 17：12 项面板手势、22 项语音手势、224 项数字区布局用例通过。
- Python 直接依赖与参考传递约束的 pip 全新解析模拟通过（`--dry-run --ignore-installed`），未改动现有环境。
- ZXing 从官方地址下载并核对 SHA-256 通过；公开源码扫描无发现，PowerShell 语法检查通过。
- APK 构建与签名校验通过：显式旧式工具链路径、标准 SDK 目录接口均验证；后者使用本机已有 Build Tools 34.0.0 / android-33 与 JDK 17，未实际下载默认示例的 35.0.0 / android-34。未向手机发起安装。
- GitHub CI 已配置但尚未在 GitHub 运行；Windows 正式发行包未在本轮重建，驱动/无线/AOA 未重新实机验收。
