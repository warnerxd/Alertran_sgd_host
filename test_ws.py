#!/usr/bin/env python3
"""
test_ws.py — Validación del endpoint WebSocket de ALERTRAN SGD.

Uso:
  python test_ws.py <job_id>
  python test_ws.py <job_id> [--host wss://deprisahermes.ddns.net]

Si no se indica --host, usa wss://deprisahermes.ddns.net por defecto.

Flujo:
  1. Conecta a wss://<host>/ws/<job_id>
  2. Espera y muestra todos los mensajes hasta recibir
     finalizado | cancelado | error, o hasta timeout.
  3. Imprime un resumen del resultado.
"""

import argparse
import asyncio
import json
import sys
import time

try:
    import websockets
except ImportError:
    print("[ERROR] Instala websockets: pip install websockets")
    sys.exit(1)

DEFAULT_HOST = "wss://deprisahermes.ddns.net"
TIMEOUT_SEG  = 120   # tiempo máximo esperando eventos

# Tipos de mensaje que indican fin de job
TIPOS_FIN = {"finalizado", "cancelado", "error"}


def _color(code: str, txt: str) -> str:
    """ANSI color — se omite si la salida no es TTY."""
    if not sys.stdout.isatty():
        return txt
    return f"\033[{code}m{txt}\033[0m"


def _fmt(evt: dict) -> str:
    tipo = evt.get("type", "?")
    data = evt.get("data", "")

    if tipo == "snapshot":
        snap = data if isinstance(data, dict) else {}
        return (
            _color("36", "[snapshot]") +
            f" status={snap.get('status','?')}  "
            f"progress={snap.get('progress', 0)}%  "
            f"logs={len(snap.get('logs', []))}"
        )
    if tipo == "log":
        return _color("37", f"[log]    ") + f" {data}"
    if tipo == "progress":
        bar = "█" * int((data or 0) / 5) + "░" * (20 - int((data or 0) / 5))
        return _color("34", f"[progress]") + f" {bar} {data}%"
    if tipo == "estado":
        return _color("33", f"[estado] ") + f" {data}"
    if tipo == "guia_procesada":
        d = data if isinstance(data, dict) else {}
        return (
            _color("35", "[guia]   ") +
            f" {d.get('guia','')}  {d.get('status','')}  {d.get('resultado','')}"
        )
    if tipo == "tiempo":
        return _color("34", f"[tiempo] ") + f" {data}"
    if tipo == "finalizado":
        return _color("32", "[FINALIZADO] ") + json.dumps(data, ensure_ascii=False)[:200]
    if tipo == "cancelado":
        return _color("33", "[CANCELADO]  ") + json.dumps(data, ensure_ascii=False)[:200]
    if tipo == "error":
        return _color("31", "[ERROR]      ") + json.dumps(data, ensure_ascii=False)[:200]
    if tipo == "ping":
        return _color("90", "[ping]")
    return f"[{tipo}] {json.dumps(data, ensure_ascii=False)[:120]}"


async def escuchar(url: str):
    print(f"\n  Conectando a {_color('36', url)} …\n")
    t0 = time.monotonic()
    recibidos = 0
    tipo_fin  = None

    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            print(_color("32", "  Conexión establecida.\n"))

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_SEG)
                except asyncio.TimeoutError:
                    print(_color("31", f"\n  [TIMEOUT] No se recibió ningún mensaje en {TIMEOUT_SEG}s."))
                    return False

                recibidos += 1
                evt = json.loads(raw)
                print(f"  {_fmt(evt)}")

                if evt.get("type") in TIPOS_FIN:
                    tipo_fin = evt["type"]
                    break

    except OSError as exc:
        print(_color("31", f"\n  [CONEXIÓN FALLIDA] {exc}"))
        return False
    except websockets.exceptions.InvalidStatus as exc:
        print(_color("31", f"\n  [WS RECHAZADO] HTTP {exc.response.status_code}"))
        return False
    except Exception as exc:
        print(_color("31", f"\n  [ERROR INESPERADO] {type(exc).__name__}: {exc}"))
        return False

    elapsed = time.monotonic() - t0
    print(
        f"\n  {'─'*55}\n"
        f"  Mensajes recibidos : {recibidos}\n"
        f"  Tiempo transcurrido: {elapsed:.1f}s\n"
        f"  Resultado final    : {_color('32' if tipo_fin == 'finalizado' else '33', tipo_fin or 'desconocido')}\n"
    )
    return tipo_fin == "finalizado"


def main():
    parser = argparse.ArgumentParser(
        description="Valida el WebSocket de ALERTRAN SGD contra un job_id real."
    )
    parser.add_argument("job_id", help="ID del job activo (UUID)")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Base WSS del servidor (default: {DEFAULT_HOST})",
    )
    args = parser.parse_args()

    url = f"{args.host.rstrip('/')}/ws/{args.job_id}"
    ok  = asyncio.run(escuchar(url))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
