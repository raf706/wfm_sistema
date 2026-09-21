import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client
from engine import generar_malla_semanal

# 1. Configuración de la plataforma web
st.set_page_config(page_title="Sistema WFM - Control de Tareo", page_icon="⚙️", layout="wide")

# 2. Conexión a Supabase
SUPABASE_URL = "https://vsnyqynjaxdmofyewfcq.supabase.co"
SUPABASE_KEY = "sb_publishable__wmHvw9dfAcu-o78te3iMg_9JqpAb_P"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("⚙️ Sistema WFM - Panel de Administración")

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
tab1, tab2, tab3 = st.tabs([
    "📅 Matriz de Tareo", 
    "🚨 Registrar Incidencia / Vacaciones", 
    "👥 Gestión de Personal y Sedes"
])

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
            st.success(f"Restricción registrada para {colab_sel}.")
            st.cache_data.clear()
    else:
        st.warning("No hay colaboradores disponibles.")

# --- TAB 3: GESTIÓN DE PERSONAL Y SEDES ---
with tab3:
    col_izq, col_der = st.columns(2)

    # --- SECCIÓN COLABORADORES ---
    with col_izq:
        st.subheader("👨‍💼 Gestión de Colaboradores")
        
        with st.expander("➕ Agregar Nuevo Colaborador", expanded=True):
            with st.form("form_nuevo_colab", clear_on_submit=True):
                nuevo_codigo = st.text_input("Código (ej. EMP010):")
                nuevo_nombre = st.text_input("Nombre Completo:")
                nueva_posicion = st.selectbox("Posición / Perfil:", ["A", "B", "C"])
                
                btn_agregar_emp = st.form_submit_button("Guardar Colaborador")
                
                if btn_agregar_emp:
                    if nuevo_codigo and nuevo_nombre:
                        nuevo_emp = {
                            "codigo": nuevo_codigo,
                            "nombre": nuevo_nombre,
                            "posicion": nueva_posicion,
                            "he_acumuladas": 0.0,
                            "dias_pendientes_recuperacion": 0,
                            "activo": True
                        }
                        supabase.table("colaboradores").insert(nuevo_emp).execute()
                        st.success(f"✅ {nuevo_nombre} registrado correctamente.")
                        st.cache_data.clear()
                    else:
                        st.error("Por favor completa el código y el nombre.")

        with st.expander("🗑️ Desactivar / Eliminar Colaborador"):
            res_activos = supabase.table("colaboradores").select("id, nombre, codigo").eq("activo", True).execute()
            list_activos = {f"[{c['codigo']}] {c['nombre']}": c['id'] for c in res_activos.data} if res_activos.data else {}
            
            if list_activos:
                emp_a_eliminar = st.selectbox("Seleccionar Colaborador a dar de baja:", list(list_activos.keys()))
                if st.button("🚫 Dar de Baja Colaborador"):
                    id_emp = list_activos[emp_a_eliminar]
                    # Soft delete (Desactivar) para no romper el historial del tareo
                    supabase.table("colaboradores").update({"activo": False}).eq("id", id_emp).execute()
                    st.warning(f"{emp_a_eliminar} ha sido dado de baja.")
                    st.cache_data.clear()
            else:
                st.info("No hay colaboradores activos.")

    # --- SECCIÓN SEDES ---
    with col_der:
        st.subheader("🏢 Gestión de Sedes")
        
        with st.expander("➕ Agregar Nueva Sede", expanded=True):
            with st.form("form_nueva_sede", clear_on_submit=True):
                nombre_sede = st.text_input("Nombre de la Sede (ej. Sede 4):")
                btn_agregar_sede = st.form_submit_button("Guardar Sede")
                
                if btn_agregar_sede:
                    if nombre_sede:
                        supabase.table("sedes").insert({"nombre": nombre_sede, "activa": True}).execute()
                        st.success(f"✅ {nombre_sede} creada exitosamente.")
                        st.cache_data.clear()
                    else:
                        st.error("Ingresa el nombre de la sede.")

        with st.expander("🗑️ Eliminar Sede"):
            try:
                res_sedes = supabase.table("sedes").select("id, nombre").eq("activa", True).execute()
                list_sedes = {s['nombre']: s['id'] for s in res_sedes.data} if res_sedes.data else {}
                
                if list_sedes:
                    sede_a_eliminar = st.selectbox("Seleccionar Sede a Eliminar:", list(list_sedes.keys()))
                    if st.button("🗑️ Eliminar Sede Seleccionada"):
                        id_sede = list_sedes[sede_a_eliminar]
                        supabase.table("sedes").update({"activa": False}).eq("id", id_sede).execute()
                        st.warning(f"{sede_a_eliminar} eliminada.")
                        st.cache_data.clear()
                else:
                    st.info("No hay sedes activas.")
            except Exception:
                st.info("Crea la tabla 'sedes' en Supabase para habilitar este módulo.")