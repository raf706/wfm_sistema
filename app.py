import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from supabase import create_client, Client
from engine import generar_malla_semanal, limpiar_posicion, registrar_incidencia_diaria
import os

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(page_title="Tareo de Operaciones - Fargoline", page_icon="📦", layout="wide")

# CONEXIÓN A BASE DE DATOS
SUPABASE_URL = "https://vsnyqynjaxdmofyewfcq.supabase.co"
SUPABASE_KEY = "sb_publishable__wmHvw9dfAcu-o78te3iMg_9JqpAb_P"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================================================================
# 2. SISTEMA DE SEGURIDAD (LOGIN CONECTADO A BASE DE DATOS)
# =========================================================================
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.write(""); st.write("")
        if os.path.exists("logo.png.png"): st.image("logo.png.png", width=220)
        elif os.path.exists("logo.png"): st.image("logo.png", width=220)
        
        st.title("🔒 Acceso al Sistema")
        usuario = st.text_input("👤 Usuario")
        clave = st.text_input("🔑 Contraseña", type="password")
        
        if st.button("Ingresar", type="primary", use_container_width=True):
            try:
                res_user = supabase.table("usuarios").select("*").eq("id", 1).execute()
                if res_user.data:
                    db_usuario = res_user.data[0]['usuario']
                    db_clave = res_user.data[0]['clave']
                    
                    if usuario == db_usuario and clave == db_clave:
                        st.session_state.autenticado = True
                        st.rerun()
                    else:
                        st.error("❌ Usuario o contraseña incorrectos")
                else:
                    st.error("⚠️ No se encontró la tabla de usuarios en Supabase.")
            except Exception as e:
                st.error("⚠️ Error de conexión.")
    
    st.stop()

# =========================================================================
# 3. APLICACIÓN PRINCIPAL
# =========================================================================
col_logo, col_title = st.columns([2, 8])
with col_logo:
    if os.path.exists("logo.png.png"): st.image("logo.png.png", width=220)
    elif os.path.exists("logo.png"): st.image("logo.png", width=220)
    else: st.write("")

with col_title:
    st.title("Tareo de Operaciones - Fargoline")

dias_nombres = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

with st.sidebar:
    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state.autenticado = False
        st.rerun()
        
    with st.expander("🔐 Cambiar Usuario/Contraseña"):
        with st.form("form_cambio_clave"):
            nuevo_user = st.text_input("Nuevo Usuario:")
            nueva_clave = st.text_input("Nueva Contraseña:", type="password")
            if st.form_submit_button("Guardar Nuevos Datos"):
                if nuevo_user and nueva_clave:
                    supabase.table("usuarios").update({"usuario": nuevo_user.strip(), "clave": nueva_clave.strip()}).eq("id", 1).execute()
                    st.success("✅ ¡Credenciales actualizadas con éxito!")
                else:
                    st.warning("⚠️ Debes llenar ambos campos.")
    
    st.divider()
    st.header("⚡ Acciones Rápidas")
    fecha_seleccionada = st.date_input("Inicio de malla (Lunes recomendado):", date.today())
    num_semanas = st.selectbox("Semanas a programar / visualizar:", [1, 2, 3, 4], index=0)
    st.info("💡 La malla no borra tu historial. Solo sobrescribe las fechas seleccionadas.")
    
    if st.button("🚀 Recalcular Malla", type="primary"):
        with st.spinner(f"Generando turnos para {num_semanas} semana(s)..."):
            generar_malla_semanal(fecha_seleccionada, num_semanas)
            st.success("¡Malla actualizada correctamente!")
            st.cache_data.clear()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📅 Matriz y Reporte", 
    "🏢 Demanda Dinámica",
    "🚨 Incidencias", 
    "👥 Personal y Sedes",
    "🗂️ Histórico"
])

# =========================================================================
# TAB 1: MATRIZ Y REPORTE EJECUTIVO
# =========================================================================
with tab1:
    dias_totales = 7 * num_semanas
    dias_semana = [str(fecha_seleccionada + timedelta(days=i)) for i in range(dias_totales)]
    f_ini_s = str(fecha_seleccionada)
    f_fin_s = str(fecha_seleccionada + timedelta(days=dias_totales - 1))

    @st.cache_data(ttl=5)
    def cargar_datos_tareo(f_inicio_str, f_fin_str):
        res = supabase.table("tareo_programado").select("fecha, turno, sede, es_hhee, estado, colaboradores(nombre, posicion)").gte("fecha", f_inicio_str).lte("fecha", f_fin_str).execute()
        return res.data if res.data else []

    raw_data = cargar_datos_tareo(f_ini_s, f_fin_s)

    sedes_unicas = sorted(list(set(row.get('sede', 'Sede 1') for row in raw_data if row.get('sede')))) if raw_data else []
    opciones_sedes = ["Todas las Sedes"] + sedes_unicas

    col_s1, col_s2 = st.columns([3, 1])
    with col_s1: sede_filtro = st.selectbox("🏢 Ver Malla por Sede Específica:", opciones_sedes, index=0)
    with col_s2:
        st.write(""); st.write("")
        if st.button("🔄 Refrescar Vista"): st.cache_data.clear(); st.rerun()

    filas = []
    for row in raw_data:
        nombre_sede = row.get('sede', 'Sede 1')
        if sede_filtro != "Todas las Sedes" and nombre_sede != sede_filtro: continue

        turno_base = "D" if row['turno'] == "Día" else "N"
        estado = row.get('estado')
        
        if estado in ['FALTA', 'DM', 'PERMISO']: 
            codigo_turno = f"❌ {estado}"
        else: 
            he_text = " [HE]" if row.get('es_hhee') else ""
            if sede_filtro == "Todas las Sedes":
                codigo_turno = f"{turno_base} ({nombre_sede}){he_text}"
            else:
                codigo_turno = f"{turno_base}{he_text}"

        filas.append({
            "Colaborador": row['colaboradores']['nombre'],
            "Posición": limpiar_posicion(row['colaboradores']['posicion']),
            "Fecha": str(row['fecha']),
            "Turno": codigo_turno
        })

    if filas:
        df = pd.DataFrame(filas)
        matriz_df = df.pivot_table(index=["Colaborador", "Posición"], columns="Fecha", values="Turno", aggfunc="first").fillna("L")
        matriz_df = matriz_df.reindex(columns=dias_semana, fill_value="L")
        
        st.subheader(f"📊 Cuadrante Semanal — Vista: {sede_filtro}")
        st.dataframe(matriz_df, use_container_width=True)
        csv = matriz_df.to_csv().encode('utf-8')
        st.download_button("📥 Descargar Reporte CSV", csv, f"tareo_{fecha_seleccionada}_{sede_filtro}.csv", "text/csv")
    else: st.info(f"No hay registros asignados para **{sede_filtro}** en este periodo.")

    st.divider()

    st.subheader("👔 Reporte Ejecutivo Consolidado")
    try:
        res_dem = supabase.table("demanda_operativa").select("*").execute().data
        if res_dem and raw_data:
            demanda_base = {}
            demanda_especifica = {}
            combinaciones = set()
            
            for d in res_dem:
                if "_" in d['turno']:
                    dia, t = d['turno'].split("_")
                    demanda_especifica[(d['sede'], d['posicion'], dia, t)] = d['cantidad']
                    combinaciones.add((d['sede'], d['posicion'], t))
                else:
                    demanda_base[(d['sede'], d['posicion'], d['turno'])] = d['cantidad']
                    combinaciones.add((d['sede'], d['posicion'], d['turno']))

            conteo_prog, conteo_hhee, total_hhee = {}, {}, 0
            for p in raw_data:
                if p.get('estado') in ['FALTA', 'DM', 'PERMISO']: continue
                s, t, pos = p['sede'], p['turno'], limpiar_posicion(p['colaboradores']['posicion'])
                conteo_prog[(s, pos, t)] = conteo_prog.get((s, pos, t), 0) + 1
                if p.get('es_hhee'): 
                    conteo_hhee[(s, pos, t)] = conteo_hhee.get((s, pos, t), 0) + 1
                    total_hhee += 1

            reporte_filas = []
            total_req_sem, total_prog_sem = 0, 0

            for (s, pos, t) in sorted(combinaciones):
                req_base = demanda_base.get((s, pos, t), 0)
                req_periodo = 0
                for i in range(dias_totales):
                    d_fecha = fecha_seleccionada + timedelta(days=i)
                    nombre_dia = dias_nombres[d_fecha.weekday()]
                    req_periodo += demanda_especifica.get((s, pos, nombre_dia, t), req_base)

                prog_semanal = conteo_prog.get((s, pos, t), 0)
                if req_periodo == 0 and prog_semanal == 0: continue

                hhee_semanal = conteo_hhee.get((s, pos, t), 0)
                deficit_semanal = req_periodo - prog_semanal

                total_req_sem += req_periodo
                total_prog_sem += prog_semanal
                estado = f"⚠️ Faltan {deficit_semanal}" if deficit_semanal > 0 else ("✅ Ok" if deficit_semanal == 0 else "🔵 Exceso")

                reporte_filas.append({
                    "Sede": s, "Cargo": pos, "Turno": t,
                    "Req. Base (Diario)": req_base, "Req. Periodo Total": req_periodo,
                    "Prog. Real": prog_semanal, "HHEE (Extras)": hhee_semanal, 
                    "Déficit Real": deficit_semanal if deficit_semanal > 0 else 0, "Estado": estado
                })

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Turnos Req. (Total Periodo)", total_req_sem)
            kpi2.metric("Turnos Normales", total_prog_sem - total_hhee)
            kpi3.metric("Horas Extras [HE]", total_hhee, delta_color="off")
            deficit_total = total_req_sem - total_prog_sem
            kpi4.metric("Déficit Faltante", f"{deficit_total}", delta=-deficit_total if deficit_total > 0 else 0, delta_color="inverse")

            df_reporte = pd.DataFrame(reporte_filas)
            st.dataframe(df_reporte, use_container_width=True)

            if not df_reporte.empty:
                st.divider()
                st.subheader("📈 Análisis Gráfico de Cobertura y Presupuesto por Sede")
                df_sede = df_reporte.groupby('Sede', as_index=False)[['Req. Periodo Total', 'Prog. Real', 'HHEE (Extras)', 'Déficit Real']].sum()
                df_sede['Turnos Normales'] = df_sede['Prog. Real'] - df_sede['HHEE (Extras)']

                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    df_g1 = df_sede[['Sede', 'Prog. Real', 'Déficit Real']].melt(id_vars='Sede', var_name='Indicador', value_name='Turnos')
                    fig1 = px.bar(df_g1, x='Sede', y='Turnos', color='Indicador', title='Cobertura vs Déficit',
                                  color_discrete_map={'Prog. Real': '#198754', 'Déficit Real': '#dc3545'}, text_auto=True)
                    fig1.update_layout(barmode='stack')
                    st.plotly_chart(fig1, use_container_width=True)
                with col_g2:
                    df_g2 = df_sede[['Sede', 'Turnos Normales', 'HHEE (Extras)']].melt(id_vars='Sede', var_name='Tipo de Turno', value_name='Cantidad')
                    fig2 = px.bar(df_g2, x='Sede', y='Cantidad', color='Tipo de Turno', title='Composición Operativa: Normales vs HHEE',
                                  color_discrete_map={'Turnos Normales': '#0d6efd', 'HHEE (Extras)': '#ffc107'}, text_auto=True)
                    fig2.update_layout(barmode='stack')
                    st.plotly_chart(fig2, use_container_width=True)
    except Exception: pass

# =========================================================================
# TAB 2: DEMANDA DINÁMICA
# =========================================================================
with tab2:
    st.subheader("🏢 Definir Demanda Operativa (Matriz Inteligente)")
    st.markdown("Establece la demanda diaria por defecto, o configura picos operativos en días específicos de la semana.")

    modo_demanda = st.radio("⚙️ Modo de Configuración:", ["Demanda Base (Aplica a todos los días)", "Demanda Específica (Excepciones por Día)"], horizontal=True)

    dia_seleccionado = None
    if modo_demanda == "Demanda Específica (Excepciones por Día)":
        dia_seleccionado = st.selectbox("📅 Seleccionar Día a configurar:", dias_nombres)

    try: res_sedes = supabase.table("sedes").select("nombre").eq("activa", True).execute().data
    except Exception: res_sedes = []
    sedes_opt = [s['nombre'] for s in res_sedes] if res_sedes else []

    res_colabs = supabase.table("colaboradores").select("posicion").eq("activo", True).execute().data
    posiciones_opt = sorted(list(set(limpiar_posicion(c['posicion']) for c in res_colabs if c.get('posicion')))) if res_colabs else []

    if posiciones_opt and sedes_opt:
        try: res_demanda = supabase.table("demanda_operativa").select("*").execute().data
        except Exception: res_demanda = []
        
        demanda_dict = {}
        if res_demanda:
            for d in res_demanda:
                t = d['turno']
                if modo_demanda == "Demanda Base (Aplica a todos los días)":
                    if "_" not in t: demanda_dict[(d['sede'], d['posicion'], t)] = d['cantidad']
                else:
                    if t.startswith(f"{dia_seleccionado}_"):
                        turno_real = t.split("_")[1]
                        demanda_dict[(d['sede'], d['posicion'], turno_real)] = d['cantidad']
        
        filas_editor = []
        for s in sedes_opt:
            for p in posiciones_opt:
                filas_editor.append({
                    "Sede": s, "Posición": p,
                    "Requerimiento DÍA": demanda_dict.get((s, p, "Día"), 0),
                    "Requerimiento NOCHE": demanda_dict.get((s, p, "Noche"), 0)
                })
                
        df_editor = pd.DataFrame(filas_editor)
        edited_df = st.data_editor(df_editor, use_container_width=True, hide_index=True, disabled=["Sede", "Posición"])
        
        st.divider()
        c_btn1, c_btn2 = st.columns([3, 7])
        with c_btn1:
            if st.button("💾 Guardar Matriz Actual", type="primary"):
                nuevos_registros = []
                turno_dia_str = "Día" if modo_demanda == "Demanda Base (Aplica a todos los días)" else f"{dia_seleccionado}_Día"
                turno_noche_str = "Noche" if modo_demanda == "Demanda Base (Aplica a todos los días)" else f"{dia_seleccionado}_Noche"

                for _, row in edited_df.iterrows():
                    s, p = row["Sede"], row["Posición"]
                    c_dia, c_noche = int(row["Requerimiento DÍA"]), int(row["Requerimiento NOCHE"])
                    
                    if c_dia > 0: nuevos_registros.append({"sede": s, "posicion": p, "turno": turno_dia_str, "cantidad": c_dia})
                    if c_noche > 0: nuevos_registros.append({"sede": s, "posicion": p, "turno": turno_noche_str, "cantidad": c_noche})
                        
                turnos_borrar = ["Día", "Noche"] if modo_demanda == "Demanda Base (Aplica a todos los días)" else [f"{dia_seleccionado}_Día", f"{dia_seleccionado}_Noche"]
                supabase.table("demanda_operativa").delete().in_("turno", turnos_borrar).execute()
                
                if nuevos_registros: supabase.table("demanda_operativa").insert(nuevos_registros).execute()
                
                st.success("✅ ¡Matriz guardada exitosamente!")
                st.cache_data.clear(); st.rerun()
                
        with c_btn2:
            if st.button("🗑️ Vaciar TODA la Demanda"):
                supabase.table("demanda_operativa").delete().neq("id", 0).execute()
                st.warning("⚠️ Base y excepciones eliminadas."); st.cache_data.clear(); st.rerun()
    else: st.warning("Primero debes registrar colaboradores y sedes.")

# =========================================================================
# TAB 3 Y TAB 4 (Incidencias y Gestión de Personal Múltiple)
# =========================================================================
with tab3:
    st.subheader("🚨 Registrar Faltas, DM o Permisos (Día a Día)")
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
                    if success: st.success(msg)
                    else: st.error(msg)
                else: st.error("No se encontró el turno para actualizar.")
    else: st.info("No hay turnos programados activos para esta fecha.")

    st.divider()
    st.subheader("📅 Bloquear Fechas Futuras (Vacaciones)")
    res_colab = supabase.table("colaboradores").select("id, nombre, posicion").eq("activo", True).execute()
    opc_colab = {f"{c['nombre']} ({limpiar_posicion(c['posicion'])})": c['id'] for c in res_colab.data} if res_colab.data else {}
    if opc_colab:
        colab_vaca = st.selectbox("Seleccionar Colaborador para Vacaciones:", list(opc_colab.keys()))
        c1, c2 = st.columns(2)
        f_ini, f_fin = c1.date_input("Inicio:"), c2.date_input("Fin:")
        if st.button("💾 Guardar Vacaciones"):
            supabase.table("restricciones_fechas").insert({"colaborador_id": opc_colab[colab_vaca], "fecha_inicio": str(f_ini), "fecha_fin": str(f_fin), "tipo": "VACACIONES"}).execute()
            st.success("Vacaciones guardadas."); st.cache_data.clear()

with tab4:
    col_izq, col_der = st.columns(2)
    with col_izq:
        st.subheader("👨‍💼 Colaboradores")
        with st.expander("📁 Carga Masiva (Excel/CSV)"):
            archivo = st.file_uploader("Selecciona archivo:", type=["xlsx", "csv"])
            if archivo and st.button("📥 Importar Lista"):
                try:
                    df = pd.read_csv(archivo) if archivo.name.endswith('.csv') else pd.read_excel(archivo)
                    df.columns = [str(c).strip() for c in df.columns]
                    regs = []
                    for _, row in df.iterrows():
                        if pd.isna(row.iloc[0]) or pd.isna(row.iloc[1]): continue
                        try: cod = str(int(float(row.iloc[0])))
                        except: cod = str(row.iloc[0]).strip()
                        pos = limpiar_posicion(str(row.iloc[2])) if not pd.isna(row.iloc[2]) else "General"
                        regs.append({
                            "codigo": cod, 
                            "nombre": str(row.iloc[1]).strip(), 
                            "posicion": pos, 
                            "he_acumuladas": 0.0, 
                            "dias_pendientes_recuperacion": 0, 
                            "activo": True
                        })
                    if regs:
                        # USAMOS UPSERT EN LUGAR DE INSERT PARA EVITAR COLAPSOS POR DUPLICADOS
                        supabase.table("colaboradores").upsert(regs).execute()
                        st.success(f"✅ ¡{len(regs)} colaborador(es) procesados/actualizados correctamente!")
                        st.cache_data.clear()
                        st.rerun()
                except Exception as e:
                    st.error(f"⚠️ Error al procesar el archivo. Revisa que el formato del Excel sea correcto. Detalle: {e}")

        with st.expander("➕ Agregar Manual"):
            with st.form("f_emp", clear_on_submit=True):
                cod, nom, pos = st.text_input("Código:"), st.text_input("Nombre:"), st.text_input("Posición:")
                if st.form_submit_button("Guardar") and nom:
                    try:
                        supabase.table("colaboradores").upsert({"codigo": cod, "nombre": nom, "posicion": limpiar_posicion(pos), "he_acumuladas": 0, "dias_pendientes_recuperacion": 0, "activo": True}).execute()
                        st.success("✅ Guardado correctamente."); st.cache_data.clear(); st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ Error al guardar: {e}")
        
        with st.expander("🗑️ Dar de Baja (Selección Múltiple)"):
            res_activos = supabase.table("colaboradores").select("id, nombre").eq("activo", True).execute().data
            if res_activos:
                opts = {c['nombre']: c['id'] for c in res_activos}
                sel_list = st.multiselect("Seleccionar Colaboradores a dar de baja:", list(opts.keys()))
                if st.button("🚫 Dar de Baja Selección") and sel_list:
                    ids_baja = [opts[n] for n in sel_list]
                    supabase.table("colaboradores").update({"activo": False}).in_("id", ids_baja).execute()
                    st.success(f"✅ ¡{len(ids_baja)} colaborador(es) dados de baja exitosamente!")
                    st.cache_data.clear(); st.rerun()
            else: st.info("No hay colaboradores activos.")

        with st.expander("🔄 Reactivar Personal (Inactivos)"):
            res_inactivos = supabase.table("colaboradores").select("id, nombre").eq("activo", False).execute().data
            if res_inactivos:
                opts_in = {c['nombre']: c['id'] for c in res_inactivos}
                sel_react = st.multiselect("Seleccionar Colaboradores a reactivar:", list(opts_in.keys()))
                if st.button("✅ Reactivar Selección") and sel_react:
                    ids_react = [opts_in[n] for n in sel_react]
                    supabase.table("colaboradores").update({"activo": True}).in_("id", ids_react).execute()
                    st.success(f"✅ ¡{len(ids_react)} colaborador(es) reactivados exitosamente!")
                    st.cache_data.clear(); st.rerun()
            else: st.info("No hay colaboradores dados de baja.")

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

# =========================================================================
# TAB 5: HISTÓRICO Y REPORTES
# =========================================================================
with tab5:
    st.subheader("🗂️ Consulta de Histórico General")
    st.markdown("Revisa el registro detallado de turnos de cualquier periodo, aplica filtros y descárgalo.")

    c_f1, c_f2 = st.columns(2)
    hist_ini = c_f1.date_input("📅 Fecha de Inicio:", date.today() - timedelta(days=7), key="hist_ini")
    hist_fin = c_f2.date_input("📅 Fecha Fin:", date.today() + timedelta(days=7), key="hist_fin")

    if hist_ini <= hist_fin:
        @st.cache_data(ttl=5)
        def fetch_historico(ini, fin):
            res = supabase.table("tareo_programado").select("fecha, turno, sede, es_hhee, estado, colaboradores(nombre, posicion)").gte("fecha", str(ini)).lte("fecha", str(fin)).order("fecha").execute()
            return res.data

        data_hist = fetch_historico(hist_ini, hist_fin)

        if data_hist:
            filas_hist = []
            for r in data_hist:
                filas_hist.append({
                    "Fecha": r['fecha'], "Colaborador": r['colaboradores']['nombre'],
                    "Cargo": limpiar_posicion(r['colaboradores']['posicion']), "Sede": r['sede'],
                    "Turno": r['turno'], "Condición": "Hora Extra (HHEE)" if r['es_hhee'] else "Normal",
                    "Estado": r['estado']
                })
            df_hist = pd.DataFrame(filas_hist)

            st.write("---")
            st.markdown("### 🔍 Filtros Inteligentes")
            cf1, cf2, cf3 = st.columns(3)
            nombres_unicos = sorted(df_hist["Colaborador"].unique())
            sedes_unicas = sorted(df_hist["Sede"].unique())
            estados_unicos = sorted(df_hist["Estado"].unique())

            f_nombres = cf1.multiselect("Filtrar por Colaborador(es):", nombres_unicos)
            f_sedes = cf2.multiselect("Filtrar por Sede(s):", sedes_unicas)
            f_estados = cf3.multiselect("Filtrar por Estado:", estados_unicos)

            df_filtrado = df_hist.copy()
            if f_nombres: df_filtrado = df_filtrado[df_filtrado["Colaborador"].isin(f_nombres)]
            if f_sedes: df_filtrado = df_filtrado[df_filtrado["Sede"].isin(f_sedes)]
            if f_estados: df_filtrado = df_filtrado[df_filtrado["Estado"].isin(f_estados)]

            st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

            csv_hist = df_filtrado.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Descargar Base de Datos Filtrada (CSV)", data=csv_hist, file_name=f"historico_WFM_{hist_ini}_a_{hist_fin}.csv", mime="text/csv")

            st.write("---")
            st.write("**📌 Resumen del periodo filtrado:**")
            k1, k2, k3 = st.columns(3)
            k1.metric("Total Turnos Registrados", len(df_filtrado))
            k2.metric("Total Horas Extras", len(df_filtrado[df_filtrado["Condición"] == "Hora Extra (HHEE)"]))
            k3.metric("Total Ausencias (Faltas/DM/Permisos)", len(df_filtrado[df_filtrado["Estado"].isin(["FALTA", "DM", "PERMISO"])]))
        else:
            st.info("No hay turnos registrados en este rango de fechas. Prueba ampliando la búsqueda.")
    else:
        st.error("La 'Fecha de Inicio' debe ser anterior o igual a la 'Fecha Fin'.")

    st.write("---")
    with st.expander("⚠️ Zona de Peligro - Borrar Registros (Modo Pruebas)"):
        st.markdown("Usa estas herramientas para limpiar la base de datos de turnos y hacer pruebas desde cero.")
        c_del1, c_del2 = st.columns(2)
        
        with c_del1:
            st.markdown("#### 📅 Borrar por Rango de Fechas")
            del_ini = st.date_input("Desde:", date.today(), key="del_ini")
            del_fin = st.date_input("Hasta:", date.today(), key="del_fin")
            if st.button("🗑️ Borrar Rango Seleccionado", type="primary"):
                if del_ini <= del_fin:
                    supabase.table("tareo_programado").delete().gte("fecha", str(del_ini)).lte("fecha", str(del_fin)).execute()
                    st.success(f"✅ Se han eliminado los turnos desde {del_ini} hasta {del_fin}.")
                    st.cache_data.clear(); st.rerun()
                else: st.error("La fecha 'Desde' debe ser anterior a 'Hasta'.")
                
        with c_del2:
            st.markdown("#### 🚨 Borrar TODO el Histórico")
            st.warning("Esto eliminará TODOS los turnos guardados en toda la historia de la base de datos. (Tus trabajadores y sedes NO se borrarán).")
            confirm_delete_all = st.checkbox("Sí, estoy seguro de borrar todo el historial de turnos")
            if confirm_delete_all:
                if st.button("🗑️ Vaciar Base de Datos Completamente", type="primary"):
                    supabase.table("tareo_programado").delete().neq("id", 0).execute()
                    st.success("✅ ¡La base de datos de turnos ha quedado completamente limpia!")
                    st.cache_data.clear(); st.rerun()