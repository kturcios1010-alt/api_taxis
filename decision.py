from datetime import date

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from api_cliente import conectar, pedir
from decision_logica import COLUMNAS, costos, cuantil_optimo, taxis_para_cuantil

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
ZONA_POR_DEFECTO = 161
PRIMER_DIA_PRUEBA = "2024-01-25"          # del 25 al 31 el modelo no vio los datos reales al entrenarse
COLOR = "#2D6A66"
COLOR_REAL = "#B23A3A"
COLOR_OCIOSO = "#C97B3F"


def etiqueta_fecha(texto: str, futuras: list[str]) -> str:
    d = date.fromisoformat(texto)
    return f"{DIAS[d.weekday()]} {d.day}" + (" (mañana)" if texto in futuras else "")


def fecha_larga(texto: str) -> str:
    d = date.fromisoformat(texto)
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def dinero(x: float) -> str:
    return f"${x:,.0f}"


@st.cache_data(ttl=3600, show_spinner=False)
def cargar_dia(zona_id: int, fecha: str) -> pd.DataFrame:
    datos = pedir("/pronostico", zona_id=zona_id, fecha=fecha)
    return pd.DataFrame(
        [{"hora": h["hora"], "real": h["real"], "hace_una_semana": h["hace_una_semana"], **h["cuantiles"]} for h in datos["horas"]]
    )


# ------------------------------------------------------------------ encabezado
st.title("¿Cuántos taxis enviar?")
st.caption(
    "Se fija cuánto cuesta cada error y la app calcula cuántos taxis conviene mandar cada hora "
    "y cuánto habrías gastado con otras estrategias."
)

info = conectar()
futuras = info["fechas_futuras"]
ids_zona = [z["id"] for z in info["zonas"]]
datos_zona = {z["id"]: z for z in info["zonas"]}

# ------------------------------------------------------------------ zona y fecha (recuerdan lo elegido en el Pronóstico)
zona_inicial = st.session_state.get("zona_sel", ZONA_POR_DEFECTO)
if zona_inicial not in ids_zona:
    zona_inicial = ids_zona[0]
fechas_reales = [f for f in info["fechas"] if f not in futuras]
fecha_inicial = st.session_state.get("fecha_sel")
if fecha_inicial not in info["fechas"]:
    fecha_inicial = PRIMER_DIA_PRUEBA if PRIMER_DIA_PRUEBA in info["fechas"] else info["fechas"][0]

if st.session_state.get("w_zona") not in ids_zona:
    st.session_state["w_zona"] = zona_inicial
if st.session_state.get("w_fecha") not in info["fechas"]:
    st.session_state["w_fecha"] = fecha_inicial

col_z, col_f = st.columns([1, 2])
zona_id = col_z.selectbox(
    "Zona",
    ids_zona,
    key="w_zona",
    format_func=lambda i: f"{datos_zona[i]['nombre']} ({datos_zona[i]['distrito']})",
)
fecha = col_f.segmented_control(
    "Fecha",
    info["fechas"],
    key="w_fecha",
    format_func=lambda f: etiqueta_fecha(f, futuras),
    selection_mode="single",
) or fecha_inicial
st.session_state["zona_sel"] = zona_id
st.session_state["fecha_sel"] = fecha

try:
    tabla = cargar_dia(zona_id, fecha)
except requests.HTTPError as error:
    if error.response is not None and error.response.status_code == 404:
        st.warning("No hay pronóstico para esa zona y fecha.", icon=":material/search_off:")
    else:
        st.error("La API respondió con un error. Debe intentarse de nuevo en un momento.", icon=":material/error:")
    st.stop()
except requests.RequestException:
    st.error("Se perdió la conexión con la API. Conviene recargar la página.", icon=":material/cloud_off:")
    st.stop()

hay_real = tabla["real"].notna().all()
es_futuro = fecha in futuras
nombre_zona = datos_zona[zona_id]["nombre"]


# ------------------------------------------------------------------ todo lo que depende de los costos se recalcula solo (fragmento)
@st.fragment
def decision():
    st.subheader("1. ¿Cuánto cuesta cada error?")
    c1, c2 = st.columns(2)
    c_ocioso = c1.slider(
        "Un taxi una hora sin pasajero (US$)", 1, 100, 10, key="c_ocioso",
        help="Lo que se pierde por cada taxi enviado que se quedó esperando.",
    )
    c_perdido = c2.slider(
        "Un pasajero que no encuentra taxi (US$)", 1, 200, 40, key="c_perdido",
        help="Lo que se pierde por cada viaje que no se pudo atender.",
    )

    q = cuantil_optimo(c_perdido, c_ocioso)
    q_usado = min(max(q, 0.1), 0.9)
    recomendado = taxis_para_cuantil(tabla, q_usado)
    p50 = taxis_para_cuantil(tabla, 0.5)
    semana = tabla["hace_una_semana"].to_numpy()

    st.subheader("2. Qué conviene hacer")
    if abs(q - q_usado) > 1e-9:
        st.warning(
            f"El cuantil óptimo sería {q:.0%}, pero el modelo solo entrega del 10% al 90%. "
            f"Se usa el {q_usado:.0%}, el más cercano disponible.",
            icon=":material/warning:",
        )
    razon = c_perdido / c_ocioso
    if razon > 1.0001:
        frase = (f"Perder un pasajero cuesta **{razon:.1f} veces** lo que cuesta un taxi ocioso, así que conviene **pasarse** "
                 f"antes que quedarse corto: se envía la cantidad que alcanza en el **{q:.0%}** de los casos, "
                 "más que el pronóstico central.")
    elif razon < 0.9999:
        frase = (f"Un taxi ocioso cuesta **{1 / razon:.1f} veces** lo que cuesta perder un pasajero, así que conviene "
                 f"**quedarse algo corto**: se envía la cantidad que alcanza en el **{q:.0%}** de los casos, "
                 "menos que el pronóstico central.")
    else:
        frase = "Los dos errores cuestan lo mismo, así que lo mejor es enviar el pronóstico central (cuantil 50%)."
    st.markdown(frase)
    st.latex(
        rf"\text{{cuantil óptimo}}=\frac{{\text{{pasajero perdido}}}}{{\text{{pasajero perdido}}+\text{{taxi ocioso}}}}"
        rf"=\frac{{{c_perdido}}}{{{c_perdido}+{c_ocioso}}}={q:.2f}"
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Cuantil óptimo", f"{q:.0%}", border=True, help="Qué tan seguro se quiere estar de cubrir la demanda de cada hora.")
    m2.metric(
        "Taxis a enviar en el día",
        f"{recomendado.sum():,}",
        delta=f"{recomendado.sum() - p50.sum():+,} vs. pronóstico central",
        delta_color="off",
        border=True,
    )
    hora_max = int(tabla["hora"].iloc[recomendado.argmax()])
    m3.metric("Hora con más taxis", f"{hora_max:02d}:00", delta=f"{recomendado.max():,} taxis", delta_color="off", border=True)

    # --------------------------------------------- gráfico del plan por hora
    fig = go.Figure()
    fig.add_trace(go.Bar(x=tabla["hora"], y=recomendado, name=f"Taxis a enviar (cuantil {q_usado:.0%})", marker_color=COLOR, opacity=0.85))
    fig.add_trace(go.Scatter(x=tabla["hora"], y=p50, mode="lines", name="Pronóstico central (p50)", line=dict(color="#1B2A41", width=2)))
    fig.add_trace(go.Scatter(x=tabla["hora"], y=semana, mode="lines", name="Igual que hace una semana", line=dict(color="#7A7F87", width=1.5, dash="dot")))
    if hay_real:
        fig.add_trace(go.Scatter(x=tabla["hora"], y=tabla["real"], mode="markers", name="Viajes reales", marker=dict(color=COLOR_REAL, size=8)))
    fig.update_layout(
        title=dict(text=f"{nombre_zona} · {fecha_larga(fecha)}" + (" (mañana)" if es_futuro else ""), font=dict(size=15)),
        xaxis=dict(title="Hora del día", dtick=2, range=[-0.7, 23.7]),
        yaxis=dict(title="Taxis", rangemode="tozero"),
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0),
        margin=dict(l=10, r=10, t=50, b=10),
        height=410,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig)

    # --------------------------------------------- descarga del plan
    plan = pd.DataFrame({
        "zona": nombre_zona,
        "fecha": fecha,
        "hora": tabla["hora"],
        "taxis_a_enviar": recomendado,
        "pronostico_central_p50": p50,
        "cuantil_usado": round(q_usado, 3),
        "costo_taxi_ocioso": c_ocioso,
        "costo_pasajero_perdido": c_perdido,
    })
    st.download_button(
        "Descargar el plan por hora (CSV)",
        plan.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"plan_taxis_zona{zona_id}_{fecha}.csv",
        mime="text/csv",
        icon=":material/download:",
    )

    # --------------------------------------------- comparación de costos (solo con datos reales)
    st.subheader("3. ¿Cuánto habrías gastado con otras estrategias?")
    if not hay_real:
        st.info(
            "El 1 de febrero es \"mañana\": todavía no hay viajes reales para calcular costos. "
            "Para comparar hay que elegir un día de enero.",
            icon=":material/schedule:",
        )
        return
    if fecha < PRIMER_DIA_PRUEBA:
        st.warning(
            "Este día se usó para entrenar el modelo, así que ya \"conocía\" la respuesta y la comparación sale demasiado buena. "
            f"Para una comparación honesta conviene elegir del {PRIMER_DIA_PRUEBA[-2:]} al 31 de enero.",
            icon=":material/school:",
        )

    real = tabla["real"].to_numpy()
    estrategias = {
        f"Recomendación (cuantil {q_usado:.0%})": recomendado,
        "Pronóstico central (p50)": p50,
        "Igual que hace una semana": semana,
    }
    filas = []
    for nombre, enviados in estrategias.items():
        c = costos(enviados, real, c_ocioso, c_perdido)
        filas.append({
            "Estrategia": nombre,
            "Taxis enviados": c["taxis_enviados"],
            "Taxis ociosos": c["taxis_ociosos"],
            "Pasajeros perdidos": c["pasajeros_perdidos"],
            "Costo de taxis ociosos": c["costo_ocioso"],
            "Costo de pasajeros perdidos": c["costo_perdido"],
            "Costo total": c["costo_total"],
        })
    comp = pd.DataFrame(filas)
    mejor = comp["Costo total"].min()
    costos_total = comp["Costo total"].tolist()
    propio = costos_total[0]

    def cambio(otro):
        """Cuánto más (o menos) cuesta la otra regla frente a la recomendación, en %."""
        return f"{(otro / propio - 1) * 100:+.0f}% vs. la recomendación" if propio > 0 else None

    k1, k2, k3 = st.columns(3)
    k1.metric(f"Recomendación (p{q_usado * 100:.0f})", dinero(propio), border=True)
    k2.metric("Enviar el pronóstico central (p50)", dinero(costos_total[1]), delta=cambio(costos_total[1]),
              delta_color="inverse", border=True, help="Rojo: cuesta más que la recomendación. Verde: cuesta menos.")
    k3.metric("Enviar lo de hace una semana", dinero(costos_total[2]), delta=cambio(costos_total[2]),
              delta_color="inverse", border=True, help="Rojo: cuesta más que la recomendación. Verde: cuesta menos.")

    fig_c = go.Figure()
    fig_c.add_trace(go.Bar(y=comp["Estrategia"], x=comp["Costo de taxis ociosos"], name="Taxis ociosos", orientation="h", marker_color=COLOR_OCIOSO))
    fig_c.add_trace(go.Bar(y=comp["Estrategia"], x=comp["Costo de pasajeros perdidos"], name="Pasajeros perdidos", orientation="h", marker_color=COLOR_REAL))
    fig_c.update_layout(
        barmode="stack", height=230, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(title="Costo total del día (US$)"), yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", yanchor="top", y=-0.35, x=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_c)

    st.dataframe(
        comp, hide_index=True,
        column_config={
            "Costo de taxis ociosos": st.column_config.NumberColumn(format="$%d"),
            "Costo de pasajeros perdidos": st.column_config.NumberColumn(format="$%d"),
            "Costo total": st.column_config.NumberColumn(format="$%d"),
        },
    )
    if mejor < propio - 0.5:
        st.caption(
            ":material/info: Un solo día puede salir mal por azar: si otra estrategia gana hoy, conviene mirar la semana completa. "
            "El cuantil óptimo es el mejor **en promedio**, no cada día."
        )

    if st.toggle("Ver los 7 días de prueba de esta zona (25 al 31 de enero)"):
        fechas_prueba = [f for f in fechas_reales if f >= PRIMER_DIA_PRUEBA]
        acumulado = {nombre: 0.0 for nombre in estrategias}
        for f in fechas_prueba:
            try:
                dia = cargar_dia(zona_id, f)
            except requests.RequestException:
                st.error("No se pudo consultar uno de los días. Conviene recargar la página.")
                break
            r = dia["real"].to_numpy()
            plan_dia = {
                f"Recomendación (cuantil {q_usado:.0%})": taxis_para_cuantil(dia, q_usado),
                "Pronóstico central (p50)": taxis_para_cuantil(dia, 0.5),
                "Igual que hace una semana": dia["hace_una_semana"].to_numpy(),
            }
            for nombre, enviados in plan_dia.items():
                acumulado[nombre] += costos(enviados, r, c_ocioso, c_perdido)["costo_total"]
        semana_df = pd.DataFrame({"Estrategia": list(acumulado), "Costo de la semana": list(acumulado.values())})
        st.dataframe(semana_df, hide_index=True, column_config={"Costo de la semana": st.column_config.NumberColumn(format="$%d")})


decision()
