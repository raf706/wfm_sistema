from supabase import create_client, Client
from datetime import date, timedelta

SUPABASE_URL = "https://vsnyqynjaxdmofyewfcq.supabase.co"
SUPABASE_KEY = "sb_publishable__wmHvw9dfAcu-o78te3iMg_9JqpAb_P" 

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

EQUIVALENCIAS_POSICION = {}

def limpiar_posicion(pos: str) -> str:
    if not pos:
        return ""
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
        if es_dia_descanso_preferido:
            score += 100.0
            
        return score

def generar_malla_semanal(fecha_inicio: date):
    print(f"\n==================================================")
    print(f" GENERANDO TAREO CON HHEE EXTREMAS (COBERTURA TOTAL)")
    print(f"==================================================\n")

    supabase.table("tareo_programado").delete().neq("id", 0).execute()

    colaboradores = supabase.table("colaboradores").select("*").eq("activo", True).execute().data
    restricciones = supabase.table("restricciones_fechas").select("*").execute().data

    if not colaboradores: return

    try:
        res_demanda = supabase.table("demanda_operativa").select("*").execute().data
    except Exception:
        res_demanda = []

    demanda_diaria = []
    if res_demanda:
        for item in res_demanda:
            pos_norm = normalizar_posicion(item['posicion'])
            for _ in range(item.get('cantidad', 1)):
                demanda_diaria.append({"sede": item['sede'], "posicion": pos_norm, "turno": item['turno']})
    else:
        posiciones_existentes = list(set(normalizar_posicion(c['posicion']) for c in colaboradores if c.get('posicion')))
        for pos in posiciones_existentes:
            demanda_diaria.append({"sede": "Sede 1", "posicion": pos, "turno": "Día"})
            demanda_diaria.append({"sede": "Sede 1", "posicion": pos, "turno": "Noche"})

    colabs_por_pos = {}
    for c in colaboradores:
        pos = normalizar_posicion(c['posicion'])
        colabs_por_pos.setdefault(pos, []).append(c)

    offset_colaborador = {}
    for pos, lista_c in colabs_por_pos.items():
        lista_c.sort(key=lambda x: x['id'])
        for idx, c in enumerate(lista_c):
            offset_colaborador[c['id']] = idx

    historial_semana = {c['id']: [] for c in colaboradores}
    dias = [fecha_inicio + timedelta(days=i) for i in range(7)]
    registros_a_insertar = []

    for idx_dia, d in enumerate(dias):
        for slot in demanda_diaria:
            candidatos_normales = []
            candidatos_hhee = []
            candidatos_emergencia = []
            
            for emp in colaboradores:
                if normalizar_posicion(emp['posicion']) != slot['posicion']: continue
                
                esta_de_vacaciones = False
                for r in restricciones:
                    if r['colaborador_id'] == emp['id'] and date.fromisoformat(r['fecha_inicio']) <= d <= date.fromisoformat(r['fecha_fin']):
                        esta_de_vacaciones = True
                        break
                if esta_de_vacaciones: continue

                turnos_del_colaborador = historial_semana[emp['id']]
                
                if any(t['fecha'] == str(d) for t in turnos_del_colaborador): continue
                
                if turnos_del_colaborador:
                    ultimo_turno = turnos_del_colaborador[-1]
                    ayer = str(d - timedelta(days=1))
                    if ultimo_turno['fecha'] == ayer and ultimo_turno['turno'] == "Noche" and slot['turno'] == "Día":
                        continue 

                consecutivos = 0
                temp_d = d - timedelta(days=1)
                while any(t['fecha'] == str(temp_d) for t in turnos_del_colaborador):
                    consecutivos += 1
                    temp_d -= timedelta(days=1)

                idx_emp = offset_colaborador.get(emp['id'], 0)
                rest_start = (idx_emp * 2) % 7
                dias_descanso_pref = [(rest_start + r) % 7 for r in range(3)]
                es_descanso_pref = (idx_dia in dias_descanso_pref)

                score = CalculadorEquidad.calcular_score(
                    emp.get('he_acumuladas', 0.0), emp.get('dias_pendientes_recuperacion', 0),
                    (slot['turno'] == "Noche"), len(turnos_del_colaborador), consecutivos, es_descanso_pref
                )
                
                if len(turnos_del_colaborador) < 4:
                    candidatos_normales.append((score, emp))
                elif len(turnos_del_colaborador) < 6:
                    candidatos_hhee.append((score, emp))
                elif len(turnos_del_colaborador) < 7: 
                    candidatos_emergencia.append((score, emp))

            if candidatos_normales:
                candidatos_normales.sort(key=lambda x: x[0])
                ganador = candidatos_normales[0][1]
                es_hhee = False
            elif candidatos_hhee:
                candidatos_hhee.sort(key=lambda x: x[0])
                ganador = candidatos_hhee[0][1]
                es_hhee = True
            elif candidatos_emergencia:
                candidatos_emergencia.sort(key=lambda x: x[0])
                ganador = candidatos_emergencia[0][1]
                es_hhee = True
            else:
                continue

            historial_semana[ganador['id']].append({"fecha": str(d), "turno": slot['turno']})
            registros_a_insertar.append({
                "colaborador_id": ganador['id'], "fecha": str(d), "sede": slot['sede'],
                "turno": slot['turno'], "estado": "PROGRAMADO", "es_hhee": es_hhee
            })

    if registros_a_insertar:
        supabase.table("tareo_programado").insert(registros_a_insertar).execute()
        print(f"✅ Se han generado {len(registros_a_insertar)} turnos exitosamente.")

# --- AQUÍ ESTÁ LA FUNCIÓN DE INCIDENCIAS PARA QUE LA LEA APP.PY ---
def registrar_incidencia_diaria(fecha_inc: date, id_colab: int, tipo: str, requiere_reemplazo: bool):
    turnos = supabase.table("tareo_programado").select("*").eq("fecha", str(fecha_inc)).eq("colaborador_id", id_colab).execute().data
    turno_valido = None
    for t in turnos:
        if t.get('estado') not in ['FALTA', 'DM', 'PERMISO']:
            turno_valido = t
            break
            
    if not turno_valido:
        return False, "El colaborador no está programado para ese día o ya tenía una incidencia."
        
    supabase.table("tareo_programado").update({"estado": tipo}).eq("id", turno_valido['id']).execute()
    
    supabase.table("restricciones_fechas").insert({
        "colaborador_id": id_colab, "fecha_inicio": str(fecha_inc), "fecha_fin": str(fecha_inc), "tipo": tipo
    }).execute()
    
    msg = f"✅ Incidencia ({tipo}) registrada con éxito."
    
    if requiere_reemplazo:
        colaboradores = supabase.table("colaboradores").select("*").eq("activo", True).execute().data
        colab_ausente = next((c for c in colaboradores if c['id'] == id_colab), None)
        
        if colab_ausente:
            pos_req = normalizar_posicion(colab_ausente['posicion'])
            sede_req = turno_valido['sede']
            turno_req = turno_valido['turno']
            
            turnos_hoy = supabase.table("tareo_programado").select("colaborador_id").eq("fecha", str(fecha_inc)).execute().data
            ocupados_hoy = [t['colaborador_id'] for t in turnos_hoy]
            restricciones = supabase.table("restricciones_fechas").select("*").execute().data
            
            candidatos = []
            for emp in colaboradores:
                if emp['id'] in ocupados_hoy: continue
                if normalizar_posicion(emp['posicion']) != pos_req: continue
                
                bloqueado = False
                for r in restricciones:
                    if r['colaborador_id'] == emp['id'] and date.fromisoformat(r['fecha_inicio']) <= fecha_inc <= date.fromisoformat(r['fecha_fin']):
                        bloqueado = True
                        break
                if bloqueado: continue
                
                ayer = fecha_inc - timedelta(days=1)
                t_ayer = supabase.table("tareo_programado").select("turno").eq("fecha", str(ayer)).eq("colaborador_id", emp['id']).execute().data
                if t_ayer and t_ayer[0]['turno'] == "Noche" and turno_req == "Día":
                    continue
                    
                candidatos.append(emp)
                
            if candidatos:
                reemplazo = candidatos[0]
                supabase.table("tareo_programado").insert({
                    "colaborador_id": reemplazo['id'],
                    "fecha": str(fecha_inc),
                    "sede": sede_req,
                    "turno": turno_req,
                    "estado": "PROGRAMADO",
                    "es_hhee": True
                }).execute()
                msg += f" Se asignó automáticamente a **{reemplazo['nombre']}** como reemplazo [HE]."
            else:
                msg += " ⚠️ No se encontró a nadie disponible para reemplazar."

    return True, msg

if __name__ == "__main__":
    generar_malla_semanal(date.today())