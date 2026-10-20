"""Punto de entrada: define las páginas, la navegación y la barra lateral."""
import requests
import streamlit as st

from api_cliente import pedir, url_api

st.set_page_config(page_title="Taxis NYC", page_icon=":material/local_taxi:", layout="wide")

paginas = {
    "Planificar": [
        st.Page("paginas/pronostico.py", title="Pronóstico", icon=":material/insights:", default=True),
        st.Page("paginas/decision.py", title="Decisión", icon=":material/tune:"),
    ],
    "Entender": [
        st.Page("paginas/segmentacion.py", title="Segmentación de zonas", icon=":material/bubble_chart:"),
        st.Page("paginas/ficha.py", title="Ficha del modelo", icon=":material/description:"),
    ],
}
pagina = st.navigation(paginas)

with st.sidebar:
    st.markdown("**:material/local_taxi: Taxis NYC**")
    st.caption("Demanda de taxis amarillos, enero de 2024 (NYC TLC).")
    try:
        pedir("/")
        st.badge("API en línea", icon=":material/cloud_done:", color="green")
    except requests.RequestException:
        st.badge("API sin respuesta", icon=":material/cloud_off:", color="red")
    with st.popover("Configurar API", icon=":material/settings:"):
        st.caption("La app consulta esta dirección (se cambia en los Secrets de Streamlit Cloud):")
        st.code(url_api(), language=None)

pagina.run()
