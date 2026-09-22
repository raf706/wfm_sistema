import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client
from engine import generar_malla_semanal, normalizar_posicion

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
tab1, tab2, tab3, tab4 = st.tabs([
    "📅 Matriz de Tareo", 
    "🏢 Requerimiento por Sede",
    "🚨 Registrar Incidencia / Vacaciones", 
    "👥 Gestión de Personal y Sedes"
])

# --- TAB 1: MATRIZ DE TAREO ---
with tab1:
    @st.cache_data(ttl=5)
    def cargar_matriz_tareo():
        res = supabase.table("tareo_programado").select("fecha, turno, sede, colaboradores(nombre, posicion)").execute()
        if not res.data:
            return pd.DataFrame()

        filas = []
        for row in res.data:
            # Mostramos el turno junto con la sede asignada
            nombre_sede = row.get('sede', 'Sede 1')
            if row['turno'] == "Día":
                codigo_turno = f"D ({nombre_sede})"
            elif row['turno'] == "Noche":
                codigo_turno = f"N ({nombre_sede})"
            else:
                codigo_turno = "L"

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
        st.subheader("Cuadrante Semanal (Turno y Sede Asignada)")
        st.dataframe(matriz_df, use_container_width=True)
        
        csv = matriz_df.to_csv().encode('utf-8')
        st.download_button("📥 Descargar Reporte CSV", csv, f"tareo_{date.today()}.csv", "text/csv")

# --- TAB 2: CONFIGURACIÓN DE REQUERIMIENTOS POR SEDE ---
with tab2:
    st.subheader("🏢 Definir Cuántos Trabajadores Requiere Cada Sede")
    st.markdown("Establece la cantidad de personal necesaria por cargo, sede y turno (Día / Noche).")

    # Obtener sedes y posiciones únicas
    try:
        res_sedes = supabase.table("sedes").select("nombre").eq("activa", True).execute().data
        sedes_opt = [s['nombre'] for s in res_sedes] if res_sedes else ["Sede 1", "Sede 2", "Sede 3"]
    except Exception:
        sedes_opt = ["Sede 1", "Sede 2", "Sede 3"]

    res_colabs = supabase.table("colaboradores").select("posicion").eq("activo", True).execute().data
    posiciones_opt = sorted(list(set(normalizar_posicion(c['posicion']) for c in res_colabs if c.get('posicion')))) if res_colabs else []

    if posiciones_opt:
        c1, c2, c3, c4 = st.columns(4)
        sede_sel = c1.selectbox("Seleccionar Sede:", sedes_opt)
        pos_sel = c2.selectbox("Cargo / Posición:", posiciones_opt)
        turno_sel = c3.selectbox("Turno:", ["Día", "Noche"])
        cant_sel = c4.number_input("Personal Requerido:", min_value=0, max_value=20, value=1)

        if st.button("💾 Guardar Requerimiento"):
            # Insertar o actualizar requerimiento
            supabase.table("demanda_operativa").upsert(
                {"sede": sede_sel, "posicion": pos_sel, "turno": turno_sel, "cantidad": cant_sel},
                on_conflict="sede,posicion,turno"
            ).execute()
            st.success(f"✅ Requerimiento guardado: {cant_sel} {pos_sel} para {sede_sel} en turno {turno_sel}.")
            st.cache_data.clear()

        st.divider()
        st.subheader("📋 Cobertura Actual Configurada")
        try:
            res_demanda = supabase.table("demanda_operativa").select("*").execute().data
            if res_demanda:
                df_demanda = pd.DataFrame(res_demanda)[["sede", "posicion", "turno", "cantidad"]]
                df_demanda.columns = ["Sede", "Posición / Cargo", "Turno", "Personal Requerido"]
                st.dataframe(df_demanda, use_container_width=True)
            else:
                st.info("Aún no has configurado requerimientos específicos.")
        except Exception:
            st.info("Crea la tabla 'demanda_operativa' en Supabase para visualizar el resumen.")
    else:
        st.warning("Primero debes importar o registrar colaboradores para definir la demanda por cargo.")

# --- TAB 3: REGISTRO DE INCIDENCIAS ---
with tab3:
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

# --- TAB 4: GESTIÓN DE PERSONAL Y SEDES ---
with tab4:
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.subheader("👨‍💼 Gestión de Colaboradores")
        
        with st.expander("📁 Carga Masiva desde Excel / CSV", expanded=True):
            st.markdown("Subir el archivo Excel (.xlsx o .csv) con la lista de colaboradores.")
            archivo_excel = st.file_uploader("Selecciona tu archivo Excel (.xlsx o .csv):", type=["xlsx", "csv"])
            
            if archivo_excel is not None:
                try:
                    if archivo_excel.name.endswith('.csv'):
                        df_cargado = pd.read_csv(archivo_excel)
                    else:
                        df_cargado = pd.read_excel(archivo_excel)
                    
                    df_cargado.columns = [str(c).strip() for c in df_cargado.columns]
                    st.write("Vista previa:")
                    st.dataframe(df_cargado.head(5))
                    
                    if st.button("📥 Importar Lista Completa"):
                        nuevos_registros = []
                        for _, row in df_cargado.iterrows():
                            raw_codigo = row.iloc[0]
                            raw_nombre = row.iloc[1]
                            raw_posicion = row.iloc[2]

                            if pd.isna(raw_codigo) or pd.isna(raw_nombre): continue

                            try:
                                val_codigo = str(int(float(raw_codigo))).strip()
                            except ValueError:
                                val_codigo = str(raw_codigo).strip()

                            val_nombre = str(raw_nombre).strip()
                            val_posicion = str(raw_posicion).strip() if not pd.isna(raw_posicion) else "General"
                            
                            nuevos_registros.append({
                                "codigo": val_codigo,
                                "nombre": val_nombre,
                                "posicion": val_posicion,
                                "he_acumuladas": 0.0,
                                "dias_pendientes_recuperacion": 0,
                                "activo": True
                            })
                        
                        if nuevos_registros:
                            supabase.table("colaboradores").insert(nuevos_registros).execute()
                            st.success(f"✅ ¡Se registraron {len(nuevos_registros)} colaboradores!")
                            st.cache_data.clear()
                except Exception as e:
                    st.error(f"Error al procesar el archivo. Detalle: {e}")

        with st.expander("➕ Agregar Manualmente"):
            with st.form("form_nuevo_colab", clear_on_submit=True):
                nuevo_codigo = st.text_input("Código:")
                nuevo_nombre = st.text_input("Nombre Completo:")
                nueva_posicion = st.text_input("Posición:")
                btn_agregar_emp = st.form_submit_button("Guardar Colaborador")
                
                if btn_agregar_emp and nuevo_codigo and nuevo_nombre:
                    supabase.table("colaboradores").insert({
                        "codigo": nuevo_codigo, "nombre": nuevo_nombre, "posicion": nueva_posicion,
                        "he_acumuladas": 0.0, "dias_pendientes_recuperacion": 0, "activo": True
                    }).execute()
                    st.success(f"✅ {nuevo_nombre} registrado.")
                    st.cache_data.clear()

        with st.expander("🗑️ Dar de Baja Colaborador"):
            res_activos = supabase.table("colaboradores").select("id, nombre, codigo").eq("activo", True).execute()
            list_activos = {f"[{c['codigo']}] {c['nombre']}": c['id'] for c in res_activos.data} if res_activos.data else {}
            
            if list_activos:
                emp_a_eliminar = st.selectbox("Seleccionar Colaborador:", list(list_activos.keys()))
                if st.button("🚫 Dar de Baja"):
                    supabase.table("colaboradores").update({"activo": False}).eq("id", list_activos[emp_a_eliminar]).execute()
                    st.warning(f"{emp_a_eliminar} ha sido dado de baja.")
                    st.cache_data.clear()

    with col_der:
        st.subheader("🏢 Gestión de Sedes")
        
        with st.expander("➕ Agregar Nueva Sede", expanded=True):
            with st.form("form_nueva_sede", clear_on_submit=True):
                nombre_sede = st.text_input("Nombre de la Sede:")
                btn_agregar_sede = st.form_submit_button("Guardar Sede")
                
                if btn_agregar_sede and nombre_sede:
                    supabase.table("sedes").insert({"nombre": nombre_sede, "activa": True}).execute()
                    st.success(f"✅ {nombre_sede} creada.")
                    st.cache_data.clear()

        with st.expander("🗑️ Eliminar Sede"):
            try:
                res_sedes = supabase.table("sedes").select("id, nombre").eq("activa", True).execute()
                list_sedes = {s['nombre']: s['id'] for s in res_sedes.data} if res_sedes.data else {}
                
                if list_sedes:
                    sede_a_eliminar = st.selectbox("Seleccionar Sede:", list(list_sedes.keys()))
                    if st.button("🗑️ Eliminar Sede"):
                        supabase.table("sedes").update({"activa": False}).eq("id", list_sedes[sede_a_eliminar]).execute()
                        st.warning(f"{sede_a_eliminar} eliminada.")
                        st.cache_data.clear()
            except Exception:
                st.info("Crea la tabla 'sedes' en Supabase.")