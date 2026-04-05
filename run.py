"""
Punto de entrada para el servidor.
Fija ProactorEventLoop ANTES de que uvicorn cree el loop,
lo que permite a Playwright lanzar subprocesos en Windows.

Uso: python run.py
"""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="localhost",
        port=8000,
        reload=False,
    )
