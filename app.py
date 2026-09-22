import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from supabase import create_client, Client
from engine import generar_malla_semanal, limpiar_posicion, registrar_incidencia_diaria

st.set_page_config(page_title="Sistema WFM - Control de Tareo", page_icon="⚙️", layout="wide")

SUPABASE_URL = "https://vsnyqynjaxdmofyewfcq.supabase.co"
SUPABASE_KEY = "sb_publishable__wmHvw9dfAcu-o78te3iMg_9JqpAb_P"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("⚙️ Sistema WFM - Panel de Administración")

with st.sidebar:
    st.header("⚡ Acciones Rápidas")
    fecha_seleccionada = st.date_input("Inicio de semana a programar:", date.today())
    
    if st.button("🚀 Recalcular Malla Semanal", type="primary"):
        with st.spinner("Generando matriz con cobertura extrema..."):
            generar_malla_semanal(fecha_seleccionada)
            st.success("¡Malla actualizada correctamente!")
            st.cache_data.clear()

tab1, tab2, tab3, tab4 = st.tabs([
    "📅 Matriz y Reporte Ejecutivo", 
    "🏢 Requerimiento por Sede",
    "🚨 Incidencias y Reemplazos", 
    "👥 Gestión de Personal y Sedes"
])

# --- TAB 1: MATRIZ Y REPORTE EJECUTIVO ---
with tab1:
    dias_semana = [str(fecha_seleccionada + timedelta(days=i)) for i in range(7)]

    @st.cache_data(ttl=5)
    def cargar_matriz_tareo(f_inicio_str, f_fin_str, lista_dias):
        res = supabase.table("tareo_programado")\
            .select("fecha, turno, sede, es_hhee, estado, colaboradores(nombre, posicion)")\
            .gte("fecha", f_inicio_str)\
            .lte("fecha", f_fin_str)\
            .execute()
        
        if not res.data: return pd.DataFrame()

        filas = []
        for row in res.data:
            nombre_sede = row.get('sede', 'Sede 1')
            turno_base = "D" if row['turno'] == "Día" else "N"
            estado = row.get('estado')
            
            if estado in ['FALTA', 'DM', 'PERMISO']:
                codigo_turno = f"❌ {estado}"
            else:
                if row.get('es_hhee'):
                    codigo_turno = f"{turno_base} ({nombre_sede}) [HE]"
                else:
                    codigo_turno = f"{turno_base} ({nombre_sede})"

            filas.append({
                "Colaborador": row['colaboradores']['nombre'],
                "Posición": limpiar_posicion(row['colaboradores']['posicion']),
                "Fecha": str(row['fecha']),
                "Turno": codigo_turno
            })
        
        df = pd.DataFrame(filas)
        matriz = df.pivot_table(index=["Colaborador", "Posición"], columns="Fecha", values="Turno", aggfunc="first").fillna("L")
        matriz = matriz.reindex(columns=lista_dias, fill_value="L")
        return matriz

    f_ini_s = str(fecha_seleccionada)
    f_fin_s = str(fecha_seleccionada + timedelta(days=6))
    matriz_df = cargar_matriz_tareo(f_ini_s, f_fin_s, dias_semana)

    col_title, col_btn_refresh = st.columns([4, 1])
    with col_title:
        st.subheader("📊 Cuadrante Semanal")
    with col_btn_refresh:
        if st.button("🔄 Actualizar Vista"):
            st.cache_data.clear()
            st.rerun()
            
    if matriz_df.empty:
        st.info("Haz clic en **'🚀 Recalcular Malla Semanal'** para generar el cuadrante.")
    else:
        st.dataframe(matriz_df, use_container_width=True)
        csv = matriz_df.to_csv().encode('utf-8')
        st.download_button("📥 Descargar Reporte CSV", csv, f"tareo_{fecha_seleccionada}.csv", "text/csv")

    st.divider()

    st.subheader("👔 Reporte Ejecutivo para Jefatura")
    try:
        res_dem = supabase.table("demanda_operativa").select("*").execute().data
        res_prog = supabase.table("tareo_programado")\
            .select("sede, turno, es_hhee, estado, colaboradores(posicion)")\
            .gte("fecha", f_ini_s).lte("fecha", f_fin_s).execute().data

        if res_dem:
            df_dem = pd.DataFrame(res_dem)
            conteo_prog = {}
            conteo_hhee = {}  
            total_hhee = 0
            if res_prog:
                for p in res_prog:
                    if p.get('estado') in ['FALTA', 'DM', 'PERMISO']: continue
                    
                    s = p['sede']
                    t = p['turno']
                    pos = limpiar_posicion(p['colaboradores']['posicion'])
                    key = (s, pos, t)
                    
                    conteo_prog[key] = conteo_prog.get(key, 0) + 1
                    
                    if p.get('es_hhee'): 
                        conteo_hhee[key] = conteo_hhee.get(key, 0) + 1
                        total_hhee += 1

            reporte_filas = []
            total_req_sem, total_prog_sem = 0, 0

            for _, r in df_dem.iterrows():
                s, pos, t, req_diario = r['sede'], limpiar_posicion(r['posicion']), r['turno'], r['cantidad']
                req_semanal = req_diario * 7
                
                prog_semanal = conteo_prog.get((s, pos, t), 0)
                hhee_semanal = conteo_hhee.get((s, pos, t), 0)
                deficit_semanal = req_semanal - prog_semanal

                total_req_sem += req_semanal
                total_prog_sem += prog_semanal

                estado = f"⚠️ Faltan {deficit_semanal}" if deficit_semanal > 0 else ("✅ Ok" if deficit_semanal == 0 else "🔵 Exceso")

                reporte_filas.append({
                    "Sede": s, "Cargo": pos, "Turno": t,
                    "Req. Diario": req_diario, "Req. Semana": req_semanal,
                    "Prog. Real": prog_semanal, "HHEE (Extras)": hhee_semanal, 
                    "Déficit Real": deficit_semanal if deficit_semanal > 0 else 0, "Estado": estado
                })

            # --- MÉTRICAS KPI ---
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Turnos Requeridos", total_req_sem)
            kpi2.metric("Turnos Normales", total_prog_sem - total_hhee)
            kpi3.metric("Horas Extras [HE]", total_hhee, delta_color="off")
            deficit_total = total_req_sem - total_prog_sem
            kpi4.metric("Déficit Faltante", f"{deficit_total}", delta=-deficit_total if deficit_total > 0 else 0, delta_color="inverse")

            # --- TABLA EJECUTIVA ---
            df_reporte = pd.DataFrame(reporte_filas)
            st.dataframe(df_reporte, use_container_width=True)

            # =========================================================
            # NUEVO: GRÁFICOS INTERACTIVOS (COBERTURA Y HHEE POR SEDE)
            # =========================================================
            if not df_reporte.empty:
                st.divider()
                st.subheader("📈 Análisis Gráfico de Cobertura y Presupuesto por Sede")
                
                # Agrupar los datos de la tabla por 'Sede'
                df_sede = df_reporte.groupby('Sede', as_index=False)[['Req. Semana', 'Prog. Real', 'HHEE (Extras)', 'Déficit Real']].sum()
                # Calcular Turnos Normales = Total Programado - Horas Extras
                df_sede['Turnos Normales'] = df_sede['Prog. Real'] - df_sede['HHEE (Extras)']

                col_graf1, col_graf2 = st.columns(2)

                with col_graf1:
                    # Gráfico 1: Turnos Programados vs Déficit Faltante
                    df_g1 = df_sede[['Sede', 'Prog. Real', 'Déficit Real']].melt(id_vars='Sede', var_name='Indicador', value_name='Turnos')
                    fig1 = px.bar(df_g1, x='Sede', y='Turnos', color='Indicador', 
                                  title='Nivel de Cobertura vs Déficit',
                                  color_discrete_map={'Prog. Real': '#198754', 'Déficit Real': '#dc3545'}, 
                                  text_auto=True)
                    fig1.update_layout(barmode='stack')
                    st.plotly_chart(fig1, use_container_width=True)

                with col_graf2:
                    # Gráfico 2: Composición del Costo (Turnos Normales vs Horas Extras)
                    df_g2 = df_sede[['Sede', 'Turnos Normales', 'HHEE (Extras)']].melt(id_vars='Sede', var_name='Tipo de Turno', value_name='Cantidad')
                    fig2 = px.bar(df_g2, x='Sede', y='Cantidad', color='Tipo de Turno', 
                                  title='Composición Operativa: Normales vs HHEE',
                                  color_discrete_map={'Turnos Normales': '#0d6efd', 'HHEE (Extras)': '#ffc107'}, 
                                  text_auto=True)
                    fig2.update_layout(barmode='stack')
                    st.plotly_chart(fig2, use_container_width=True)

        else:
            st.info("Configura los requerimientos en la pestaña **'🏢 Requerimiento por Sede'**.")
    except Exception as e:
        pass

# --- TAB 2 ---
with tab2:
    st.subheader("🏢 Definir Cuántos Trabajadores Requiere Cada Sede")
    try:
        res_sedes = supabase.table("sedes").select("nombre").eq("activa", True).execute().data
        sedes_opt = [s['nombre'] for s in res_sedes] if res_sedes else ["Sede 1", "Sede 2", "Sede 3"]
    except Exception: sedes_opt = ["Sede 1"]

    res_colabs = supabase.table("colaboradores").select("posicion").eq("activo", True).execute().data
    posiciones_opt = sorted(list(set(limpiar_posicion(c['posicion']) for c in res_colabs if c.get('posicion')))) if res_colabs else []

    if posiciones_opt:
        c1, c2, c3, c4 = st.columns(4)
        sede_sel = c1.selectbox("Seleccionar Sede:", sedes_opt)
        pos_sel = c2.selectbox("Cargo / Posición:", posiciones_opt)
        turno_sel = c3.selectbox("Turno:", ["Día", "Noche"])
        cant_sel = c4.number_input("Personal Requerido:", min_value=0, max_value=20, value=1)

        if st.button("💾 Guardar Requerimiento"):
            supabase.table("demanda_operativa").upsert(
                {"sede": sede_sel, "posicion": pos_sel, "turno": turno_sel, "cantidad": cant_sel},
                on_conflict="sede,posicion,turno"
            ).execute()
            st.success("Guardado.")
            st.cache_data.clear()

        st.divider()
        col_tit, col_btn = st.columns([3, 1])
        with col_tit: st.subheader("📋 Cobertura Actual Configurada")
        with col_btn:
            if st.button("🗑️ Vaciar Demanda"):
                supabase.table("demanda_operativa").delete().neq("id", 0).execute()
                st.cache_data.clear()
                st.rerun()

        try:
            res_demanda = supabase.table("demanda_operativa").select("*").execute().data
            if res_demanda: st.dataframe(pd.DataFrame(res_demanda)[["sede", "posicion", "turno", "cantidad"]], use_container_width=True)
        except: pass

# --- TAB 3: GESTIÓN DE INCIDENCIAS DIARIAS Y REEMPLAZOS ---
with tab3:
    st.subheader("🚨 Registrar Faltas, DM o Permisos (Día a Día)")
    st.markdown("Selecciona el día para ver quiénes están programados hoy y reportar si no asistieron.")
    
    c_fecha, c_resto = st.columns([1, 2])
    fecha_incidencia = c_fecha.date_input("Seleccionar Fecha del Incidente:", date.today())
    
    res_turnos = supabase.table("tareo_programado").select("colaborador_id, turno, sede, estado, colaboradores(nombre, posicion)").eq("fecha", str(fecha_incidencia)).execute().data
    turnos_activos = [t for t in res_turnos if t.get('estado') not in ['FALTA', 'DM', 'PERMISO']] if res_turnos else []
    
    if turnos_activos:
        opciones_hoy = {f"{t['colaboradores']['nombre']} - {t['turno']} ({t['sede']})": t['colaborador_id'] for t in turnos_activos}
        
        with st.form("form_incidencia_diaria", clear_on_submit=True):
            colab_sel = st.selectbox("Colaborador que Ausentó:", list(opciones_hoy.keys()))
            motivo = st.selectbox("Motivo de la Ausencia:", ["FALTA", "DM", "PERMISO"])
            reemplazar = st.checkbox("¿Buscar reemplazo automáticamente? (Se asignará como Hora Extra)", value=True)
            
            if st.form_submit_button("Registrar Ausencia e Iniciar Reemplazo"):
                id_c = opciones_hoy[colab_sel]
                turnos_update = supabase.table("tareo_programado").select("id").eq("fecha", str(fecha_incidencia)).eq("colaborador_id", id_c).execute().data
                if turnos_update:
                    st.cache_data.clear()
                    success, msg = registrar_incidencia_diaria(fecha_incidencia, id_c, motivo, reemplazar)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.error("No se encontró el turno para actualizar.")
                
    else:
        st.info("No hay turnos programados activos para esta fecha.")

    st.divider()

    st.subheader("📅 Bloquear Fechas Futuras (Vacaciones)")
    res_colab = supabase.table("colaboradores").select("id, nombre, posicion").eq("activo", True).execute()
    opc_colab = {f"{c['nombre']} ({limpiar_posicion(c['posicion'])})": c['id'] for c in res_colab.data} if res_colab.data else {}
    
    if opc_colab:
        colab_vaca = st.selectbox("Seleccionar Colaborador para Vacaciones:", list(opc_colab.keys()))
        c1, c2 = st.columns(2)
        f_ini = c1.date_input("Inicio:")
        f_fin = c2.date_input("Fin:")
        if st.button("💾 Guardar Vacaciones"):
            supabase.table("restricciones_fechas").insert({"colaborador_id": opc_colab[colab_vaca], "fecha_inicio": str(f_ini), "fecha_fin": str(f_fin), "tipo": "VACACIONES"}).execute()
            st.success("Vacaciones guardadas.")
            st.cache_data.clear()

# --- TAB 4 ---
with tab4:
    col_izq, col_der = st.columns(2)
    with col_izq:
        st.subheader("👨‍💼 Colaboradores")
        with st.expander("📁 Carga Masiva (Excel/CSV)"):
            archivo = st.file_uploader("Selecciona archivo:", type=["xlsx", "csv"])
            if archivo and st.button("📥 Importar Lista"):
                df = pd.read_csv(archivo) if archivo.name.endswith('.csv') else pd.read_excel(archivo)
                df.columns = [str(c).strip() for c in df.columns]
                regs = []
                for _, row in df.iterrows():
                    if pd.isna(row.iloc[0]) or pd.isna(row.iloc[1]): continue
                    try: cod = str(int(float(row.iloc[0])))
                    except: cod = str(row.iloc[0]).strip()
                    pos = limpiar_posicion(str(row.iloc[2])) if not pd.isna(row.iloc[2]) else "General"
                    regs.append({"codigo": cod, "nombre": str(row.iloc[1]).strip(), "posicion": pos, "he_acumuladas": 0.0, "dias_pendientes_recuperacion": 0, "activo": True})
                if regs:
                    supabase.table("colaboradores").insert(regs).execute()
                    st.success(f"¡{len(regs)} registrados!")
                    st.cache_data.clear()
        
        with st.expander("➕ Agregar Manual"):
            with st.form("f_emp", clear_on_submit=True):
                cod, nom, pos = st.text_input("Código:"), st.text_input("Nombre:"), st.text_input("Posición:")
                if st.form_submit_button("Guardar") and nom:
                    supabase.table("colaboradores").insert({"codigo": cod, "nombre": nom, "posicion": limpiar_posicion(pos), "he_acumuladas": 0, "dias_pendientes_recuperacion": 0, "activo": True}).execute()
                    st.cache_data.clear()
        
        with st.expander("🗑️ Dar de Baja"):
            res_activos = supabase.table("colaboradores").select("id, nombre").eq("activo", True).execute().data
            if res_activos:
                opts = {c['nombre']: c['id'] for c in res_activos}
                sel = st.selectbox("Colaborador:", list(opts.keys()))
                if st.button("🚫 Dar de Baja"):
                    supabase.table("colaboradores").update({"activo": False}).eq("id", opts[sel]).execute()
                    st.cache_data.clear()

    with col_der:
        st.subheader("🏢 Sedes")
        with st.expander("➕ Agregar Sede"):
            with st.form("f_sede", clear_on_submit=True):
                nom_sede = st.text_input("Sede:")
                if st.form_submit_button("Guardar") and nom_sede:
                    supabase.table("sedes").insert({"nombre": nom_sede, "activa": True}).execute()
                    st.cache_data.clear()
        with st.expander("🗑️ Eliminar Sede"):
            try:
                res_sedes = supabase.table("sedes").select("id, nombre").eq("activa", True).execute().data
                if res_sedes:
                    opts_s = {s['nombre']: s['id'] for s in res_sedes}
                    sel_s = st.selectbox("Sede:", list(opts_s.keys()))
                    if st.button("🗑️ Eliminar"):
                        supabase.table("sedes").update({"activa": False}).eq("id", opts_s[sel_s]).execute()
                        st.cache_data.clear()
            except: pass