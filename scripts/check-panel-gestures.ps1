param([string]$Toolchain=$env:PHONEBRIDGE_TOOLCHAIN, [string]$JavaHome=$env:JAVA_HOME)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'java-tools.ps1')
$jdk=Get-Item -LiteralPath (Find-PhoneBridgeJdk -JavaHome $JavaHome -Toolchain $Toolchain)
$gestureStage=Join-Path ([IO.Path]::GetTempPath()) ('PhoneBridge-gesture-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $gestureStage | Out-Null
& "$($jdk.FullName)/bin/javac.exe" --release 8 -encoding UTF-8 -d $gestureStage "$repo/android/app/src/PanelGesture.java" "$repo/tests/android/PanelGestureTest.java" "$repo/android/app/src/VoiceGesture.java" "$repo/tests/android/VoiceGestureTest.java" "$repo/android/app/src/NumberPadLayout.java" "$repo/tests/android/NumberPadLayoutTest.java" "$repo/android/app/src/PanelRoute.java" "$repo/tests/android/PanelRouteTest.java" "$repo/android/app/src/PanelPalette.java" "$repo/tests/android/PanelPaletteTest.java"
if($LASTEXITCODE){throw 'Gesture test compilation failed'}
& "$($jdk.FullName)/bin/java.exe" -cp $gestureStage com.phonebridge.app.PanelGestureTest
if($LASTEXITCODE){throw 'Gesture classification test failed'}
& "$($jdk.FullName)/bin/java.exe" -cp $gestureStage com.phonebridge.app.VoiceGestureTest
if($LASTEXITCODE){throw 'Voice gesture classification test failed'}
& "$($jdk.FullName)/bin/java.exe" -cp $gestureStage com.phonebridge.app.NumberPadLayoutTest
if($LASTEXITCODE){throw 'NumberPad layout test failed'}
& "$($jdk.FullName)/bin/java.exe" -cp $gestureStage com.phonebridge.app.PanelRouteTest
if($LASTEXITCODE){throw 'Panel route test failed'}
& "$($jdk.FullName)/bin/java.exe" -cp $gestureStage com.phonebridge.app.PanelPaletteTest
if($LASTEXITCODE){throw 'Panel palette test failed'}
