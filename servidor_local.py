#!/usr/bin/env python3
"""
Servidor local del tracker ONPE.

Levanta un hilo que consulta a la ONPE cada cierto intervalo y guarda el
historial en onpe_historial.json. El hilo principal sirve la pagina
(index.html) y un endpoint /api/datos con las series para dibujar en el
navegador.

Uso:
    pip install -r requirements.txt
    python servidor_local.py
    python servidor_local.py --intervalo 1
    python servidor_local.py --port 9000

Para una URL publica se usa un tunel de cloudflare:
    cloudflared tunnel run onpe
"""

import os
import json
import time
import argparse
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from onpe_tracker import (
    fetch_resumen,
    cargar_historial,
    guardar_historial,
    _filtrar_por_intervalo,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_estado = {"payload": {"tiempos": [], "series": {}, "candidatos": []}}
_lock = threading.Lock()

# Peru no usa horario de verano, siempre UTC-5
PERU_TZ = timezone(timedelta(hours=-5))


def _a_peru_iso(ts):
    # un timestamp naive se asume en hora local de la maquina y se pasa a
    # hora de Peru. el ISO lleva el huso (-05:00) para que la pagina muestre
    # hora de Peru sin importar desde donde se abra.
    return ts.astimezone(PERU_TZ).isoformat()


PALETA = ["#E63946", "#457B9D", "#2A9D8F", "#E9C46A", "#F4A261"]


def construir_payload(historial, intervalo):
    if intervalo:
        historial = _filtrar_por_intervalo(historial, intervalo)
    if not historial:
        return {"tiempos": [], "series": {}, "candidatos": []}

    nombres = []
    for e in historial:
        for c in e["candidatos"]:
            if c["nombre"] not in nombres:
                nombres.append(c["nombre"])

    tiempos = [_a_peru_iso(e["timestamp"]) for e in historial]
    series = {n: [] for n in nombres}
    for e in historial:
        got = {c["nombre"]: c["porcentaje"] for c in e["candidatos"]}
        for n in nombres:
            series[n].append(got.get(n))

    nombre_k = next((n for n in nombres if "FUJIMORI" in n.upper()
                     or "FUERZA POPULAR" in n.upper()), None)
    nombre_r = next((n for n in nombres if "SANCHEZ" in n.upper()
                     or "JUNTOS" in n.upper()), None)
    if nombre_k is None and nombres:
        nombre_k = nombres[0]
    if nombre_r is None and len(nombres) > 1:
        nombre_r = nombres[1]

    colores = {n: PALETA[i % len(PALETA)] for i, n in enumerate(nombres)}
    if nombre_k:
        colores[nombre_k] = "#F4720B"
    if nombre_r:
        colores[nombre_r] = "#2EA043"

    ult = historial[-1]
    pct_actas = [e["pct_actas"] for e in historial]

    vk = series.get(nombre_k, [None])[-1] if nombre_k else None
    vr = series.get(nombre_r, [None])[-1] if nombre_r else None
    lider = diferencia = None
    if vk is not None and vr is not None:
        diferencia = round(abs(vk - vr), 3)
        lider = nombre_k if vk >= vr else nombre_r

    return {
        "actualizado": _a_peru_iso(ult["timestamp"]),
        "candidatos":  nombres,
        "colores":     colores,
        "tiempos":     tiempos,
        "series":      series,
        "actas": {
            "pct":            pct_actas,
            "contabilizadas": ult.get("contabilizadas", 0),
            "total":          ult.get("total_actas", 0),
        },
        "ultimo": {"lider": lider, "diferencia_pp": diferencia},
    }


def _proximo_tick(intervalo_min):
    base  = datetime.now().replace(second=0, microsecond=0)
    resto = base.minute % intervalo_min
    if resto == 0:
        return base + timedelta(minutes=intervalo_min)
    return base + timedelta(minutes=(intervalo_min - resto))


def _actualizar_payload(historial, intervalo):
    payload = construir_payload(historial, intervalo)
    with _lock:
        _estado["payload"] = payload


def bucle_tracker(historial_path, intervalo):
    historial = cargar_historial(historial_path)
    _actualizar_payload(historial, intervalo)
    if historial:
        print(f"  Historial previo: {len(historial)} registros.")

    primera = True
    while True:
        if not primera:
            espera = (_proximo_tick(intervalo) - datetime.now()).total_seconds()
            if espera > 0:
                time.sleep(espera)
        primera = False

        print(f"\n[{datetime.now():%H:%M:%S}] Consultando ONPE ...")
        try:
            resultado = fetch_resumen()
        except Exception as exc:
            print(f"  Error consultando ONPE: {exc}")
            resultado = None

        if resultado:
            historial.append(resultado)
            try:
                guardar_historial(historial, historial_path)
                _actualizar_payload(historial, intervalo)
                print(f"  OK: {resultado['pct_actas']:.2f}% actas "
                      f"({len(historial)} puntos)")
            except Exception as exc:
                print(f"  Error guardando: {exc}")
        else:
            print("  Sin datos esta vez, se reintenta en el proximo ciclo.")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(BASE_DIR, "index.html"), "rb") as f:
                    self._send(200, "text/html; charset=utf-8", f.read())
            except FileNotFoundError:
                self._send(500, "text/plain", b"falta index.html")
        elif path == "/api/datos":
            with _lock:
                body = json.dumps(_estado["payload"], ensure_ascii=False)
            self._send(200, "application/json; charset=utf-8",
                       body.encode("utf-8"))
        elif path == "/healthz":
            self._send(200, "text/plain", b"ok")
        else:
            self._send(404, "text/plain", b"not found")

    def log_message(self, *_):
        pass


def main():
    p = argparse.ArgumentParser(description="Servidor local del tracker ONPE")
    p.add_argument("--port",      type=int, default=8000)
    p.add_argument("--intervalo", type=int, default=5,
                   help="Minutos entre consultas")
    p.add_argument("--historial", default="onpe_historial.json")
    args = p.parse_args()

    threading.Thread(
        target=bucle_tracker,
        args=(args.historial, args.intervalo),
        daemon=True,
    ).start()

    print(f"Servidor en http://localhost:{args.port}  "
          f"(intervalo {args.intervalo} min)")
    print("  Ctrl+C para detener.")
    try:
        ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nDetenido.")


if __name__ == "__main__":
    main()
