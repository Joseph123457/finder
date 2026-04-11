# Tesseract 자동 다운로드 + 한국어 언어팩 설치 스크립트.
# Why: 별도 사용자 조작 없이 PyInstaller 빌드에 번들 가능한 Tesseract 트리를
#       resources/tesseract/ 에 만들어둔다. 한 번 실행하면 충분.
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts\fetch_tesseract.ps1

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest 가 빠르도록.

# Why curl: PowerShell 5.1의 Invoke-WebRequest는 일부 GitHub TLS 설정에서 중단되는
# 사례가 있어, 더 안정적인 curl.exe(Windows 10 1803+ 기본 포함)를 사용한다.
function Download-File {
    param([string]$Url, [string]$Out)
    Write-Host "GET $Url"
    & curl.exe -L --fail --retry 3 --retry-delay 2 -o $Out $Url
    if ($LASTEXITCODE -ne 0) {
        throw "curl failed ($LASTEXITCODE) for $Url"
    }
}

$Root = Split-Path -Parent $PSScriptRoot
$Resources = Join-Path $Root "resources\tesseract"
$Tmp = Join-Path $env:TEMP "jeanfinder_tess"

if (-not (Test-Path $Tmp)) { New-Item -ItemType Directory -Path $Tmp | Out-Null }
if (Test-Path $Resources) { Remove-Item -Recurse -Force $Resources }
New-Item -ItemType Directory -Path $Resources | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Resources "tessdata") | Out-Null

# 1) UB Mannheim Tesseract 5.x 인스톨러 다운로드 (영문 OCR 포함, ~70MB)
$InstallerUrl = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
$InstallerPath = Join-Path $Tmp "tesseract-setup.exe"

if (-not (Test-Path $InstallerPath)) {
    Download-File $InstallerUrl $InstallerPath
}

# 2) silent install. UB Mannheim 인스톨러는 Inno Setup 기반이라 /SILENT /DIR 사용 가능.
#    설치 위치는 사용자 폴더로 지정해 admin 권한이 없어도 동작.
$InstallDir = Join-Path $Tmp "tesseract"
if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
Write-Host "Silent installing to $InstallDir ..."
Start-Process -FilePath $InstallerPath `
    -ArgumentList @("/SP-", "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$InstallDir") `
    -Wait

if (-not (Test-Path (Join-Path $InstallDir "tesseract.exe"))) {
    throw "Tesseract install failed: tesseract.exe not found in $InstallDir"
}

# 3) 한국어 언어팩 다운로드 (tessdata_fast 사용 → 속도/정확도 균형, ~14MB)
$KorUrl = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/kor.traineddata"
$KorPath = Join-Path $InstallDir "tessdata\kor.traineddata"
Download-File $KorUrl $KorPath

# 4) 영문 traineddata도 fast 로 교체 (기본은 정확도 best 라 OCR 속도가 매우 느리다)
$EngUrl = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata"
$EngPath = Join-Path $InstallDir "tessdata\eng.traineddata"
Download-File $EngUrl $EngPath

# 5) resources/tesseract/ 로 필요한 파일만 복사.
#    번들 크기를 줄이려고 doc/ 등은 건너뛴다.
Write-Host "Copying binaries to $Resources ..."
$KeepFiles = @("tesseract.exe")
$KeepDlls = Get-ChildItem -Path $InstallDir -Filter "*.dll" -File
foreach ($f in $KeepFiles) {
    Copy-Item (Join-Path $InstallDir $f) $Resources -Force
}
foreach ($dll in $KeepDlls) {
    Copy-Item $dll.FullName $Resources -Force
}

# tessdata: kor / eng + tesseract가 요구하는 osd.traineddata 만 보존
$TessSrc = Join-Path $InstallDir "tessdata"
$TessDst = Join-Path $Resources "tessdata"
foreach ($name in @("kor.traineddata", "eng.traineddata", "osd.traineddata")) {
    $src = Join-Path $TessSrc $name
    if (Test-Path $src) {
        Copy-Item $src $TessDst -Force
    }
}
# configs/ 폴더가 있어야 일부 page-segmentation 모드가 동작
$ConfigSrc = Join-Path $TessSrc "configs"
if (Test-Path $ConfigSrc) {
    Copy-Item $ConfigSrc $TessDst -Recurse -Force
}
$TessConfigSrc = Join-Path $TessSrc "tessconfigs"
if (Test-Path $TessConfigSrc) {
    Copy-Item $TessConfigSrc $TessDst -Recurse -Force
}

Write-Host ""
Write-Host "=== resources\tesseract\ contents ==="
Get-ChildItem -Recurse $Resources | Select-Object FullName, Length | Format-Table -AutoSize
$Total = (Get-ChildItem -Recurse $Resources -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("Total: {0:N1} MB" -f ($Total / 1MB))

Write-Host ""
Write-Host "DONE. Now rebuild with: pyinstaller build.spec --noconfirm --clean"
