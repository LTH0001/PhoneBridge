param(
    [string]$Toolchain = $env:PHONEBRIDGE_TOOLCHAIN,
    [string]$AndroidSdk = $env:ANDROID_SDK_ROOT,
    [string]$JavaHome = $env:JAVA_HOME,
    [string]$BuildToolsVersion = '35.0.0',
    [string]$Platform = 'android-34',
    [switch]$Install,
    [string]$Serial = ''
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'java-tools.ps1')
if (-not $AndroidSdk) { $AndroidSdk = $env:ANDROID_HOME }
$jdkPath = Find-PhoneBridgeJdk -JavaHome $JavaHome -Toolchain $Toolchain
if (-not $Toolchain -and -not $AndroidSdk) { throw 'Set ANDROID_SDK_ROOT, or explicitly pass -Toolchain for a custom toolchain.' }
# ASCII junctions let native Android tools open paths containing Chinese names.
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ('PhoneBridge-build-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
if ($Toolchain) { New-Item -ItemType Junction -Path (Join-Path $stage 'toolchain') -Target $Toolchain | Out-Null }
else { New-Item -ItemType Junction -Path (Join-Path $stage 'sdk') -Target $AndroidSdk | Out-Null }
New-Item -ItemType Junction -Path (Join-Path $stage 'jdk') -Target $jdkPath | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage 'app') | Out-Null
foreach ($name in @('src','res','AndroidManifest.xml')) {
    Copy-Item -LiteralPath (Join-Path $repo "android\app\$name") -Destination (Join-Path $stage 'app') -Recurse
}
$jdk = Get-Item -LiteralPath (Join-Path $stage 'jdk')
$env:JAVA_HOME = $jdk.FullName
$env:Path = "$($jdk.FullName)\bin;$env:Path"
$tools = @{}
foreach ($name in @('aapt2.exe','d8.bat','zipalign.exe','apksigner.bat','android.jar')) {
    if ($Toolchain) {
        $item = Get-ChildItem -LiteralPath (Join-Path $stage 'toolchain') -Recurse -File -Filter $name | Select-Object -First 1
    } else {
        $relative = if ($name -eq 'android.jar') { "platforms/$Platform/android.jar" } else { "build-tools/$BuildToolsVersion/$name" }
        $item = Get-Item -LiteralPath (Join-Path (Join-Path $stage 'sdk') $relative) -ErrorAction SilentlyContinue
    }
    if (-not $item) { throw "Missing Android build tool: $name" }
    $tools[$name] = $item.FullName
}
$app = Join-Path $stage 'app'
$build = Join-Path $app 'build'
New-Item -ItemType Directory -Path $build -Force | Out-Null
$keystore = Join-Path $build 'debug.keystore'
$originalKey = Join-Path $repo 'android\app\build\debug.keystore'
if (Test-Path -LiteralPath $originalKey) { Copy-Item -LiteralPath $originalKey -Destination $keystore }
if (-not (Test-Path -LiteralPath $keystore)) {
    & "$($jdk.FullName)\bin\keytool.exe" -genkeypair -keystore $keystore -alias phonebridge -keyalg RSA -keysize 2048 -validity 10000 -storepass phonebridge -keypass phonebridge -dname 'CN=PhoneBridge'
    if ($LASTEXITCODE) { throw 'Keystore generation failed' }
}
$res = Join-Path $build 'res.zip'
& $tools['aapt2.exe'] compile --dir (Join-Path $app 'res') -o $res
if ($LASTEXITCODE) { throw 'aapt2 compile failed' }
$base = Join-Path $build 'base.apk'
& $tools['aapt2.exe'] link -o $base -I $tools['android.jar'] --manifest (Join-Path $app 'AndroidManifest.xml') $res --auto-add-overlay
if ($LASTEXITCODE) { throw 'aapt2 link failed' }
$classes = Join-Path $build ('classes-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $classes | Out-Null
$sources = Get-ChildItem -LiteralPath (Join-Path $app 'src') -File -Filter '*.java' | ForEach-Object FullName
$qrSource=Join-Path $repo 'vendor\zxing\core-3.5.3.jar'
if ((Get-FileHash -LiteralPath $qrSource).Hash -ne '8D8064C1636FDAEF7189DD9055C7D59950A8940A12F2293956446EC3C109FD82') { throw 'ZXing core hash mismatch' }
$qrJar=Join-Path $build 'zxing.jar'
Copy-Item -LiteralPath $qrSource -Destination $qrJar
& "$($jdk.FullName)\bin\javac.exe" --release 8 -encoding UTF-8 -classpath "$($tools['android.jar']);$qrJar" -d $classes $sources
if ($LASTEXITCODE) { throw 'javac failed' }
$classJar = Join-Path $build 'classes.jar'
& "$($jdk.FullName)\bin\jar.exe" cf $classJar -C $classes .
if ($LASTEXITCODE) { throw 'jar failed' }
$dex = Join-Path $build 'dex'
New-Item -ItemType Directory -Path $dex -Force | Out-Null
& $tools['d8.bat'] --release --min-api 26 --lib $tools['android.jar'] --output $dex $classJar $qrJar
if ($LASTEXITCODE) { throw 'd8 failed' }
& "$($jdk.FullName)\bin\jar.exe" uf $base -C $dex classes.dex
if ($LASTEXITCODE) { throw 'dex packaging failed' }
$aligned = Join-Path $build 'aligned.apk'
& $tools['zipalign.exe'] -f 4 $base $aligned
if ($LASTEXITCODE) { throw 'zipalign failed' }
$apk = Join-Path $build 'phonebridge.apk'
& $tools['apksigner.bat'] sign --ks $keystore --ks-pass pass:phonebridge --key-pass pass:phonebridge --out $apk $aligned
if ($LASTEXITCODE) { throw 'APK signing failed' }
& $tools['apksigner.bat'] verify $apk
if ($LASTEXITCODE) { throw 'APK verification failed' }
$outputDir = Join-Path $repo 'android\app\build'
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
Copy-Item -LiteralPath $apk -Destination (Join-Path $outputDir 'phonebridge.apk') -Force
if (-not (Test-Path -LiteralPath $originalKey)) { Copy-Item -LiteralPath $keystore -Destination $originalKey }
Write-Output "Built: $(Join-Path $outputDir 'phonebridge.apk')"
if ($Install) {
    $adb = Join-Path $repo 'vendor\scrcpy\adb.exe'
    $adbArgs = @(); if ($Serial) { $adbArgs += @('-s', $Serial) }
    & $adb @adbArgs shell input keyevent KEYCODE_WAKEUP
    & $adb @adbArgs install --no-incremental -r $apk
    if ($LASTEXITCODE) { throw 'APK install failed' }
}
