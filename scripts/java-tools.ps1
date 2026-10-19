# Shared explicit JDK resolution. Dot-source; does not install or change PATH.
function Find-PhoneBridgeJdk {
    param([string]$JavaHome = $env:JAVA_HOME, [string]$Toolchain = '')
    if ($JavaHome) {
        if (-not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin/javac.exe'))) { throw 'JAVA_HOME does not contain javac.exe' }
        return [IO.Path]::GetFullPath($JavaHome)
    }
    if ($Toolchain) {
        $candidates = @(Get-ChildItem -LiteralPath $Toolchain -Directory | Where-Object Name -Like 'jdk*')
        if ($candidates.Count -ne 1) { throw 'Provide -JavaHome explicitly when the toolchain has zero or multiple JDKs.' }
        return $candidates[0].FullName
    }
    $command = Get-Command javac.exe -ErrorAction SilentlyContinue
    if ($command) { return Split-Path -Parent (Split-Path -Parent $command.Source) }
    throw 'Install JDK 17+ and set JAVA_HOME, or pass -JavaHome.'
}
