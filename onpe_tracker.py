#!/usr/bin/env python3
"""
Lectura del conteo nacional de la ONPE para la segunda vuelta 2026.

Consulta la API publica del conteo y maneja el historial en JSON.
El servidor (servidor_local.py) reutiliza estas funciones.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from curl_cffi import requests as cr
except ImportError:
    print("Falta curl_cffi. Instala con: pip install curl_cffi")
    sys.exit(1)


BASE_URL    = "https://resultadosegundavuelta.onpe.gob.pe"
ID_ELECCION = 10

PARAMS_NACIONAL = {
    "idEleccion":       ID_ELECCION,
    "ambitoGeografico": 1,
    "tipoFiltro":       "eleccion",
    "idEleccionFiltro": ID_ELECCION,
}

HEADERS_API = {
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
    "Referer":         f"{BASE_URL}/main/resumen",
    "Origin":          BASE_URL,
    "Cache-Control":   "no-cache",
}


def _get_api(path, params, timeout=25):
    return cr.get(
        BASE_URL + path,
        headers=HEADERS_API,
        params=params,
        impersonate="chrome124",
        timeout=timeout,
    )


def _parse_json_safe(resp):
    body = resp.text.strip()
    if body[:1] not in ("{", "["):
        return None
    try:
        raw = resp.json()
    except Exception:
        return None
    if isinstance(raw, dict) and not raw.get("success", True):
        return None
    if isinstance(raw, dict) and "data" in raw:
        return raw["data"]
    return raw


def fetch_resumen():
    try:
        r_cand = _get_api(
            "/presentacion-backend/resumen-general/participantes",
            PARAMS_NACIONAL,
        )
    except Exception:
        return None

    if r_cand.status_code != 200:
        return None

    lista_cand = _parse_json_safe(r_cand)
    if not isinstance(lista_cand, list) or not lista_cand:
        return None

    # los codigos 80 y 81 son votos en blanco y nulos, se descartan
    candidatos = []
    for c in lista_cand:
        if not isinstance(c, dict):
            continue
        codigo = str(c.get("codigoAgrupacionPolitica", ""))
        if codigo in ("80", "81"):
            continue
        nombre = (c.get("nombreAgrupacionPolitica")
                  or c.get("nombreCandidato")
                  or c.get("nombre") or "?")
        candidato = c.get("nombreCandidato", "")
        votos = int(c.get("totalVotosValidos", c.get("totalVotos", 0)))
        pct_val = float(c.get("porcentajeVotosValidos",
                        c.get("porcentajeVotos", 0.0)))
        candidatos.append({
            "nombre":     nombre,
            "candidato":  candidato,
            "votos":      votos,
            "porcentaje": pct_val,
        })

    if not candidatos:
        return None

    pct_actas = total_actas = contabilizadas = 0
    try:
        r_tot = _get_api(
            "/presentacion-backend/resumen-general/totales",
            PARAMS_NACIONAL,
        )
        if r_tot.status_code == 200:
            tot = _parse_json_safe(r_tot)
            if isinstance(tot, list):
                tot = tot[0] if tot else {}
            if isinstance(tot, dict):
                pct_actas      = float(tot.get("actasContabilizadas", 0.0))
                total_actas    = int(tot.get("totalActas", 0))
                contabilizadas = int(tot.get("contabilizadas", 0))
    except Exception:
        pass

    return {
        "timestamp":      datetime.now(),
        "candidatos":     candidatos,
        "pct_actas":      pct_actas,
        "total_actas":    total_actas,
        "contabilizadas": contabilizadas,
    }


def cargar_historial(path):
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    for entry in raw:
        if isinstance(entry.get("timestamp"), str):
            entry["timestamp"] = datetime.fromisoformat(entry["timestamp"])
    return raw


def guardar_historial(historial, path):
    serial = []
    for entry in historial:
        e = dict(entry)
        e["timestamp"] = entry["timestamp"].isoformat()
        serial.append(e)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serial, f, ensure_ascii=False, indent=2)


def _filtrar_por_intervalo(historial, intervalo_min):
    # deja solo las entradas que caen en una marca de reloj multiplo de
    # intervalo_min (los segundos se redondean al minuto). si varias caen
    # en la misma marca, se queda con la mas cercana.
    if not intervalo_min or intervalo_min <= 0:
        return historial

    seleccion = {}
    for entry in historial:
        ts = entry["timestamp"]
        marca = ts.replace(second=0, microsecond=0)
        if ts.second >= 30:
            marca += timedelta(minutes=1)
        if marca.minute % intervalo_min != 0:
            continue
        dist = abs((ts - marca).total_seconds())
        prev = seleccion.get(marca)
        if prev is None or dist < prev[0]:
            seleccion[marca] = (dist, entry)

    return [seleccion[k][1] for k in sorted(seleccion.keys())]
