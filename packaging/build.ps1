# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
# Compila PDFRapid (.exe en carpeta), la versión portable (.zip) y, si Inno Setup 6 está instalado, el instalador.
# Uso (desde la raíz del proyecto): powershell -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$ver = "1.0.0"
# Python del proyecto (venv) o, en GitHub Actions, el del sistema.
$py = if (Test-Path "$root\venv\Scripts\python.exe") { "$root\venv\Scripts\python" } else { "python" }

# Seguridad antes de compilar (ver SECURITY.md): lista de componentes (SBOM) de lo que lleva el instalador,
# revisión de vulnerabilidades conocidas de esas versiones (pip-audit, usa internet) y análisis del código (bandit).
# Un hallazgo detiene la compilación; $env:PDFRAPID_SKIP_AUDIT = "1" la omite (p. ej. sin internet).
New-Item -ItemType Directory -Force "build" | Out-Null
& $py packaging\sbom.py build\sbom.cdx.json build\sbom-reqs.txt $ver
if ($LASTEXITCODE -ne 0) { throw "No se pudo generar la lista de componentes (SBOM)" }
if ($env:PDFRAPID_SKIP_AUDIT -ne "1") {
    & $py -m pip_audit -r build\sbom-reqs.txt --no-deps --disable-pip --progress-spinner off
    if ($LASTEXITCODE -ne 0) { throw "pip-audit: hay dependencias con vulnerabilidades conocidas (actualízalas) o no hubo conexión" }
    & $py -m bandit -q -r core ui dialogs models utils main.py pdfgm_merge.py -ll
    if ($LASTEXITCODE -ne 0) { throw "bandit: revisa los hallazgos de seguridad del código" }
} else { Write-Host "AVISO: revisión de vulnerabilidades omitida (PDFRAPID_SKIP_AUDIT=1)" }

& $py -m PyInstaller packaging\pdfrapid.spec --noconfirm --distpath build\dist --workpath build\work
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló" }
Copy-Item build\sbom.cdx.json "build\dist\PDFRapid\sbom.cdx.json"; Copy-Item SECURITY.md "build\dist\PDFRapid\SECURITY.md"
& $py -m core.guide "build\dist\PDFRapid\guia"     # guía de usuario en PDF (es/en), Ayuda → Guía de usuario
if ($LASTEXITCODE -ne 0) { throw "No se pudo generar la guía de usuario" }

function Sign-File($file) {
    if (-not $env:PDFRAPID_SIGN_CERT) { return }
    $tool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.DirectoryName -like "*\x64" } | Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $tool) { throw "signtool.exe no encontrado: instala el Windows SDK (componente 'Signing Tools')" }
    $tsa = if ($env:PDFRAPID_SIGN_TSA) { $env:PDFRAPID_SIGN_TSA } else { "http://time.certum.pl" }
    & $tool.FullName sign /n $env:PDFRAPID_SIGN_CERT /fd sha256 /tr $tsa /td sha256 $file
    if ($LASTEXITCODE -ne 0) { throw "No se pudo firmar $file" }
    Write-Host "Firmado: $file"
}
Sign-File "build\dist\PDFRapid\PDFRapid.exe"
$iscc = @("$env:ProgramFiles (x86)\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc packaging\pdfrapid.iss
    Get-ChildItem "build\installer\*-setup.exe" | ForEach-Object { Sign-File $_.FullName }
    Write-Host "Instalador en build\installer"
}
else { Write-Host "Inno Setup 6 no encontrado: solo se generó build\dist\PDFRapid" }

# Portable: la misma carpeta + portable.txt (configuración y log en .\data, nada en el registro)
$tmp = "build\portable\PDFRapid"
if (Test-Path "build\portable") { Remove-Item -Recurse -Force "build\portable" }
New-Item -ItemType Directory -Force $tmp | Out-Null
Copy-Item -Recurse "build\dist\PDFRapid\*" $tmp
Copy-Item -Recurse "docs\legal" "$tmp\legal"; Copy-Item "LICENSE" "$tmp\LICENSE.txt"; Copy-Item "packaging\THIRD_PARTY_NOTICES.txt" $tmp
Set-Content -Encoding utf8 "$tmp\portable.txt" "PDFRapid portable: la configuracion y el log se guardan en la carpeta data. Borra este archivo para usar el modo normal."
New-Item -ItemType Directory -Force "build\installer" | Out-Null
& $py -c "import shutil; shutil.make_archive(r'build\installer\PDFRapid-$ver-portable', 'zip', r'build\portable', 'PDFRapid')"
Write-Host "Portable en build\installer\PDFRapid-$ver-portable.zip"
Copy-Item build\sbom.cdx.json "build\installer\PDFRapid-$ver-sbom.cdx.json"
Write-Host "Lista de componentes en build\installer\PDFRapid-$ver-sbom.cdx.json"
