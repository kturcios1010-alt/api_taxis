"""Cuentas de la página de decisión, sin Streamlit, para poder probarlas con facilidad.

Idea del "vendedor de periódicos":
  - Si envío un taxi de más, pierdo el costo de un taxi ocioso (c_ocioso).
  - Si me falta un taxi, pierdo el costo de un pasajero perdido (c_perdido).
  - El mejor número de taxis es el cuantil  c_perdido / (c_perdido + c_ocioso)  del pronóstico.
"""
import numpy as np
import pandas as pd

NIVELES = np.arange(0.1, 0.91, 0.1)                      # 0.1, 0.2, ..., 0.9: los cuantiles que entrega la API
COLUMNAS = [f"p{int(round(n * 100))}" for n in NIVELES]  # p10, p20, ..., p90


def cuantil_optimo(c_perdido: float, c_ocioso: float) -> float:
    """Con 40 y 10 dólares: 40 / (40 + 10) = 0.80."""
    if c_perdido <= 0 or c_ocioso <= 0:
        raise ValueError("Los dos costos deben ser mayores que cero.")
    return c_perdido / (c_perdido + c_ocioso)


def taxis_para_cuantil(tabla: pd.DataFrame, q: float) -> np.ndarray:
    """Taxis a enviar cada hora: el cuantil q del pronóstico, redondeado a un número entero de taxis.

    La API solo entrega 9 cuantiles (10%, 20%, ..., 90%); si q cae entre dos, se interpola entre ellos.
    Fuera de ese rango (menos de 10% o más de 90%) se usa el cuantil extremo disponible.
    """
    valores = tabla[COLUMNAS].to_numpy(dtype=float)
    return np.array([np.rint(np.interp(q, NIVELES, fila)) for fila in valores]).astype(int)


def costos(enviados, real, c_ocioso: float, c_perdido: float) -> dict:
    """Costo de enviar `enviados` taxis cuando de verdad hubo `real` viajes, hora por hora."""
    enviados = np.asarray(enviados, dtype=float)
    real = np.asarray(real, dtype=float)
    ociosos = np.maximum(enviados - real, 0)         # taxis que sobraron
    perdidos = np.maximum(real - enviados, 0)        # pasajeros sin taxi
    return {
        "taxis_enviados": int(enviados.sum()),
        "taxis_ociosos": int(ociosos.sum()),
        "pasajeros_perdidos": int(perdidos.sum()),
        "costo_ocioso": float(ociosos.sum() * c_ocioso),
        "costo_perdido": float(perdidos.sum() * c_perdido),
        "costo_total": float(ociosos.sum() * c_ocioso + perdidos.sum() * c_perdido),
    }
