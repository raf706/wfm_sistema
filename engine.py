from supabase import create_client, Client
from datetime import date, timedelta
import random
from collections import defaultdict

SUPABASE_URL = "https://vsnyqynjaxdmofyewfcq.supabase.co"
SUPABASE_KEY = "sb_publishable__wmHvw9dfAcu-o78te3iMg_9JqpAb_P" 

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

EQUIVALENCIAS_POSICION = {}

def limpiar_posicion(pos: str) -> str:
    if not pos: return ""
    pos_clean = pos.strip().title()
    pos_clean = pos_clean.replace(" De ", " de ").replace(" Y ", " y ")
    return pos_clean

def normalizar_posicion(pos: str) -> str:
    clean = limpiar_posicion(pos)
    return EQUIVALENCIAS_POSICION.get(clean, clean)

class CalculadorEquidad:
    @staticmethod
    def calcular_score(he_acumuladas: float, dias_deuda: int, es_noche: bool, turnos_semana: int, dias_consecutivos: int, es_dia_descanso_preferido: bool) -> float:
        score = (he_acumuladas or 0.0) * 10.0
        if es_noche: score += 15.0
        if dias_deuda and dias_deuda > 0: score -= 50.0
        score += turnos_semana * 20.0 
        score += dias_consecutivos * 25.0 
        if es_dia_descanso_preferido: score += 100.0
        return score

def generar_malla_semanal(fecha_inicio: date, num_semanas: int = 1):
    print(f"\n==================================================")
    print(f" GENERANDO TAREO CON QA APROBADO (BLOQUEOS ACTIVOS)")
    print(f"==================================================\n")

    fecha_fin_total = fecha_inicio + timedelta(days=(7 * num_semanas) - 1)
    supabase.table("tareo_programado").delete().gte("fecha", str(fecha_inicio)).lte("fecha", str(fecha_fin_total)).execute()

    colaboradores = supabase.table("colaboradores").select("*").eq("activo", True).execute().data
    restricciones = supabase.table("restricciones_fechas").select("*").execute().data
    if not colaboradores: return

    try: res_demanda = supabase.table("demanda_operativa").select("*").execute().data
    except Exception: res_demanda = []

    demanda_base = {}
    demanda_especifica = {}
    combinaciones = set()

    if res_demanda:
        for item in res_demanda:
            pos_norm = normalizar_posicion(item['posicion'])
            s = item['sede']
            t = item['turno']
            c = item.get('cantidad', 1)

            if "_" in t:
                dia, turno_real = t.split("_")
                demanda_especifica[(s, pos_norm, dia, turno_real)] = c
                combinaciones.add((s, pos_norm, turno_real))
            else:
                demanda_base[(s, pos_norm, t)] = c
                combinaciones.add((s, pos_norm, t))
    else:
        posiciones_existentes = list(set(normalizar_posicion(c['posicion']) for c in colaboradores if c.get('posicion')))
        for pos in posiciones_existentes:
            combinaciones.add(("Sede 1", pos, "Día"))
            combinaciones.add(("Sede 1", pos, "Noche"))
            demanda_base[("Sede 1", pos, "Día")] = 1
            demanda_base[("Sede 1", pos, "Noche")] = 1

    colabs_por_pos = {}
    for c in colaboradores:
        pos = normalizar_posicion(c['posicion'])
        colabs_por_pos.setdefault(pos, []).append(c)

    offset_colaborador = {}
    for pos, lista_c in colabs_por_pos.items():
        lista_c.sort(key=lambda x: x['id'])
        for idx, c in enumerate(lista_c): offset_colaborador[c['id']] = idx

    # CARGA HISTÓRICA PROFUNDA (14 DÍAS ATRÁS)
    historial_global = {c['id']: [] for c in colaboradores}
    fecha_hist_inicio = fecha_inicio - timedelta(days=14)
    historial_previo = supabase.table("tareo_programado").select("colaborador_id, fecha, turno, estado").gte("fecha", str(fecha_hist_inicio)).lt("fecha", str(fecha_inicio)).execute().data
    
    if historial_previo:
        for t in historial_previo:
            if t['colaborador_id'] in historial_global:
                # Solo contamos los que realmente trabajó
                if t.get('estado') not in ['FALTA', 'DM', 'PERMISO']:
                    historial_global[t['colaborador_id']].append({"fecha": str(t['fecha']), "turno": t['turno']})

    registros_a_insertar = []
    dias_nombres = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

    for semana in range(num_semanas):
        inicio_semana = fecha_inicio + timedelta(days=7 * semana)
        dias_semana = [inicio_semana + timedelta(days=i) for i in range(7)]
        historial_semana_actual = {c['id']: [] for c in colaboradores}

        for idx_dia_semana, d in enumerate(dias_semana):
            nombre_dia = dias_nombres[d.weekday()]
            slots_hoy = []

            for (s, p, t) in combinaciones:
                cant = demanda_especifica.get((s, p, nombre_dia, t), demanda_base.get((s, p, t), 0))
                for _ in range(cant):
                    slots_hoy.append({"sede": s, "posicion": p, "turno": t})

            if idx_dia_semana % 2 == 0:
                slots_hoy.sort(key=lambda x: x['turno'])
            else:
                slots_hoy.sort(key=lambda x: x['turno'], reverse=True)

            for slot in slots_hoy:
                candidatos_normales = []
                candidatos_hhee = []
                candidatos_emergencia = []
                
                for emp in colaboradores:
                    if normalizar_posicion(emp['posicion']) != slot['posicion']: continue
                    
                    # Validación 1: Vacaciones
                    esta_de_vacaciones = False
                    for r in restricciones:
                        if r['colaborador_id'] == emp['id'] and date.fromisoformat(r['fecha_inicio']) <= d <= date.fromisoformat(r['fecha_fin']):
                            esta_de_vacaciones = True; break
                    if esta_de_vacaciones: continue

                    turnos_globales = historial_global[emp['id']]
                    turnos_esta_semana = historial_semana_actual[emp['id']]
                    
                    # Validación 2: Ya tiene turno hoy
                    if any(t['fecha'] == str(d) for t in turnos_globales): continue
                    
                    # Validación 3: Consistencia de Turno (Misma semana)
                    if turnos_esta_semana:
                        turno_base_semana = turnos_esta_semana[0]['turno']
                        if slot['turno'] != turno_base_semana: continue 
                    
                    # =========================================================================
                    # 🚨 QA HARD CONSTRAINTS (REGLAS DE BLOQUEO ABSOLUTO)
                    # =========================================================================
                    ayer = str(d - timedelta(days=1))
                    
                    # HARD CONSTRAINT A: Ruptura Biológica (Noche -> Día)
                    if turnos_globales:
                        turno_ayer = next((t for t in turnos_globales if t['fecha'] == ayer), None)
                        if turno_ayer and turno_ayer['turno'] == "Noche" and slot['turno'] == "Día":
                            continue # BLOQUEO ABSOLUTO
                    
                    # HARD CONSTRAINT B: Días consecutivos excesivos (>6)
                    consecutivos = 0
                    temp_d = d - timedelta(days=1)
                    while any(t['fecha'] == str(temp_d) for t in turnos_globales):
                        consecutivos += 1
                        temp_d -= timedelta(days=1)
                    
                    if consecutivos >= 6:
                        continue # BLOQUEO ABSOLUTO (Fuerza descanso)
                    # =========================================================================

                    idx_emp = offset_colaborador.get(emp['id'], 0)
                    rest_start = (idx_emp * 2) % 7
                    dias_descanso_pref = [(rest_start + r) % 7 for r in range(3)]
                    es_descanso_pref = (idx_dia_semana in dias_descanso_pref)

                    score = CalculadorEquidad.calcular_score(
                        emp.get('he_acumuladas', 0.0), emp.get('dias_pendientes_recuperacion', 0),
                        (slot['turno'] == "Noche"), len(turnos_esta_semana), consecutivos, es_descanso_pref
                    )
                    
                    if len(turnos_esta_semana) < 4: candidatos_normales.append((score, emp))
                    elif len(turnos_esta_semana) < 6: candidatos_hhee.append((score, emp))
                    elif len(turnos_esta_semana) < 7: candidatos_emergencia.append((score, emp))

                if candidatos_normales:
                    candidatos_normales.sort(key=lambda x: x[0])
                    ganador = candidatos_normales[0][1]
                elif candidatos_hhee:
                    candidatos_hhee.sort(key=lambda x: x[0])
                    ganador = candidatos_hhee[0][1]
                elif candidatos_emergencia:
                    candidatos_emergencia.sort(key=lambda x: x[0])
                    ganador = candidatos_emergencia[0][1]
                else: continue

                nuevo_turno = {"fecha": str(d), "turno": slot['turno']}
                historial_global[ganador['id']].append(nuevo_turno)
                historial_semana_actual[ganador['id']].append(nuevo_turno)

                registros_a_insertar.append({
                    "colaborador_id": ganador['id'], "fecha": str(d), "sede": slot['sede'],
                    "turno": slot['turno'], "estado": "PROGRAMADO", 
                    "semana_idx": semana 
                })

    # =========================================================================
    # FASE 2: DISTRIBUCIÓN Y DISPERSIÓN INTELIGENTE DE HHEE
    # =========================================================================
    he_por_fecha = defaultdict(int)
    turnos_por_colab_semana = defaultdict(list)
    
    for r in registros_a_insertar:
        clave = (r['semana_idx'], r['colaborador_id'])
        turnos_por_colab_semana[clave].append(r)
        
    for clave, lista_turnos in turnos_por_colab_semana.items():
        num_turnos = len(lista_turnos)
        if num_turnos > 4:
            num_he = num_turnos - 4 
            random.shuffle(lista_turnos)
            lista_turnos.sort(key=lambda x: he_por_fecha[x['fecha']])
            
            for i, t in enumerate(lista_turnos):
                if i < num_he:
                    t['es_hhee'] = True
                    he_por_fecha[t['fecha']] += 1
                else:
                    t['es_hhee'] = False
        else:
            for t in lista_turnos:
                t['es_hhee'] = False

    for r in registros_a_insertar:
        if 'semana_idx' in r:
            del r['semana_idx']

    if registros_a_insertar:
        supabase.table("tareo_programado").insert(registros_a_insertar).execute()
        print(f"✅ Se han generado {len(registros_a_insertar)} turnos. QA Passed.")

def registrar_incidencia_diaria(fecha_inc: date, id_colab: int, tipo: str, requiere_reemplazo: bool):
    turnos = supabase.table("tareo_programado").select("*").eq("fecha", str(fecha_inc)).eq("colaborador_id", id_colab).execute().data
    turno_valido = None
    for t in turnos:
        if t.get('estado') not in ['FALTA', 'DM', 'PERMISO']: turno_valido = t; break
            
    if not turno_valido: return False, "No programado."
        
    supabase.table("tareo_programado").update({"estado": tipo}).eq("id", turno_valido['id']).execute()
    supabase.table("restricciones_fechas").insert({"colaborador_id": id_colab, "fecha_inicio": str(fecha_inc), "fecha_fin": str(fecha_inc), "tipo": tipo}).execute()
    msg = f"✅ Incidencia ({tipo}) registrada con éxito."
    
    if requiere_reemplazo:
        colaboradores = supabase.table("colaboradores").select("*").eq("activo", True).execute().data
        colab_ausente = next((c for c in colaboradores if c['id'] == id_colab), None)
        if colab_ausente:
            pos_req = normalizar_posicion(colab_ausente['posicion'])
            sede_req, turno_req = turno_valido['sede'], turno_valido['turno']
            
            turnos_hoy = supabase.table("tareo_programado").select("colaborador_id").eq("fecha", str(fecha_inc)).execute().data
            ocupados_hoy = [t['colaborador_id'] for t in turnos_hoy]
            restricciones = supabase.table("restricciones_fechas").select("*").execute().data
            
            candidatos = []
            for emp in colaboradores:
                if emp['id'] in ocupados_hoy or normalizar_posicion(emp['posicion']) != pos_req: continue
                bloqueado = False
                for r in restricciones:
                    if r['colaborador_id'] == emp['id'] and date.fromisoformat(r['fecha_inicio']) <= fecha_inc <= date.fromisoformat(r['fecha_fin']):
                        bloqueado = True; break
                if bloqueado: continue
                
                ayer = fecha_inc - timedelta(days=1)
                t_ayer = supabase.table("tareo_programado").select("turno").eq("fecha", str(ayer)).eq("colaborador_id", emp['id']).execute().data
                if t_ayer and t_ayer[0]['turno'] == "Noche" and turno_req == "Día": continue
                    
                candidatos.append(emp)
                
            if candidatos:
                reemplazo = candidatos[0]
                supabase.table("tareo_programado").insert({
                    "colaborador_id": reemplazo['id'], "fecha": str(fecha_inc), "sede": sede_req,
                    "turno": turno_req, "estado": "PROGRAMADO", "es_hhee": True
                }).execute()
                msg += f" Reemplazo automático: **{reemplazo['nombre']}** [HE]."
            else: msg += " ⚠️ No se encontró reemplazo."

    return True, msg