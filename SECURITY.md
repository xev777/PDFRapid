# Seguridad de PDFRapid / Security policy

_English below._

## Reportar una vulnerabilidad

Si encuentras un fallo de seguridad (por ejemplo, un PDF que hace que el programa ejecute código, abra algo sin
preguntar o filtre información), **no lo publiques**: repórtalo en privado desde [Avisos de seguridad de GitHub](https://github.com/xev777/PDFRapid/security/advisories/new) con:

- versión de PDFRapid (Ayuda → Acerca de) y de Windows;
- descripción del problema y pasos para reproducirlo;
- si puedes, el archivo de prueba (sin datos personales) y el registro `pdfrapid.log`.

**Plazos orientativos:**

| Paso | Plazo |
|---|---|
| Acuse de recibo | 3 días hábiles |
| Evaluación inicial y gravedad | 7 días |
| Corrección de fallos graves o que ya se estén aprovechando | lo antes posible, objetivo 30 días |
| Publicación del aviso | junto con la versión corregida, dando crédito a quien lo reportó si lo desea |

Si un fallo se está aprovechando activamente, se notificará además a las autoridades que exija la ley aplicable
(por ejemplo, el Reglamento (UE) 2024/2847 de ciberresiliencia, si el programa se comercializa en la UE).

## Versiones con soporte

| Versión | Actualizaciones de seguridad |
|---|---|
| 1.x (actual) | Sí (la versión 1.x más reciente) |
| Versiones beta anteriores a 1.0 | No: actualiza a la última 1.x |

Las correcciones de seguridad se publican siempre como una versión nueva completa (instalador y portable).

## Cómo se protege PDFRapid

- **Sin conexión:** no envía documentos ni datos. Solo el sello de tiempo y la firma de larga duración, si el
  usuario los activa, contactan servidores (envían un resumen del documento o consultan la vigencia del
  certificado). Las pruebas automáticas se ejecutan con la red bloqueada.
- **Contenido de los PDF:** no se ejecuta JavaScript del PDF; solo se abren enlaces `http`, `https` y `mailto`, y
  siempre preguntando; los adjuntos solo se abren si son documentos de tipos conocidos y se marcan como
  descargados de internet (Vista protegida de Office, SmartScreen); el resto solo se puede guardar.
- **Conversión con Office:** las macros se desactivan a la fuerza al automatizar Word, Excel y PowerPoint.
- **Firma:** las contraseñas y los PIN nunca se guardan; con token o certificado de Windows la clave privada no
  sale del dispositivo.
- **Cada compilación:** genera la lista de componentes (SBOM, CycloneDX `sbom.cdx.json`, incluida en el
  programa), revisa vulnerabilidades conocidas de esas versiones (pip-audit) y analiza el código (bandit). Un
  hallazgo detiene la compilación.

---

## Security policy (English)

**Reporting:** please don't disclose security issues publicly. Report it privately through [GitHub security advisories](https://github.com/xev777/PDFRapid/security/advisories/new) with the PDFRapid
version (Help → About), Windows version, steps to reproduce and, if possible, a test file without personal data
and `pdfrapid.log`. We aim to acknowledge within 3 business days, assess within 7 days and fix serious or
actively exploited issues as soon as possible (target: 30 days), publishing an advisory with the fixed release
and crediting the reporter if they wish.

**Supported versions:** the latest 1.x release receives security updates. Pre-1.0 betas are not supported.

**Protections:** offline by design (only the optional timestamp and long-term validation contact servers);
PDF JavaScript is not executed; only `http`, `https` and `mailto` links open, after confirmation; only known
document types open from attachments, with the Mark of the Web; Office macros are force-disabled during
conversion; passwords and PINs are never stored; every build produces a CycloneDX SBOM (`sbom.cdx.json`) and
fails on known-vulnerable dependencies (pip-audit) or code findings (bandit).
