"""Funciones compartidas por todas las páginas para hablar con la API."""
import requests
import streamlit as st


def url_api() -> str:
    """La dirección de la API vive en st.secrets (no en el código). Si no existe, se usa la local."""
    try:
        return str(st.secrets["API_URL"]).rstrip("/")
    except Exception:
        return "http://localhost:8000"


@st.cache_data(ttl=3600, show_spinner=False)
def _pedir(base: str, ruta: str, parametros: dict):
    """GET a la API. Con @st.cache_data, la misma consulta no se repite en cada clic durante una hora.
    Si la API falla se lanza una excepción, y las excepciones NO se guardan en el caché."""
    respuesta = requests.get(f"{base}{ruta}", params=parametros, timeout=90)   # 90 s: Render tarda ~1 min en despertar
    respuesta.raise_for_status()
    return respuesta.json()


def pedir(ruta: str, **parametros):
    return _pedir(url_api(), ruta, parametros)


def conectar():
    """Conecta con la API y devuelve /info. Si no responde, explica qué pasó y detiene la página (sin errores de Python)."""
    try:
        with st.status("Conectando con la API...", expanded=False) as estado:
            info = pedir("/info")
            estado.update(label="API conectada", state="complete")
        return info
    except requests.RequestException as error:
        st.error(
            f"No se pudo conectar con la API en {url_api()}. "
            "Si está en Render, puede estar despertando: conviene esperar un minuto y recargar la página.",
            icon=":material/cloud_off:",
        )
        st.caption(f"Detalle: {error}")
        st.stop()
