import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATOS = Path(__file__).resolve().parent.parent / "data"
CSV = DATOS / "zonas_segmentadas.csv"
META = DATOS / "segmentacion_meta.json"

COLORES = ["#2D6A66", "#C97B3F", "#4C78A8", "#B23A3A", "#7A6BAE", "#8C8C3C", "#5E8C61"]
COLORES_BADGE = ["green", "orange", "blue", "red", "violet", "yellow", "gray"]

st.title("Segmentación de zonas")
st.caption(
    "K-Means agrupa las zonas por cómo se usan los taxis: a qué hora, qué tan lejos, cuánto se paga. "
    "PCA las resume en dos ejes para poder dibujarlas."
)

if not CSV.exists() or not META.exists():
    st.info(
        "Faltan los archivos de la segmentación: `zonas_segmentadas.csv` y `segmentacion_meta.json`. "
        "Se generan con el cuaderno (celda 5) y se copian en la carpeta `data/` junto a `streamlit_app.py`.",
        icon=":material/folder_off:",
    )
    st.stop()


@st.cache_data
def cargar():
    zonas = pd.read_csv(CSV)
    meta = json.loads(META.read_text(encoding="utf-8"))
    return zonas, meta


zonas, meta = cargar()
columnas_hora = [f"h{h}" for h in range(24)]
zonas["perfil_horario"] = zonas[columnas_hora].values.tolist()
grupos = [g["nombre"] for g in meta["grupos"]]
info_grupo = {g["nombre"]: g for g in meta["grupos"]}
color_de = {g: COLORES[i % len(COLORES)] for i, g in enumerate(grupos)}
badge_de = {g: COLORES_BADGE[i % len(COLORES_BADGE)] for i, g in enumerate(grupos)}

# ------------------------------------------------------------------ filtro por grupos
elegidos = st.pills("Grupos", grupos, selection_mode="multi", default=grupos)
if not elegidos:
    st.warning("Hay que elegir al menos un grupo para ver las zonas.", icon=":material/filter_alt:")
    st.stop()
visibles = zonas[zonas["grupo"].isin(elegidos)].copy()

# ------------------------------------------------------------------ una tarjeta por grupo
for inicio in range(0, len(elegidos), 4):
    fila = elegidos[inicio:inicio + 4]
    columnas = st.columns(4)
    for col, nombre in zip(columnas, fila):
        datos = zonas[zonas["grupo"] == nombre]
        with col.container(border=True):
            st.badge(nombre, color=badge_de[nombre])
            st.metric("Zonas", f"{len(datos)}", border=False)
            noche = datos["pct_22_5"].mean()                                        # promedio simple de las zonas del grupo (como la referencia)
            st.caption(
                f"{datos['viajes_dia'].sum():,.0f} viajes al día · "
                f"{datos['dist_mediana'].median():.1f} millas · "
                f"{noche:.0f}% de noche"
            )
            with st.popover("¿Qué la distingue?"):
                st.write(info_grupo[nombre]["descripcion"])

# ------------------------------------------------------------------ mapa de zonas (PCA) y perfil horario
v1, v2 = meta["varianza_pca"]
col_mapa, col_perfil = st.columns([3, 2])

with col_mapa:
    fig = px.scatter(
        visibles,
        x="pc1",
        y="pc2",
        color="grupo",
        size="viajes_dia",
        size_max=30,
        color_discrete_map=color_de,
        category_orders={"grupo": grupos},
        custom_data=["zona_id"],
        hover_name="zona",
        hover_data={"distrito": True, "viajes_dia": ":,.0f", "dist_mediana": ":.1f", "pc1": False, "pc2": False, "grupo": False},
        labels={"viajes_dia": "Viajes al día", "dist_mediana": "Distancia mediana (mi)", "distrito": "Distrito"},
    )
    fig.update_traces(marker=dict(opacity=0.8, line=dict(width=0.5, color="white")))
    fig.update_layout(
        xaxis_title=f"Componente 1 ({v1:.0%} de la variación)",
        yaxis_title=f"Componente 2 ({v2:.0%} de la variación)",
        legend=dict(orientation="h", yanchor="top", y=-0.2, x=0, title_text=""),
        margin=dict(l=10, r=10, t=10, b=10),
        height=430,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    evento = st.plotly_chart(
        fig,
        on_select="rerun",
        selection_mode=("points", "box", "lasso"),
        key="mapa_zonas",
    )
    st.caption(
        ":material/touch_app: Se pueden seleccionar zonas en el gráfico (clic, caja o lazo) para compararlas. "
        f"Los dos ejes conservan {v1 + v2:.0%} de la variación de las zonas."
    )


def ids_seleccionados(evento) -> list[int]:
    """Los zona_id de los puntos elegidos en el gráfico (viajan en custom_data)."""
    try:
        puntos = evento.selection.points
    except AttributeError:
        return []
    ids = []
    for punto in puntos:
        dato = punto.get("customdata")
        if dato is not None:
            ids.append(int(dato[0] if isinstance(dato, (list, tuple)) else dato))
    return ids


ids = [i for i in ids_seleccionados(evento) if i in set(visibles["zona_id"])]
seleccion = visibles[visibles["zona_id"].isin(ids)] if ids else visibles.iloc[0:0]

with col_perfil:
    comparadas = seleccion.nlargest(8, "viajes_dia") if len(seleccion) else visibles.nlargest(5, "viajes_dia")
    titulo = "Perfil horario de las zonas seleccionadas" if len(seleccion) else "Perfil horario de las zonas con más viajes"
    st.markdown(f"**{titulo}**")
    fig_perfil = go.Figure()
    for _, z in comparadas.iterrows():
        fig_perfil.add_trace(go.Scatter(x=list(range(24)), y=z["perfil_horario"], mode="lines", name=z["zona"],
                                        line=dict(width=2)))
    fig_perfil.update_layout(
        xaxis=dict(title="Hora del día", dtick=4, range=[0, 23]),
        yaxis=dict(title="Proporción de viajes", tickformat=".0%"),
        legend=dict(orientation="h", yanchor="top", y=-0.3, x=0, font=dict(size=10)),
        margin=dict(l=10, r=10, t=10, b=10),
        height=360,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_perfil)
    if len(seleccion) > 8:
        st.caption(f"Se muestran las 8 zonas con más viajes de las {len(seleccion)} seleccionadas.")
    elif not len(seleccion):
        st.caption("Ejemplo: al seleccionar zonas de vida nocturna y compararlas con las del centro, se ve a qué hora llega cada pico.")

# ------------------------------------------------------------------ detalle por zona
st.subheader("Detalle por zona")
detalle = (seleccion if len(seleccion) else visibles).sort_values("viajes_dia", ascending=False)
if len(seleccion):
    st.caption(f"Mostrando las {len(detalle)} zonas seleccionadas en el gráfico.")
st.dataframe(
    detalle[["zona", "distrito", "grupo", "viajes_dia", "dist_mediana", "pct_22_5", "propina_mediana", "perfil_horario"]],
    hide_index=True,
    height=min(420, 38 + 35 * len(detalle)),
    column_config={
        "zona": st.column_config.TextColumn("Zona"),
        "distrito": st.column_config.TextColumn("Distrito"),
        "grupo": st.column_config.TextColumn("Grupo"),
        "viajes_dia": st.column_config.NumberColumn("Viajes al día", format="%d"),
        "dist_mediana": st.column_config.NumberColumn("Distancia mediana", format="%.1f mi"),
        "pct_22_5": st.column_config.ProgressColumn("Viajes de noche", format="%.1f%%", min_value=0, max_value=100),
        "propina_mediana": st.column_config.NumberColumn("Propina mediana", format="$%.2f"),
        "perfil_horario": st.column_config.LineChartColumn("Perfil de 0 a 23 h"),
    },
)

# ------------------------------------------------------------------ por qué k grupos
with st.expander("¿Por qué %d grupos?" % meta["k"], icon=":material/science:"):
    st.markdown(
        "El **coeficiente de silueta** mide qué tan bien separados están los grupos: cerca de 1, cada zona "
        "se parece mucho a las de su grupo y poco a las de otros; cerca de 0, los grupos se traslapan. "
        "Se probó de 2 a 7 grupos y se eligió el valor marcado."
    )
    k_ini = sorted(int(k) for k in meta["silueta"])
    tabla = pd.DataFrame({"k": k_ini, "silueta": [meta["silueta"][str(k)] for k in k_ini]})
    tabla["elegido"] = tabla["k"].map(lambda k: "Elegido" if k == meta["k"] else "Otros")
    fig_silueta = px.bar(
        tabla, x="k", y="silueta", color="elegido",
        color_discrete_map={"Elegido": "#2D6A66", "Otros": "#B8C4C2"},
        labels={"k": "Número de grupos (k)", "silueta": "Coeficiente de silueta"},
    )
    fig_silueta.update_layout(
        showlegend=False, height=260, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(dtick=1), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_silueta)
    st.markdown(
        f"Las variables se **escalaron** (media 0 y desviación 1) para que ninguna pese más solo por sus unidades "
        f"(millas, dólares, porcentajes). Para dibujar las zonas, PCA resume las {len(meta['variables'])} variables en dos ejes: "
        f"el primero conserva {v1:.0%} de la variación y el segundo {v2:.0%}."
    )
