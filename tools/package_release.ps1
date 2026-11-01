param([string]$Version = '0.2.0', [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$output = (Resolve-Path -LiteralPath $OutputDirectory).Path
$windows = Join-Path $root 'companion\build\windows\x64\runner\Release'
$apk = Join-Path $root 'companion\build\app\outputs\flutter-apk\app-release.apk'
if (!(Test-Path "$windows\Afterglow.exe") -or !(Test-Path $apk)) { throw 'Build both release targets before packaging.' }
Copy-Item -LiteralPath "$root\LICENSE" -Destination "$windows\LICENSE.txt"
Copy-Item -LiteralPath "$root\companion\WINDOWS-README.txt" -Destination "$windows\README.txt"
$bundleFiles = Get-ChildItem -LiteralPath $windows | Where-Object { $_.Extension -ne '.exe' -or $_.Name -eq 'Afterglow.exe' }
Compress-Archive -Path $bundleFiles.FullName -DestinationPath "$output\afterglow-$Version-windows-x64.zip" -Force
Copy-Item -LiteralPath $apk -Destination "$output\afterglow-$Version-android.apk"
& git -C $root archive --format=tar.gz "--prefix=afterglow-$Version/" "--output=$output\afterglow-$Version-linux.tar.gz" HEAD
if ($LASTEXITCODE -ne 0) { throw 'Linux source archive failed.' }
Get-ChildItem -LiteralPath $output -File | Where-Object { $_.Name -match '\.(zip|apk|gz)$' } | Sort-Object Name | ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($_.Name)"
} | Set-Content -LiteralPath "$output\SHA256SUMS.txt" -Encoding utf8
Write-Output "Release files ready in $output"
