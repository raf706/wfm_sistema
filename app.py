import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client
from engine import generar_malla_semanal

# 1. Configuración de la plataforma web
st.set_page_config(page_title="Sistema WFM - Tareo & Incidencias", page_icon="⚙️", layout="wide")

# 2. Conexión con tu clave ya integrada
SUPABASE_URL = "https://vsnyqynjaxdmofyewfcq.supabase.co"
SUPABASE_KEY = "sb_publishable__wmHvw9dfAcu-o78te3iMg_9JqpAb_P"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("⚙️ Sistema WFM - Control de Tareo e Incidencias")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("⚡ Acciones Rápidas")
    fecha_seleccionada = st.date_input("Inicio de semana a programar:", date.today())
    
    if st.button("🚀 Recalcular Malla Semanal", type="primary"):
        with st.spinner("Ejecutando motor de equidad 4x3 y restricciones..."):
            generar_malla_semanal(fecha_seleccionada)
            st.success("¡Malla actualizada correctamente!")
            st.cache_data.clear()

# --- PESTAÑAS PRINCIPALES ---
tab1, tab2 = st.tabs(["📅 Matriz de Tareo", "🚨 Registrar Incidencia / Vacaciones"])

# --- TAB 1: MATRIZ DE TAREO ---
with tab1:
    @st.cache_data(ttl=5)
    def cargar_matriz_tareo():
        res = supabase.table("tareo_programado").select("fecha, turno, colaboradores(nombre, posicion)").execute()
        if not res.data:
            return pd.DataFrame()

        filas = []
        for row in res.data:
            codigo_turno = "D" if row['turno'] == "Día" else ("N" if row['turno'] == "Noche" else "L")
            filas.append({
                "Colaborador": row['colaboradores']['nombre'],
                "Posición": row['colaboradores']['posicion'],
                "Fecha": row['fecha'],
                "Turno": codigo_turno
            })
        
        df = pd.DataFrame(filas)
        matriz = df.pivot_table(
            index=["Colaborador", "Posición"], 
            columns="Fecha", 
            values="Turno", 
            aggfunc="first"
        ).fillna("L")
        return matriz

    matriz_df = cargar_matriz_tareo()
    if matriz_df.empty:
        st.info("Haz clic en **'🚀 Recalcular Malla Semanal'** para generar el cuadrante.")
    else:
        st.subheader("Cuadrante Semanal (Día / Noche / Libre)")
        st.dataframe(matriz_df, use_container_width=True)
        
        csv = matriz_df.to_csv().encode('utf-8')
        st.download_button("📥 Descargar Reporte CSV", csv, f"tareo_{date.today()}.csv", "text/csv")

# --- TAB 2: REGISTRO DE INCIDENCIAS ---
with tab2:
    st.subheader("Registrar Bloqueo por Vacaciones, DM o Incidencia")
    
    # Traer colaboradores activos desde Supabase
    res_colab = supabase.table("colaboradores").select("id, nombre, posicion").eq("activo", True).execute()
    opciones_colab = {f"{c['nombre']} (Posición {c['posicion']})": c['id'] for c in res_colab.data} if res_colab.data else {}
    
    if opciones_colab:
        colab_sel = st.selectbox("Seleccionar Colaborador:", list(opciones_colab.keys()))
        tipo_incidencia = st.selectbox("Tipo de Incidencia:", ["VACACIONES", "DM", "DESCANSO_SOLICITADO"])
        
        c1, c2 = st.columns(2)
        fecha_inicio_inc = c1.date_input("Fecha Inicio:", date.today())
        fecha_fin_inc = c2.date_input("Fecha Fin:", date.today())
        
        if st.button("💾 Guardar Restricción"):
            colab_id = opciones_colab[colab_sel]
            data_incidencia = {
                "colaborador_id": colab_id,
                "fecha_inicio": str(fecha_inicio_inc),
                "fecha_fin": str(fecha_fin_inc),
                "tipo": tipo_incidencia
            }
            supabase.table("restricciones_fechas").insert(data_incidencia).execute()
            st.success(f"Restricción registrada para {colab_sel}. ¡Recalcula la malla para ver los reemplazos!")
    else:
        st.warning("No hay colaboradores disponibles en la base de datos.")