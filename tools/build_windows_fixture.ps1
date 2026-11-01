param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$output = (Resolve-Path -LiteralPath $OutputDirectory).Path
$install = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -prerelease -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
Import-Module "$install\Common7\Tools\Microsoft.VisualStudio.DevShell.dll"
Enter-VsDevShell -VsInstallPath $install -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'
& cl.exe /nologo /EHsc /std:c++20 "/Fe:$output\windows_fixture.exe" "/Fo:$output\windows_fixture.obj" "$PSScriptRoot\windows_fixture.cpp" /link windowsapp.lib shell32.lib ole32.lib
if ($LASTEXITCODE -ne 0) { throw 'Fixture compilation failed.' }
@'
import math, struct, sys, wave
with wave.open(sys.argv[1], 'wb') as f:
    f.setparams((1,2,44100,0,'NONE','not compressed'))
    f.writeframes(b''.join(struct.pack('<h',int(math.sin(i*2*math.pi*220/44100)*3000*(.5+.5*math.sin(i*2*math.pi*2/44100)))) for i in range(44100*32)))
'@ | python - "$output\tone.wav"
Write-Output "Fixture: $output\windows_fixture.exe file:///$($output.Replace('\','/'))/tone.wav"
