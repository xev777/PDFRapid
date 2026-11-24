# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Fernando Erazo
"""Una sola instancia: los PDF abiertos desde el Explorador se agregan como pestañas a la ventana ya abierta.

La primera instancia toma un candado (QLockFile) y escucha en un canal local (QLocalServer).
Las siguientes envían sus rutas por ese canal y terminan. El canal es solo local (tubería con nombre
del usuario actual), sin red."""
import getpass
import hashlib
import json
import os
import time

from PyQt6.QtCore import QDir, QLockFile, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from core.logger import log


def _name(base):
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USERNAME", "")
    return f"{base}-{hashlib.sha256(user.encode('utf-8', 'replace')).hexdigest()[:12]}"


def pdf_args(argv):
    """Rutas absolutas de los PDF existentes entre los argumentos."""
    return [os.path.abspath(a) for a in argv if a.lower().endswith(".pdf") and os.path.isfile(a)]


def _allow_foreground():
    """Permite que la instancia principal pase al frente (Windows lo impide si no)."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)      # ASFW_ANY
        except Exception:
            pass


class SingleInstance(QObject):
    files = pyqtSignal(list)            # rutas recibidas (lista vacía = solo traer la ventana al frente)

    def __init__(self, base="PDFRapid", timeout=20.0):
        super().__init__()
        self.name = _name(base)
        self._lock = QLockFile(os.path.join(QDir.tempPath(), self.name + ".lock"))
        self._lock.setStaleLockTime(0)  # solo es viejo si el proceso que lo tomó ya no existe
        self._server = None
        self._timeout = timeout
        self.primary = False

    def start(self, paths):
        """True: esta es la instancia principal. False: las rutas se entregaron a otra y hay que salir."""
        end = time.monotonic() + self._timeout
        while True:
            if self._lock.tryLock(0):
                self._listen()
                self.primary = True
                return True
            if self._send(paths):
                return False
            if time.monotonic() > end:          # la otra no responde: abrir aparte antes que no abrir
                log.warning("Instancia principal sin respuesta; se abre una ventana aparte")
                return True
            time.sleep(0.1)                      # la principal está arrancando o cerrándose

    def _listen(self):
        QLocalServer.removeServer(self.name)    # restos de un cierre brusco
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._accept)
        if not self._server.listen(self.name):
            log.warning(f"No se pudo escuchar en {self.name}: {self._server.errorString()}")

    def _accept(self):
        while self._server and self._server.hasPendingConnections():
            s = self._server.nextPendingConnection()
            buf = bytearray()
            def leer(s=s, buf=buf):
                buf.extend(bytes(s.readAll()))
                if b"\n" not in buf or s.property("hecho"):
                    return                       # mensaje = JSON + salto de línea
                s.setProperty("hecho", True)
                try:
                    paths = [p for p in json.loads(bytes(buf).split(b"\n", 1)[0].decode("utf-8")) if isinstance(p, str)]
                except Exception:
                    paths = []
                s.write(b"ok\n"); s.flush()     # acuse: el emisor ya puede terminar
                s.disconnected.connect(s.deleteLater)
                self.files.emit(paths)
            s.readyRead.connect(leer)
            leer()

    def _send(self, paths):
        s = QLocalSocket()
        s.connectToServer(self.name)
        if not s.waitForConnected(500):
            return False
        _allow_foreground()
        s.write(json.dumps(paths).encode("utf-8") + b"\n")
        s.flush()
        s.waitForBytesWritten(2000)
        ok = s.waitForReadyRead(5000)          # esperar el acuse antes de cerrar el canal
        s.disconnectFromServer()
        if not ok:
            log.warning("La instancia principal no confirmó la recepción")
        return True

    def release(self):
        """Suelta el canal y el candado (antes de reiniciar la app, para que la nueva sea la principal)."""
        if self._server is not None:
            self._server.close(); self._server = None
        if self._lock.isLocked():
            self._lock.unlock()
        self.primary = False
