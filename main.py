"""API de pronóstico de demanda de taxis amarillos de NYC.

Endpoints (el "contrato" que la app de Streamlit espera):
    GET /            -> confirma que la API está en línea
    GET /info        -> zonas pronosticables, fechas disponibles y cuantiles
    GET /pronostico  -> las 24 horas de una zona y fecha, con cuantiles

Probar localmente:  uvicorn main:app --reload   y abrir http://localhost:8000/docs
"""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from fastapi import FastAPI, HTTPException

BASE = Path(__file__).parent

# Deben ser exactamente las mismas variables, y en el mismo orden, que en el entrenamiento
VARIABLES = [
    "zona", "hora_dia", "dia_semana", "feriado",
    "lag_24", "lag_48", "lag_167", "lag_168", "lag_169", "media_dia_ant",
]
ETIQUETAS = [f"p{p}" for p in range(10, 100, 10)]   # p10, p20, ..., p90

app = FastAPI(
    title="Pronóstico de demanda de taxis NYC",
    description="Devuelve cuántos viajes se esperan por hora en cada zona, con su rango de incertidumbre.",
)

# --- Se carga una sola vez, cuando arranca la API ---------------------------------------------
zonas = pd.read_csv(BASE / "zonas_pronostico.csv")          # columnas: id, nombre, distrito
CATEGORIAS_ZONA = sorted(zonas["id"].tolist())               # mismas categorías que en el entrenamiento

demanda = pd.read_parquet(BASE / "demanda.parquet")
demanda["zona"] = pd.Categorical(demanda["PULocationID"], categories=CATEGORIAS_ZONA)
demanda["fecha"] = demanda["hora"].dt.date

modelo = xgb.Booster()                                       # el modelo de XGBoost "puro" (sin scikit-learn)
modelo.load_model(str(BASE / "modelo_pronostico.ubj"))


# --- Endpoints --------------------------------------------------------------------------------
@app.get("/")
def raiz():
    return {"estado": "en línea", "servicio": "Pronóstico de demanda de taxis NYC"}


@app.get("/info")
def info():
    fechas = sorted(demanda["fecha"].unique())
    # Las fechas sin ningún viaje real son pronóstico a futuro (el "mañana")
    futuras = sorted(
        f for f, grupo in demanda.groupby("fecha") if grupo["viajes"].isna().all()
    )
    return {
        "zonas": zonas.to_dict(orient="records"),
        "fechas": [f.isoformat() for f in fechas],
        "fechas_futuras": [f.isoformat() for f in futuras],
        "cuantiles": ETIQUETAS,
    }


@app.get("/pronostico")
def pronostico(zona_id: int, fecha: date):
    filas = demanda[(demanda["PULocationID"] == zona_id) & (demanda["fecha"] == fecha)]
    if filas.empty:
        raise HTTPException(status_code=404, detail="No hay datos para esa zona o fecha")
    filas = filas.sort_values("hora")

    # Sin negativos (no existen viajes negativos) y cuantiles ordenados fila por fila
    entrada = xgb.DMatrix(filas[VARIABLES], enable_categorical=True)   # la zona es una categoría
    predicciones = np.clip(modelo.predict(entrada), 0, None)
    predicciones = np.sort(predicciones, axis=1)

    datos_zona = zonas[zonas["id"] == zona_id].iloc[0]
    horas = []
    for (_, fila), cuantiles in zip(filas.iterrows(), predicciones):
        horas.append({
            "hora": int(fila["hora_dia"]),
            "real": None if pd.isna(fila["viajes"]) else int(fila["viajes"]),
            "hace_una_semana": int(fila["lag_168"]),
            "cuantiles": {etiqueta: round(float(v), 1) for etiqueta, v in zip(ETIQUETAS, cuantiles)},
        })

    return {
        "zona": {
            "id": int(datos_zona["id"]),
            "nombre": datos_zona["nombre"],
            "distrito": datos_zona["distrito"],
        },
        "fecha": fecha.isoformat(),
        "horas": horas,
    }
