# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Crear PDF desde Word, Excel y PowerPoint, y escanear páginas, sin dependencias nuevas ni conexión:
- Documentos de Office: con Microsoft Office instalado (automatización COM vía PowerShell) o, si no,
  con LibreOffice (gratuito) en modo sin ventana. PDFRapid no incluye ninguno de los dos.
- Escáner: el diálogo de escaneo de Windows (WIA), que funciona con cualquier escáner con controlador WIA.
Las rutas se pasan por variables de entorno para no tener problemas con comillas o espacios."""
import glob
import os
import shutil
import subprocess
import tempfile

KINDS = {   # aplicación de Office → extensiones que abre
    "Word": (".doc", ".docx", ".docm", ".dot", ".dotx", ".rtf", ".odt", ".txt"),
    "Excel": (".xls", ".xlsx", ".xlsm", ".xlsb", ".ods", ".csv"),
    "PowerPoint": (".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".odp"),
}
EXTS = tuple(e for v in KINDS.values() for e in v)

# AutomationSecurity = 3 (msoAutomationSecurityForceDisable): al automatizar Office las macros del documento
# se habilitarían por defecto; un .docm/.xlsm malicioso podría ejecutarlas al convertirlo.
_PS = {
    "Word": r"""$a = New-Object -ComObject Word.Application; $a.Visible = $false; $a.DisplayAlerts = 0; $a.AutomationSecurity = 3
try { $d = $a.Documents.Open($env:PDFRAPID_SRC, $false, $true, $false); $d.ExportAsFixedFormat($env:PDFRAPID_DST, 17); $d.Close(0) }
finally { $a.Quit() }""",
    "Excel": r"""$a = New-Object -ComObject Excel.Application; $a.Visible = $false; $a.DisplayAlerts = $false; $a.AutomationSecurity = 3
try {
  if ($env:PDFRAPID_SRC.ToLower().EndsWith(".csv")) {   # CSV con comas aunque Windows use «;» como separador
    $t = [IO.Path]::Combine([IO.Path]::GetTempPath(), [guid]::NewGuid().ToString() + ".txt")   # con .csv Excel ignora las opciones
    Copy-Item -LiteralPath $env:PDFRAPID_SRC $t
    $a.Workbooks.OpenText($t, 65001, 1, 1, 1, $false, $false, $false, $true); $w = $a.ActiveWorkbook
    $null = $w.ActiveSheet.UsedRange.Columns.AutoFit()
  } else { $w = $a.Workbooks.Open($env:PDFRAPID_SRC, 0, $true) }
  $w.ExportAsFixedFormat(0, $env:PDFRAPID_DST); $w.Close($false)
  if ($t) { Remove-Item -LiteralPath $t -ErrorAction SilentlyContinue } }
finally { $a.Quit() }""",
    "PowerPoint": r"""$a = New-Object -ComObject PowerPoint.Application; $a.AutomationSecurity = 3
try { $p = $a.Presentations.Open($env:PDFRAPID_SRC, -1, 0, 0); $p.SaveAs($env:PDFRAPID_DST, 32); $p.Close() }
finally { $a.Quit() }""",
}

_SCAN = r"""$m = New-Object -ComObject WIA.DeviceManager
$n = @($m.DeviceInfos | Where-Object { $_.Type -eq 1 }).Count
if ($n -eq 0) { exit 4 }
try {
  $d = New-Object -ComObject WIA.CommonDialog
  $i = $d.ShowAcquireImage(1, 0, 0, '{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}', $false, $true, $false)
  if ($i -eq $null) { exit 3 }
  $null = $i.SaveFile($env:PDFRAPID_DST)
} catch {
  $h = '{0:X8}' -f $_.Exception.HResult
  if ($h -eq '80210064') { exit 3 }
  [Console]::Error.WriteLine("WIA 0x$h " + $_.Exception.Message); exit 5
}"""          # tipo 1 = escáner; formato PNG; con el diálogo de opciones del escáner


class ConverterMissing(Exception):
    """No hay Office ni LibreOffice para convertir ese tipo de archivo."""


class ScanError(Exception):
    pass


NO_SCANNER = "No se encontró ningún escáner. Conéctalo, enciéndelo y comprueba que Windows lo reconoce."


def kind_of(path: str):
    ext = os.path.splitext(path)[1].lower()
    return next((k for k, exts in KINDS.items() if ext in exts), None)


def office_installed(app: str) -> bool:
    """¿Está instalada la aplicación de Microsoft Office (registrada para automatización)?"""
    if os.name != "nt": return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{app}.Application\CLSID"): return True
    except OSError:
        return False


def find_libreoffice():
    """Ruta de soffice.exe si LibreOffice está instalado."""
    found = shutil.which("soffice")
    if found: return found
    roots = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    for r in filter(None, roots):
        for p in glob.glob(os.path.join(r, "LibreOffice*", "program", "soffice.exe")) + \
                 glob.glob(os.path.join(r, "Programs", "LibreOffice*", "program", "soffice.exe")):
            return p
    return None


def available() -> dict:
    """Qué puede convertir este equipo: {"Word": "Microsoft Office" | "LibreOffice" | None, …}."""
    lo = find_libreoffice()
    return {k: "Microsoft Office" if office_installed(k) else "LibreOffice" if lo else None for k in KINDS}


def _ps(script: str, env_extra: dict, timeout: int):
    env = dict(os.environ, **env_extra)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # salida en UTF-8 (acentos correctos) y, si algo falla, solo el mensaje del error (sin el volcado de PowerShell)
    head = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\ntrap { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }\n"
    # sin «-ExecutionPolicy Bypass»: no afecta a -Command y los antivirus lo asocian a malware
    # ruta completa: con solo «powershell», Windows también busca en la carpeta actual (un powershell.exe falso
    # en Descargas, junto al PDF, se ejecutaría)
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return subprocess.run([exe, "-NoProfile", "-Command", head + script],  # nosec B603 - guion propio, rutas por entorno
                          env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=flags)


def _first_line(text: str) -> str:
    return next((l.strip() for l in (text or "").splitlines() if l.strip()), "")


BASIC = "conversión básica"


def basic_docx_to_pdf(src: str, dst: str):
    """Último recurso para .docx sin Office ni LibreOffice (o si no pueden abrirlo): texto, títulos, listas,
    tablas e imágenes; el diseño de página puede diferir del original."""
    import mammoth
    import pymupdf
    with open(src, "rb") as f:
        html = mammoth.convert_to_html(f).value
    css = ("body{font-family:sans-serif;font-size:11pt;line-height:1.35} h1{font-size:20pt} h2{font-size:15pt} "
           "h3{font-size:12.5pt} table{border-collapse:collapse;margin:4pt 0} td,th{border:0.5pt solid #888;padding:3pt} "
           "img{max-width:100%}")
    story = pymupdf.Story(html=html, user_css=css)
    page = pymupdf.paper_rect("a4"); where = page + (56, 56, -56, -56)
    w = pymupdf.DocumentWriter(dst); more = 1
    while more:
        dev = w.begin_page(page); more, _ = story.place(where); story.draw(dev); w.end_page()
    w.close()


def office_to_pdf(src: str, dst: str, timeout: int = 300) -> str:
    """Convierte `src` a PDF en `dst` y devuelve el método usado. Orden: Microsoft Office → LibreOffice →
    conversión básica (solo .docx). ConverterMissing si no hay ninguno; RuntimeError si todos fallan."""
    kind = kind_of(src)
    if not kind: raise ValueError(f"Tipo de archivo no admitido: {os.path.basename(src)}")
    src, dst = os.path.abspath(src), os.path.abspath(dst)
    if os.path.exists(dst): os.remove(dst)
    errors = []
    if office_installed(kind):
        r = _ps(_PS[kind], {"PDFRAPID_SRC": src, "PDFRAPID_DST": dst}, timeout)
        if r.returncode == 0 and os.path.exists(dst): return "Microsoft Office"
        errors.append(f"Microsoft {kind}: " + (_first_line(r.stderr) or _first_line(r.stdout) or "no pudo convertir el archivo"))
    lo = find_libreoffice()
    if lo:
        with tempfile.TemporaryDirectory() as out:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            # perfil propio: funciona aunque el usuario tenga LibreOffice abierto
            prof = "file:///" + os.path.join(out, "perfil").replace("\\", "/")
            r = subprocess.run([lo, f"-env:UserInstallation={prof}", "--headless", "--norestore", "--convert-to", "pdf",
                                "--outdir", out, src], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout, creationflags=flags)
            made = os.path.join(out, os.path.splitext(os.path.basename(src))[0] + ".pdf")
            if os.path.exists(made):
                shutil.move(made, dst); return "LibreOffice"
            errors.append("LibreOffice: " + (_first_line(r.stderr) or _first_line(r.stdout) or "no pudo convertir el archivo"))
    if src.lower().endswith(".docx"):
        try:
            basic_docx_to_pdf(src, dst); return BASIC
        except Exception as e:
            errors.append(f"Conversión básica: {e}")
    if not errors: raise ConverterMissing(kind)
    raise RuntimeError("\n".join(errors))


def scan_page(dst_png: str, timeout: int = 900):
    """Escanea con la ventana del fabricante por TWAIN (p. ej. Epson Scan 2), que puede devolver varias páginas
    de una vez (alimentador): lista de archivos. Si no hay escáner TWAIN, usa el diálogo de Windows (WIA) y
    guarda la página en `dst_png` (True). False si se canceló. Llamar desde un hilo de trabajo."""
    if os.name != "nt": raise ScanError("El escaneo solo está disponible en Windows.")
    if os.path.exists(dst_png): os.remove(dst_png)
    pages = scan_twain(dst_png)
    if pages is not None: return pages
    r = _ps(_SCAN, {"PDFRAPID_DST": os.path.abspath(dst_png)}, timeout)
    if r.returncode == 0 and os.path.exists(dst_png): return True
    err = (r.stderr or "") + (r.stdout or "")
    if r.returncode == 3: return False                           # cancelado por el usuario
    if r.returncode == 4 or "80210015" in err: raise ScanError(NO_SCANNER)
    raise ScanError(err.strip()[:600] or "No se pudo escanear.")


def scan_twain(dst_png: str):
    """Escaneo TWAIN (core/twain_scan.py): lista de páginas, False si se canceló, None si no hay escáner TWAIN."""
    from core import twain_scan
    try:
        return twain_scan.scan(dst_png)
    except twain_scan.TwainError as e:
        raise ScanError(str(e))
