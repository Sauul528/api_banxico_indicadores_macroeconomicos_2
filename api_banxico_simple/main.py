"""
API Indicadores Macroeconómicos II
-----------------------------------
Autor: Saul Reyes Nava, Miguel Angel Prieto Villavicencio, Kevin Uziel Martinez Corral
Fecha: 27 de noviembre de 2026

API intermediaria (wrapper) que consume la API de Banxico (SIE) para tres
indicadores (dólar, UDI y un metal) y devuelve proyecciones a 30, 60 y 90 días.

Stack: FastAPI + Pydantic + Swagger (documentación automática en /docs)

Para correrla:  uvicorn main:app --reload
"""
import os
from datetime import date, datetime, timedelta
from enum import Enum

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel
from fastapi.responses import HTMLResponse

# 1. Configuración (se lee del archivo .env)
load_dotenv()

TOKEN = os.getenv("TOKEN_BANXICO")
URL_BANXICO = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"

# Clave de cada serie en Banxico
SERIES = {
    "dolar": os.getenv("SERIE_DOLAR", "SF43718"),  # Tipo de cambio FIX
    "udi": os.getenv("SERIE_UDI", "SP68257"),      # Valor de la UDI
    "metal": os.getenv("SERIE_METAL", ""),         # Valor de la onza de oro
}

NOMBRES = {
    "dolar": "Tipo de cambio FIX (pesos por dólar)",
    "udi": "Valor de la UDI (pesos)",
    "metal": os.getenv("NOMBRE_METAL", "Precio del metal"),
}

HORIZONTES = (30, 60, 90)  # días a los que se puede proyectar


# 2. Modelos de Pydantic (validan y describen los datos que regresa la API)

class Indicador(str, Enum):
    dolar = "dolar"
    udi = "udi"
    metal = "metal"


class Punto(BaseModel):
    fecha: date
    valor: float


class Proyeccion(BaseModel):
    indicador: str
    dias: int
    fecha_ultimo_dato: date
    valor_actual: float
    fecha_proyeccion: date
    valor_proyectado: float
    variacion_porcentual: float


# 3. Consulta a Banxico
def obtener_historico(indicador: str) -> list[Punto]:
    """Descarga el último año de datos de la serie desde Banxico."""
    if not TOKEN:
        raise HTTPException(503, "Falta TOKEN_BANXICO en el archivo .env")

    serie = SERIES[indicador]
    if not serie:
        raise HTTPException(503, f"Falta la clave de serie de '{indicador}' en el .env")

    hoy = date.today()
    inicio = hoy - timedelta(days=365)
    url = f"{URL_BANXICO}/{serie}/datos/{inicio}/{hoy}"

    try:
        respuesta = requests.get(url, headers={"Bmx-Token": TOKEN}, timeout=15)
    except requests.exceptions.RequestException:
        raise HTTPException(502, "No se pudo conectar con Banxico {error}")

    if respuesta.status_code != 200:
        raise HTTPException(502, f"Banxico respondió con código {respuesta.status_code}")

    try:
        datos = respuesta.json()["bmx"]["series"][0]["datos"]
    except (KeyError, IndexError):
        raise HTTPException(502, "Banxico no regresó datos para esa serie")

    puntos = []
    for d in datos:
        if d["dato"] == "N/E":  # Banxico marca así los días sin dato
            continue
        fecha = datetime.strptime(d["fecha"], "%d/%m/%Y").date()
        puntos.append(Punto(fecha=fecha, valor=float(d["dato"].replace(",", ""))))

    puntos.sort(key=lambda p: p.fecha)
    return puntos


# 4. Proyección: regresión lineal (la "línea de tendencia" de los datos)
def proyectar(puntos: list[Punto], dias: int) -> float:
    """Calcula la línea recta que mejor se ajusta al historial y la prolonga `dias` días."""
    x = [(p.fecha - puntos[0].fecha).days for p in puntos]  # días desde el primer dato
    y = [p.valor for p in puntos]

    prom_x = sum(x) / len(x)
    prom_y = sum(y) / len(y)

    pendiente = (sum((xi - prom_x) * (yi - prom_y) for xi, yi in zip(x, y))
                 / sum((xi - prom_x) ** 2 for xi in x))
    ordenada = prom_y - pendiente * prom_x

    return ordenada + pendiente * (x[-1] + dias)


# 5. Endpoints
app = FastAPI(
    title="API Indicadores Macroeconómicos",
    description="Consume la API de Banxico (dólar, UDI y un metal) y devuelve "
                "históricos y proyecciones a **30, 60 y 90 días**.",
    version="1.0.0",
)

@app.get("/", tags=["General"])
def inicio():
    """Página de inicio con la ruta de la documentación."""
    return {"mensaje": "API Indicadores Macroeconómicos", "documentacion": "/docs"}

@app.get("/{indicador}/historico", response_model=list[Punto], tags=["Histórico"])
def historico(indicador: Indicador):
    """Datos reales de Banxico del último año."""
    return obtener_historico(indicador.value)


@app.get("/{indicador}/proyeccion/{dias}", response_model=Proyeccion, tags=["Proyecciones"])
def proyeccion(indicador: Indicador, dias: int = Path(json_schema_extra={"enum": [30, 60, 90]})):
    """Proyección del indicador a 30, 60 o 90 días."""
    if dias not in HORIZONTES:
        raise HTTPException(422, f"Los días deben ser uno de: {list(HORIZONTES)}")

    puntos = obtener_historico(indicador.value)
    if len(puntos) < 10:
        raise HTTPException(422, "Hay muy pocos datos para calcular una proyección")

    ultimo = puntos[-1]
    valor_proyectado = proyectar(puntos, dias)

    return Proyeccion(
        indicador=NOMBRES[indicador.value],
        dias=dias,
        fecha_ultimo_dato=ultimo.fecha,
        valor_actual=ultimo.valor,
        fecha_proyeccion=ultimo.fecha + timedelta(days=dias),
        valor_proyectado=round(valor_proyectado, 4),
        variacion_porcentual=round((valor_proyectado - ultimo.valor) / ultimo.valor * 100, 2),
    )

