param([Parameter(Mandatory=$true)][string]$Address, [switch]$Elevated, [switch]$Remove)
$ErrorActionPreference='Stop'
$ruleName='PhoneBridge-TLS-27187'
$parsedAddress=$null
if(-not [Net.IPAddress]::TryParse($Address,[ref]$parsedAddress) -or $parsedAddress.AddressFamily -ne 'InterNetwork') { throw 'A local IPv4 address is required.' }
$taskInterface=Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -EQ $Address | Select-Object -First 1
if(-not $taskInterface) { throw 'Address is not assigned to this computer.' }
if($taskInterface.PrefixLength -lt 16){throw 'Refusing an overly broad local network scope.'}
if($Address -notmatch '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)') { throw 'Only a private LAN interface is supported.' }
$admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if(-not $admin){
    if($Elevated){throw 'Administrator approval required.'}
    $arguments=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Address',$Address,'-Elevated')
    if($Remove){$arguments+='-Remove'}
    Start-Process -FilePath "$env:SystemRoot/System32/WindowsPowerShell/v1.0/powershell.exe" -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden
    'Requested administrator approval for the scoped PhoneBridge firewall rule.'
    exit
}
if($Remove){Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule; 'Removed PhoneBridge TLS rule.';exit}
# Resolve the actual host process, not a venv launcher or all Python executables.
$connection=Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -State Listen | Select-Object -First 1
if(-not $connection){throw 'Start PhoneBridge first.'}
$program=(Get-Process -Id $connection.OwningProcess).Path
if([IO.Path]::GetFileName($program) -notin @('python.exe','pythonw.exe')){throw 'Unexpected PhoneBridge host executable.'}
# Refuse silently replacing unrelated rules. Remove requires the explicit switch above.
$existing=Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if($existing){throw 'PhoneBridge rule already exists; inspect it before changing the network scope.'}
New-NetFirewallRule -Name $ruleName -DisplayName 'PhoneBridge TLS (selected LAN only)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 27187 -LocalAddress $Address -RemoteAddress "$Address/$($taskInterface.PrefixLength)" -Program $program -Profile Any | Out-Null
'Created PhoneBridge-only TCP 27187 rule on the selected private LAN address; no other ports or firewall settings changed.'
