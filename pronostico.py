from datetime import date

import inspect

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from api_cliente import conectar, pedir

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
ZONA_POR_DEFECTO = 161            # Midtown Center, si existe
COLOR = "#2D6A66"                 # verde del tema
COLOR_REAL = "#B23A3A"
# En versiones recientes de Streamlit se puede ocultar la flecha de la métrica; en las anteriores no existe ese parámetro
SIN_FLECHA = {"delta_arrow": "off"} if "delta_arrow" in inspect.signature(st.metric).parameters else {}


# ------------------------------------------------------------------ ayuda (ventana emergente)
@st.dialog("¿Cómo leer este pronóstico?")
def ayuda():
    st.markdown(
        """
- La **línea** es el pronóstico central (mediana): la mitad de las veces la demanda real queda arriba y la mitad abajo.
- La **banda** va del cuantil 10% al 90%: en 8 de cada 10 horas, la demanda real cae dentro.
- Los **puntos** son los viajes que de verdad ocurrieron (no existen para mañana).
- Una banda ancha no es un error del modelo: es una hora **difícil de predecir**, y conviene saberlo.
        """
    )


# ------------------------------------------------------------------ utilidades
def etiqueta_fecha(texto: str, futuras: list[str]) -> str:
    d = date.fromisoformat(texto)
    sufijo = " (mañana)" if texto in futuras else ""
    return f"{DIAS[d.weekday()]} {d.day}{sufijo}"


def fecha_larga(texto: str) -> str:
    d = date.fromisoformat(texto)
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


# ------------------------------------------------------------------ encabezado
col_titulo, col_ayuda = st.columns([5, 1], vertical_alignment="bottom")
with col_titulo:
    st.title("Pronóstico de demanda")
    st.caption("Viajes por hora que se esperan en una zona, con su rango de incertidumbre. El modelo vive en la API.")
with col_ayuda:
    if st.button("Cómo leerlo", icon=":material/help:"):
        ayuda()

info = conectar()                                   # si la API no responde, explica y detiene la página
futuras = info["fechas_futuras"]

# ------------------------------------------------------------------ selectores (recuerdan su valor y viajan en el link)
ids_zona = [z["id"] for z in info["zonas"]]
datos_zona = {z["id"]: z for z in info["zonas"]}

zona_inicial = st.session_state.get("zona_sel")
if zona_inicial not in ids_zona:
    try:
        zona_inicial = int(st.query_params.get("zona", ZONA_POR_DEFECTO))
    except ValueError:
        zona_inicial = ZONA_POR_DEFECTO
if zona_inicial not in ids_zona:
    zona_inicial = ids_zona[0]

fecha_inicial = st.session_state.get("fecha_sel")
if fecha_inicial not in info["fechas"]:
    fecha_inicial = st.query_params.get("fecha", info["fechas"][0])
if fecha_inicial not in info["fechas"]:
    fecha_inicial = info["fechas"][0]

# Los selectores se manejan con `key` y se siembran desde session_state: así cambiar de zona o fecha nunca se pierde
if st.session_state.get("w_zona") not in ids_zona:
    st.session_state["w_zona"] = zona_inicial
if st.session_state.get("w_fecha") not in info["fechas"]:
    st.session_state["w_fecha"] = fecha_inicial

zona_id = st.selectbox(
    "Zona",
    ids_zona,
    key="w_zona",
    format_func=lambda i: f"{datos_zona[i]['nombre']} ({datos_zona[i]['distrito']})",
)
fecha = st.segmented_control(
    "Fecha",
    info["fechas"],
    key="w_fecha",
    format_func=lambda f: etiqueta_fecha(f, futuras),
    selection_mode="single",
) or fecha_inicial

st.session_state["zona_sel"] = zona_id              # para recordarlas al cambiar de página
st.session_state["fecha_sel"] = fecha
st.query_params["zona"] = str(zona_id)                   # para poder compartir el link
st.query_params["fecha"] = fecha

# ------------------------------------------------------------------ pronóstico desde la API
try:
    datos = pedir("/pronostico", zona_id=zona_id, fecha=fecha)
except requests.HTTPError as error:
    if error.response is not None and error.response.status_code == 404:
        st.warning("No hay pronóstico para esa zona y fecha.", icon=":material/search_off:")
    else:
        st.error("La API respondió con un error. Intenta de nuevo en un momento.", icon=":material/error:")
    st.stop()
except requests.RequestException:
    st.error("Se perdió la conexión con la API. Recarga la página.", icon=":material/cloud_off:")
    st.stop()

tabla = pd.DataFrame(
    [{"hora": h["hora"], "real": h["real"], "hace_una_semana": h["hace_una_semana"], **h["cuantiles"]} for h in datos["horas"]]
)
es_futuro = fecha in futuras
hay_real = tabla["real"].notna().any()

# ------------------------------------------------------------------ métricas
total_p50 = tabla["p50"].sum()
total_semana = tabla["hace_una_semana"].sum()
cambio = (total_p50 / total_semana - 1) * 100 if total_semana else 0
hora_pico = tabla.loc[tabla["p50"].idxmax()]

m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "Viajes esperados en el día",
    f"{total_p50:,.0f}",
    delta=f"{cambio:+.0f}% vs. hace una semana",
    border=True,
    chart_data=tabla["p50"].tolist(),
    chart_type="area",
)
m2.metric(
    "Hora pico",
    f"{int(hora_pico['hora']):02d}:00",
    delta=f"{hora_pico['p50']:,.0f} viajes",
    delta_color="off",
    **SIN_FLECHA,
    border=True,
)
m3.metric(
    "Rango del día (80%)",
    f"{tabla['p10'].sum():,.0f} – {tabla['p90'].sum():,.0f}",
    help="Suma de los límites 10% y 90% de cada hora. Es un rango conservador: más ancho de lo estricto, "
         "porque no es probable que todas las horas se equivoquen en el mismo sentido a la vez.",
    border=True,
)
if hay_real:
    error_medio = (tabla["real"] - tabla["p50"]).abs().mean()
    m4.metric(
        "Error promedio por hora",
        f"{error_medio:,.1f} viajes",
        delta=f"{tabla['real'].sum():,.0f} viajes reales",
        delta_color="off",
        **SIN_FLECHA,
        border=True,
    )
else:
    m4.metric(
        "Viajes reales",
        "Pendiente",
        delta="pronóstico a futuro",
        delta_color="off",
        **SIN_FLECHA,
        border=True,
    )

# ------------------------------------------------------------------ gráfico con banda de incertidumbre
nombre_zona = datos["zona"]["nombre"]
titulo = f"{nombre_zona} · {fecha_larga(fecha)}" + (" (pronóstico a futuro)" if es_futuro else "")

fig = go.Figure()
# La banda: primero la línea de arriba (p90), luego la de abajo (p10) rellenando hasta la anterior
fig.add_trace(go.Scatter(x=tabla["hora"], y=tabla["p90"], mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
fig.add_trace(go.Scatter(
    x=tabla["hora"], y=tabla["p10"], mode="lines", line=dict(width=0),
    fill="tonexty", fillcolor="rgba(45,106,102,0.18)", name="Rango 10%–90%", hoverinfo="skip",
))
fig.add_trace(go.Scatter(
    x=tabla["hora"], y=tabla["hace_una_semana"], mode="lines", name="Hace una semana",
    line=dict(color="#7A7F87", width=1.5, dash="dot"),
))
fig.add_trace(go.Scatter(
    x=tabla["hora"], y=tabla["p50"], mode="lines", name="Pronóstico (mediana)", line=dict(color=COLOR, width=3),
    customdata=tabla[["p10", "p90"]].to_numpy(),
    hovertemplate="Hora %{x}:00<br>Mediana: %{y:.0f}<br>Rango: %{customdata[0]:.0f} – %{customdata[1]:.0f}<extra></extra>",
))
if hay_real:
    fig.add_trace(go.Scatter(
        x=tabla["hora"], y=tabla["real"], mode="markers", name="Real",
        marker=dict(color=COLOR_REAL, size=8),
    ))
fig.update_layout(
    title=dict(text=titulo, font=dict(size=15)),
    xaxis=dict(title="Hora del día", dtick=2, range=[-0.5, 23.5]),
    yaxis=dict(title="Viajes", rangemode="tozero"),
    legend=dict(orientation="h", yanchor="top", y=-0.22, x=0),
    margin=dict(l=10, r=10, t=50, b=10),
    height=430,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig)

if es_futuro:
    st.info(
        "El 1 de febrero es \"mañana\": todavía no hay viajes reales, por eso solo se ve el pronóstico.",
        icon=":material/schedule:",
    )

# ------------------------------------------------------------------ tabla por hora
with st.expander("Ver la tabla por hora", icon=":material/table:"):
    vista = tabla.rename(columns={
        "hora": "Hora", "real": "Real", "hace_una_semana": "Hace una semana",
        "p10": "Mínimo (p10)", "p50": "Pronóstico (p50)", "p90": "Máximo (p90)",
    })[["Hora", "Real", "Hace una semana", "Mínimo (p10)", "Pronóstico (p50)", "Máximo (p90)"]]
    st.dataframe(
        vista,
        hide_index=True,
        column_config={
            "Hora": st.column_config.NumberColumn(format="%d:00"),
            "Real": st.column_config.NumberColumn(format="%d"),
            "Hace una semana": st.column_config.NumberColumn(format="%d"),
            "Mínimo (p10)": st.column_config.NumberColumn(format="%.0f"),
            "Máximo (p90)": st.column_config.NumberColumn(format="%.0f"),
            "Pronóstico (p50)": st.column_config.ProgressColumn(
                format="%.0f", min_value=0, max_value=float(tabla["p90"].max()),
            ),
        },
    )
