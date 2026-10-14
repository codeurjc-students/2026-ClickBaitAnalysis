"""#267 (2026-10-14) - Lo que tardó cada arranque del servidor en Claude Desktop.

Claude Desktop guarda, por cada servidor MCP, un registro con la hora de cada
mensaje del protocolo y lo que el servidor escribe por stderr. Este guion lo
lee y saca, por cada conexión:

- el saludo (`initialize`): cuánto tardó la respuesta, o si el cliente lo
  canceló por tiempo («Request timed out»), y a los cuántos segundos;
- el precalentado de #267 (`mcp.preheat`), si el servidor lo hizo, y a los
  cuántos segundos de lanzar el servidor terminó;
- cada petición del cliente después del saludo, con lo que tardó y a los
  cuántos segundos de lanzar el servidor llegó.

Los segundos «de lanzarlo» se cuentan desde que Desktop anota que inicia el
servidor (`Initializing server`): es lo más cercano a abrir Desktop que deja
el registro.

Es el guion de la regla de #267: con `PREHEAT_MODELS=true`, el servidor tiene
que aparecer conectado y el primer `analyze_headline` responder sin agotar el
tiempo de espera.

El registro estaba en `%APPDATA%\\Claude\\logs\\` hasta el 24 ago 2026, y desde
entonces en `%LOCALAPPDATA%\\Claude\\Logs\\`; con dos formatos de línea: JSON
entero hasta junio, y `method="…" id=N` después. Se leen los dos. Con Desktop
instalada como paquete (MSIX), el `%APPDATA%` que ve está virtualizado: fuera
de ella, el registro antiguo está en
`%LOCALAPPDATA%\\Packages\\Claude_<id>\\LocalCache\\Roaming\\Claude\\logs\\`.

Ejecutar desde la raíz, en WSL, con las rutas de Windows montadas:
    .venv/bin/python spikes/claude_desktop_registro.py \\
        /mnt/c/Users/<usuario>/AppData/Local/Claude/Logs/mcp-server-tfg-mcp-server.log \\
        [--desde 2026-10-14]
"""

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_LINEA = re.compile(r"^(\d{4}-\d\d-\d\dT[\d:.]+Z) \[[^\]]+\] \[(\w+)\] (.*)$")
_PETICION = re.compile(r'Message from client: method="([^"]+)" id=(\d+)')
_RESPUESTA = re.compile(r"Message from server: id=(\d+) (result|error)")
_JSON_CLIENTE = re.compile(r"Message from client: (\{.*\}) \{ metadata")
_JSON_SERVIDOR = re.compile(r"Message from server: (\{.*\}) \{ metadata")
_CANCELADA = re.compile(r'"?requestId"?[:=]\s*(\d+).*?timed out', re.IGNORECASE)
# El formato nuevo anota la cancelación sin sus parámetros: no dice de qué
# petición es ni por qué. Se le atribuye a la más antigua sin respuesta.
_CANCELADA_SIN_ID = re.compile(r'Message from client: method="notifications/cancelled"')
_PRECALENTADO = re.compile(r"mcp\.preheat.*?total_s=([\d.]+)")
_HORA_DEL_SERVIDOR = re.compile(r"^(\d{4}-\d\d-\d\dT[\d:.]+Z)")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
# Delante de cada línea de Desktop: la hora y dos corchetes (servidor y nivel).
# Las del servidor (structlog) llevan uno solo, y no parten.
_MARCA_DE_DESKTOP = re.compile(r"(?=\d{4}-\d\d-\d\dT[\d:.]+Z \[[^\]]+\] \[\w+\] )")


@dataclass
class Peticion:
    metodo: str
    enviada: datetime
    segundos: float | None = None
    cancelada: bool = False


@dataclass
class Conexion:
    inicio: datetime
    peticiones: dict[int, Peticion] = field(default_factory=dict)
    # Desktop puede lanzar el servidor más de una vez por conexión (para el chat
    # y para las sesiones de Code y Cowork, medido en #267): cada proceso deja
    # su `server.start` y, si precalienta, su `mcp.preheat`.
    arranques: int = 0
    # Lo que tardó cada precalentado, y a los cuántos segundos de lanzar el
    # servidor terminó (None si la línea no trae su hora).
    precalentados_s: list[tuple[float, float | None]] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)


def _hora(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def _leer(ruta: Path) -> list[Conexion]:
    conexiones: list[Conexion] = []
    actual: Conexion | None = None
    # Desktop escribe el registro mientras está abierta: se lee lo que haya. Las
    # barras de progreso de `transformers` no terminan en salto de línea, y la
    # siguiente línea de Desktop queda pegada detrás: se parte por cada marca
    # de hora suya.
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    lineas = [
        trozo
        for fisica in texto.splitlines()
        for trozo in _MARCA_DE_DESKTOP.split(fisica)
        if trozo
    ]
    for linea in lineas:
        encontrada = _LINEA.match(linea)
        if not encontrada:
            # Lo que el servidor escribe por stderr llega tal cual, sin el
            # formato de Desktop: aquí están sus `server.start` y `mcp.preheat`.
            if actual:
                limpia = _ANSI.sub("", linea)
                if "server.start" in limpia:
                    actual.arranques += 1
                if precalentado := _PRECALENTADO.search(limpia):
                    hora_del_servidor = _HORA_DEL_SERVIDOR.match(limpia)
                    terminado = (
                        (_hora(hora_del_servidor.group(1)) - actual.inicio).total_seconds()
                        if hora_del_servidor
                        else None
                    )
                    actual.precalentados_s.append((float(precalentado.group(1)), terminado))
            continue
        hora, nivel, mensaje = _hora(encontrada[1]), encontrada[2], encontrada[3]

        if mensaje.startswith("Initializing server"):
            actual = Conexion(inicio=hora)
            conexiones.append(actual)
            continue
        if actual is None:
            continue

        if nivel == "error":
            actual.errores.append(f"{encontrada[1]} {mensaje[:120]}")

        if cancelada := _CANCELADA.search(mensaje):
            peticion = actual.peticiones.get(int(cancelada.group(1)))
            if peticion and peticion.segundos is None:
                peticion.segundos = (hora - peticion.enviada).total_seconds()
                peticion.cancelada = True
            continue
        if _CANCELADA_SIN_ID.search(mensaje):
            pendiente = next(
                (peticion for peticion in actual.peticiones.values() if peticion.segundos is None),
                None,
            )
            if pendiente:
                pendiente.segundos = (hora - pendiente.enviada).total_seconds()
                pendiente.cancelada = True
            continue

        if peticion_nueva := _PETICION.search(mensaje):
            metodo, identificador = peticion_nueva.group(1), int(peticion_nueva.group(2))
            actual.peticiones[identificador] = Peticion(metodo, hora)
            continue
        if json_cliente := _JSON_CLIENTE.search(mensaje):
            try:
                cuerpo = json.loads(json_cliente.group(1))
            except json.JSONDecodeError:
                continue
            if "id" in cuerpo and "method" in cuerpo:
                metodo = cuerpo["method"]
                if metodo == "tools/call":
                    metodo += f" {cuerpo.get('params', {}).get('name', '')}"
                actual.peticiones[int(cuerpo["id"])] = Peticion(metodo, hora)
            continue

        identificador = None
        if respuesta := _RESPUESTA.search(mensaje):
            identificador = int(respuesta.group(1))
        elif json_servidor := _JSON_SERVIDOR.search(mensaje):
            try:
                cuerpo = json.loads(json_servidor.group(1))
            except json.JSONDecodeError:
                continue
            if "id" in cuerpo and "method" not in cuerpo:
                identificador = int(cuerpo["id"])
        if identificador is not None:
            peticion = actual.peticiones.get(identificador)
            if peticion and peticion.segundos is None:
                peticion.segundos = (hora - peticion.enviada).total_seconds()

    return conexiones


def _describir(peticion: Peticion, inicio: datetime | None = None) -> str:
    llegada = (
        f" (llegó a los {(peticion.enviada - inicio).total_seconds():.0f} s de lanzarlo)"
        if inicio
        else ""
    )
    if peticion.segundos is None:
        return f"{peticion.metodo}: sin respuesta{llegada}"
    if peticion.cancelada:
        return f"{peticion.metodo}: CANCELADA a los {peticion.segundos:.1f} s{llegada}"
    return f"{peticion.metodo}: {peticion.segundos:.1f} s{llegada}"


def main() -> None:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("registros", nargs="+", type=Path)
    argumentos.add_argument("--desde", help="sólo las conexiones desde esta fecha (AAAA-MM-DD)")
    opciones = argumentos.parse_args()

    for ruta in opciones.registros:
        print(f"=== {ruta}")
        for conexion in _leer(ruta):
            if opciones.desde and conexion.inicio.date().isoformat() < opciones.desde:
                continue
            saludo = next(
                (peticion for peticion in conexion.peticiones.values() if peticion.metodo == "initialize"),
                None,
            )
            if saludo is None:
                continue
            precalentado = (
                ", precalentado "
                + ", ".join(
                    f"{segundos:.1f} s"
                    + (f" (terminó a los {terminado:.0f} s)" if terminado is not None else "")
                    for segundos, terminado in conexion.precalentados_s
                )
                if conexion.precalentados_s
                else ""
            )
            print(
                f"{conexion.inicio:%Y-%m-%d %H:%M:%S} UTC  {_describir(saludo)}"
                f"  [{conexion.arranques} procesos{precalentado}]"
            )
            for peticion in conexion.peticiones.values():
                if peticion is not saludo and peticion.metodo not in (
                    "tools/list",
                    "prompts/list",
                    "resources/list",
                    "resources/templates/list",
                ):
                    print(f"    {_describir(peticion, conexion.inicio)}")
            for error in conexion.errores:
                print(f"    error: {error}")


main()
