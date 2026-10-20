import json
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RUTA = Path(__file__).resolve().parent.parent / "data" / "metricas_modelo.json"
VERDE, NARANJA, GRIS = "#2D6A66", "#C97B3F", "#9AA3AD"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

st.title("Ficha del modelo")
st.caption(
    "Qué hace el modelo, qué tan bien lo hace y en qué no se debe confiar. Una ficha (model card) es un documento "
    "estándar de la industria para que cualquier persona entienda un modelo antes de usarlo."
)

if not RUTA.exists():
    st.info(
        "Faltan las métricas del modelo: `metricas_modelo.json`. Se generan con el cuaderno (sección E) "
        "y se copian en la carpeta `data/` junto a `streamlit_app.py`.",
        icon=":material/folder_off:",
    )
    st.stop()


@st.cache_data
def cargar() -> dict:
    return json.loads(RUTA.read_text(encoding="utf-8"))


m = cargar()
modelo, datos, zonas, ev = m["modelo"], m["datos"], m["zonas"], m["evaluacion"]
tipos = pd.DataFrame(m["tipo_zona"])


def fecha_corta(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} de {MESES[d.month - 1]}"


def estilo(fig, alto=270):
    fig.update_layout(
        height=alto, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="top", y=-0.25, x=0),
    )
    return fig


# ------------------------------------------------------------------ 1. para qué sirve
with st.container(border=True):
    st.subheader(":material/target: Para qué sirve")
    st.markdown(
        f"Pronostica cuántos viajes de taxi amarillo empezarán **cada hora** en **{zonas['pronosticadas']} zonas** de Nueva York, "
        f"con un rango de incertidumbre (cuantiles del {modelo['cuantiles'][0][1:]}% al {modelo['cuantiles'][-1][1:]}%). "
        "Está pensado para **planificar la flota** con un día de anticipación."
    )
    st.badge(f"XGBoost con {len(modelo['cuantiles'])} cuantiles", icon=":material/psychology:", color="blue")
    st.badge(datos["fuente"], icon=":material/database:", color="gray")
    st.badge("Horizonte: 24 horas", icon=":material/schedule:", color="green")

    with st.expander("Con qué datos se entrenó y cómo se evaluó", icon=":material/fact_check:"):
        st.markdown(
            f"""
- **Datos:** {datos['fuente']}. La zona de cada viaje es la de origen.
- **Entrenamiento:** del {fecha_corta(datos['entrenamiento_desde'])} al {fecha_corta(datos['entrenamiento_hasta'])} ({datos['dias_entrenamiento_efectivo']} días, {datos['filas_entrenamiento']:,} filas zona-hora).
  Las primeras filas del mes no tienen el dato de «hace una semana» y se descartan.
- **Cuántos árboles:** {modelo['n_arboles']}, elegidos con una validación interna (del {fecha_corta(datos['validacion_desde'])} en adelante) y sin mirar la semana de prueba.
- **Evaluación:** del {fecha_corta(datos['prueba_desde'])} al {fecha_corta(datos['prueba_hasta'])} ({datos['filas_prueba']:,} filas zona-hora), siempre por fechas y nunca al azar, con datos que el modelo no vio al entrenarse.
- **Variables:** {', '.join(f'`{v}`' for v in modelo['variables'])}. Ninguna mira menos de 24 horas atrás, porque el pronóstico se hace el día anterior.
            """
        )

# ------------------------------------------------------------------ 2. qué tan bien funciona
with st.container(border=True):
    st.subheader(":material/query_stats: Qué tan bien funciona")
    st.caption(
        f"Evaluado en la última semana de enero ({datos['filas_prueba']:,} horas-zona que el modelo nunca vio). "
        "Error = promedio de |real − pronóstico| en viajes por hora."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Error del modelo", f"{ev['mae_modelo']:.1f} viajes/hora",
        delta=f"{ev['mejora_vs_semana_pct']:+.0f}% vs. «igual que hace una semana»",
        delta_color="inverse", border=True,
        help="Verde: el error es menor que el de la regla simple. Rojo: es mayor.",
    )
    c2.metric(
        "Cobertura del rango 10%–90%", f"{ev['cobertura_80']:.0%}",
        delta="objetivo: 80%", delta_color="off", border=True,
        help="Proporción de horas en que el valor real cayó dentro del rango pronosticado.",
    )
    c3.metric(
        "Zonas agrupadas", f"{zonas['segmentadas']}",
        delta=f"{zonas['grupos']} grupos (K-Means)", delta_color="off", border=True,
    )

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Error frente a reglas simples**")
        reglas = pd.DataFrame({
            "regla": ["Igual que ayer", "Igual que hace una semana", "Modelo (p50)"],
            "error": [ev["mae_igual_que_ayer"], ev["mae_igual_que_hace_una_semana"], ev["mae_modelo"]],
        })
        fig = go.Figure(go.Bar(
            y=reglas["regla"], x=reglas["error"], orientation="h",
            marker_color=[GRIS, GRIS, VERDE], text=reglas["error"].round(1), textposition="outside",
        ))
        fig.update_layout(xaxis_title="Viajes por hora (error promedio)", yaxis=dict(autorange="reversed"))
        st.plotly_chart(estilo(fig, 240))
    with g2:
        st.markdown("**Error según el tipo de zona**")
        orden = tipos.sort_values("mae_modelo")
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(y=orden["grupo"], x=orden["mae_modelo"], orientation="h", name="Modelo (p50)", marker_color=VERDE))
        fig2.add_trace(go.Bar(y=orden["grupo"], x=orden["mae_semana"], orientation="h", name="Igual que hace una semana", marker_color=GRIS))
        fig2.update_layout(barmode="group", xaxis_title="Viajes por hora (error promedio)", yaxis=dict(autorange="reversed"))
        st.plotly_chart(estilo(fig2, 240))

    mejora = ev["mejora_vs_semana_pct"]
    if mejora <= -10:
        frase_regla = f"El modelo le gana con claridad a «igual que hace una semana»: su error es {abs(mejora):.0f}% menor."
    elif mejora < 0:
        frase_regla = f"El modelo le gana por poco a «igual que hace una semana»: su error es solo {abs(mejora):.0f}% menor."
    else:
        frase_regla = f"El modelo **no** supera a «igual que hace una semana»: su error es {mejora:.0f}% mayor."
    cob = ev["cobertura_80"]
    if 0.75 <= cob <= 0.85:
        frase_rango = (f"Su valor principal está en el rango: el intervalo del 80% acierta {cob:.0%}, cerca de lo prometido, "
                       "y las reglas simples no entregan ningún rango.")
    elif cob < 0.75:
        frase_rango = f"El rango del 80% solo acierta {cob:.0%}: es más estrecho de lo que promete, así que conviene usarlo con cautela."
    else:
        frase_rango = f"El rango del 80% acierta {cob:.0%}: es más ancho de lo necesario, lo que puede llevar a enviar más taxis de los útiles."
    st.markdown(f"{frase_regla} {frase_rango}")

    mayor_abs = tipos.loc[tipos["mae_modelo"].idxmax()]
    mayor_rel = tipos.loc[tipos["error_relativo_pct"].idxmax()]
    st.markdown(
        f"**Dónde se equivoca más:** en viajes por hora, el error más grande está en **{mayor_abs['grupo']}** "
        f"({mayor_abs['mae_modelo']:.1f}); en proporción de su propia demanda, el grupo más difícil es **{mayor_rel['grupo']}** "
        f"({mayor_rel['error_relativo_pct']:.0f}% de sus viajes)."
    )

    with st.expander("Ver la tabla por tipo de zona y la calibración de los cuantiles", icon=":material/table:"):
        vista = tipos.rename(columns={
            "grupo": "Grupo", "zonas": "Zonas con pronóstico", "demanda_media": "Viajes por hora (promedio)",
            "mae_modelo": "Error del modelo", "mae_semana": "Error hace una semana",
            "error_relativo_pct": "Error en % de la demanda", "cobertura_80": "Cobertura del rango 80%",
        })[["Grupo", "Zonas con pronóstico", "Viajes por hora (promedio)", "Error del modelo", "Error hace una semana",
            "Error en % de la demanda", "Cobertura del rango 80%"]]
        st.dataframe(
            vista, hide_index=True,
            column_config={
                "Viajes por hora (promedio)": st.column_config.NumberColumn(format="%.1f"),
                "Error del modelo": st.column_config.NumberColumn(format="%.1f"),
                "Error hace una semana": st.column_config.NumberColumn(format="%.1f"),
                "Error en % de la demanda": st.column_config.NumberColumn(format="%.0f%%"),
                "Cobertura del rango 80%": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
            },
        )
        cal = pd.DataFrame(ev["calibracion"])
        st.markdown(
            "**Calibración:** un cuantil p debería quedar por encima de lo real en p% de las horas. "
            "Si «observado» se parece a «objetivo», el cuantil es honesto."
        )
        st.dataframe(
            cal.rename(columns={"cuantil": "Cuantil", "objetivo": "Objetivo", "observado": "Observado"}),
            hide_index=True,
            column_config={
                "Objetivo": st.column_config.NumberColumn(format="percent"),
                "Observado": st.column_config.NumberColumn(format="percent"),
            },
        )

# ------------------------------------------------------------------ 3. limitaciones
with st.container(border=True):
    st.subheader(":material/warning: Limitaciones")
    st.markdown(
        f"""
- Entrenado con **un solo mes de invierno** ({datos['dias_entrenamiento_efectivo']} días de entrenamiento efectivo): no conoce el verano, las vacaciones ni eventos como el maratón.
- Solo usa la historia de la propia demanda y el calendario (hora, día de la semana y un feriado): **no sabe de clima, conciertos ni cierres de calles**.
- Las zonas con menos de {zonas['umbral_pronostico']:,} viajes al mes no tienen pronóstico: **{zonas['pronosticadas']} de las {zonas['ciudad']} zonas** de la ciudad tienen uno, y {zonas['pronosticadas_en_manhattan']} de esas {zonas['pronosticadas']} están en Manhattan.
- El rango del 80% acierta {ev['cobertura_80']:.0%} en promedio, pero **varía por zona entre {ev['cobertura_zona_min']:.0%} y {ev['cobertura_zona_max']:.0%}**.
- Solo cubre **taxis amarillos**: no incluye taxis verdes, Uber ni Lyft, así que la demanda real de transporte es mayor que la que se ve aquí.
- La página de decisión supone que un taxi atiende un viaje por hora. Es una simplificación para poder calcular costos.
        """
    )

# ------------------------------------------------------------------ 4. usos no recomendados y a quién puede perjudicar
with st.container(border=True):
    st.subheader(":material/block: Usos no recomendados")
    st.markdown(
        f"""
- **Decidir qué conductores trabajan** o evaluar su desempeño con este pronóstico.
- **Recortar el servicio en zonas periféricas** porque «el modelo predice poca demanda»: en esos barrios se usan más otros servicios (taxis verdes, apps) que no están en estos datos. Poca demanda de taxi amarillo no significa poca necesidad de transporte.
- **Usarlo más de un día hacia adelante**: está entrenado para el día siguiente.
- **Usarlo en zonas sin pronóstico**, en otras ciudades o en otras épocas del año: no se evaluó fuera de las {zonas['pronosticadas']} zonas ni fuera de enero de 2024.
        """
    )
    st.markdown("**¿A quién podría perjudicar una mala decisión?**")
    st.markdown(
        f"""
- **Pasajeros de zonas periféricas o sin pronóstico** ({zonas['segmentadas_sin_pronostico']} zonas agrupadas no tienen pronóstico): si se recorta la flota donde parece sobrar, esperan más o se quedan sin servicio, y quienes no tienen alternativa (sin aplicación, con movilidad reducida) son los más afectados.
- **Conductores**: si se les asigna turnos con un pronóstico que falla, pasan horas sin pasajeros o pierden ingresos.
- **Operadores de la flota**: un pronóstico demasiado bajo deja pasajeros sin atender; uno demasiado alto sobra de taxis. La página de decisión pone precio a cada error para hacerlo visible.
        """
    )

# ------------------------------------------------------------------ opinión del usuario
st.divider()
st.markdown("**¿Resultó clara esta ficha?**")
valor = st.feedback("stars", key="valoracion_ficha")
if valor is not None and st.session_state.get("ultima_valoracion") != valor:
    st.session_state["ultima_valoracion"] = valor
    st.toast(f"¡Gracias por la valoración! ({valor + 1} de 5 estrellas)", icon=":material/favorite:")

st.caption("Todas las cifras de esta página salen del cuaderno (sección E) y se guardan en `data/metricas_modelo.json`.")
