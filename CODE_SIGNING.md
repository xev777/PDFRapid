# Política de firma de código / Code signing policy

_English below._

Los instaladores y ejecutables de PDFRapid para Windows se firmarán con un certificado de firma de código.
Firma de código gratuita proporcionada por [SignPath.io](https://about.signpath.io/), certificado de
[SignPath Foundation](https://signpath.org/) _(solicitud en trámite; hasta su aprobación las versiones no están
firmadas y se pueden verificar con los SHA-256 publicados en cada versión)_.

## Qué se firma

Solo los archivos compilados por [GitHub Actions](.github/workflows/build.yml) a partir del código de este
repositorio: `PDFRapid.exe` y el instalador `PDFRapid-<versión>-setup.exe`. Nunca se firman binarios compilados
en un equipo personal ni archivos de terceros.

## Funciones

| Función | Personas |
|---|---|
| Autores y revisores (committers, reviewers) | [Fernando Erazo (@xev777)](https://github.com/xev777) |
| Aprobación de cada firma (approvers) | [Fernando Erazo (@xev777)](https://github.com/xev777) |

Todos los miembros usan autenticación en dos pasos en GitHub y SignPath. Las contribuciones externas se revisan
antes de incorporarse.

## Privacidad

Este programa no transfiere ninguna información a otros sistemas en red, salvo que la persona usuaria lo pida
expresamente (sello de tiempo o validación de larga duración al firmar, y abrir enlaces o la página de donación
tras confirmarlo). Ver la [política de privacidad](docs/legal/PRIVACIDAD.md).

---

## Code signing policy (English)

Windows installers and executables of PDFRapid will be signed with a code signing certificate.
Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by
[SignPath Foundation](https://signpath.org/) _(application pending; until approved, releases are unsigned and
can be verified with the SHA-256 hashes published with each release)_.

**What is signed:** only files built by [GitHub Actions](.github/workflows/build.yml) from this repository's
source: `PDFRapid.exe` and the `PDFRapid-<version>-setup.exe` installer. Binaries built on personal machines
and third-party files are never signed.

**Roles:** committers, reviewers and approvers: [Fernando Erazo (@xev777)](https://github.com/xev777). All
members use multi-factor authentication on GitHub and SignPath. External contributions are reviewed before
being merged.

**Privacy:** this program will not transfer any information to other networked systems unless specifically
requested by the user or the person installing or operating it (timestamp or long-term validation when
signing, and opening links or the donation page after confirmation). See the
[privacy policy](docs/legal/PRIVACIDAD.md).
