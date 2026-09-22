from supabase import create_client, Client
from datetime import date, timedelta

SUPABASE_URL = "https://vsnyqynjaxdmofyewfcq.supabase.co"
SUPABASE_KEY = "sb_publishable__wmHvw9dfAcu-o78te3iMg_9JqpAb_P" 

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================================
# REGLA DE EQUIVALENCIA VACÍA: Cada cargo es independiente
# ==========================================================
EQUIVALENCIAS_POSICION = {}

def limpiar_posicion(pos: str) -> str:
    """Limpia formato (mayúsculas, 'de', 'y') sin aplicar equivalencias."""
    if not pos:
        return ""
    pos_clean = pos.strip().title()
    pos_clean = pos_clean.replace(" De ", " de ").replace(" Y ", " y ")
    return pos_clean

def normalizar_posicion(pos: str) -> str:
    """Aplica formato limpio. Al estar vacío el diccionario de equivalencias, devuelve el cargo original."""
    clean = limpiar_posicion(pos)
    return EQUIVALENCIAS_POSICION.get(clean, clean)

class CalculadorEquidad:
    @staticmethod
    def calcular_score(he_acumuladas: float, dias_deuda: int, es_noche: bool, turnos_semana: int) -> float:
        score = (he_acumuladas or 0.0) * 10.0
        if es_noche: score += 15.0
        if dias_deuda and dias_deuda > 0: score -= 50.0
        score += turnos_semana * 20.0 
        return score

def generar_malla_semanal(fecha_inicio: date):
    print(f"\n==================================================")
    print(f" GENERANDO TAREO CON DEMANDA CONFIGURABLE POR SEDE")
    print(f"==================================================\n")

    supabase.table("tareo_programado").delete().neq("id", 0).execute()

    colaboradores = supabase.table("colaboradores").select("*").eq("activo", True).execute().data
    restricciones = supabase.table("restricciones_fechas").select("*").execute().data

    if not colaboradores:
        print("No hay colaboradores activos.")
        return

    try:
        res_demanda = supabase.table("demanda_operativa").select("*").execute().data
    except Exception:
        res_demanda = []

    demanda_diaria = []
    if res_demanda:
        for item in res_demanda:
            pos_norm = normalizar_posicion(item['posicion'])
            for _ in range(item.get('cantidad', 1)):
                demanda_diaria.append({
                    "sede": item['sede'],
                    "posicion": pos_norm,
                    "turno": item['turno']
                })
    else:
        posiciones_existentes = list(set(normalizar_posicion(c['posicion']) for c in colaboradores if c.get('posicion')))
        for pos in posiciones_existentes:
            demanda_diaria.append({"sede": "Sede 1", "posicion": pos, "turno": "Día"})
            demanda_diaria.append({"sede": "Sede 1", "posicion": pos, "turno": "Noche"})

    historial_semana = {c['id']: [] for c in colaboradores}
    dias = [fecha_inicio + timedelta(days=i) for i in range(7)]
    registros_a_insertar = []

    for d in dias:
        for slot in demanda_diaria:
            candidatos_validos = []
            
            for emp in colaboradores:
                if normalizar_posicion(emp['posicion']) != slot['posicion']: continue
                
                esta_de_vacaciones = False
                for r in restricciones:
                    if r['colaborador_id'] == emp['id']:
                        f_inicio = date.fromisoformat(r['fecha_inicio'])
                        f_fin = date.fromisoformat(r['fecha_fin'])
                        if f_inicio <= d <= f_fin:
                            esta_de_vacaciones = True
                            break
                if esta_de_vacaciones: continue

                turnos_del_colaborador = historial_semana[emp['id']]
                
                if any(t['fecha'] == str(d) for t in turnos_del_colaborador): continue
                if len(turnos_del_colaborador) >= 4: continue
                
                if turnos_del_colaborador:
                    ultimo_turno = turnos_del_colaborador[-1]
                    ayer = str(d - timedelta(days=1))
                    if ultimo_turno['fecha'] == ayer and ultimo_turno['turno'] == "Noche" and slot['turno'] == "Día":
                        continue 

                score = CalculadorEquidad.calcular_score(
                    emp.get('he_acumuladas', 0.0),
                    emp.get('dias_pendientes_recuperacion', 0),
                    (slot['turno'] == "Noche"),
                    len(turnos_del_colaborador)
                )
                candidatos_validos.append((score, emp))

            if candidatos_validos:
                candidatos_validos.sort(key=lambda x: x[0])
                ganador = candidatos_validos[0][1]
                
                historial_semana[ganador['id']].append({"fecha": str(d), "turno": slot['turno']})
                registros_a_insertar.append({
                    "colaborador_id": ganador['id'],
                    "fecha": str(d),
                    "sede": slot['sede'],
                    "turno": slot['turno'],
                    "estado": "PROGRAMADO",
                    "es_hhee": False
                })

    if registros_a_insertar:
        supabase.table("tareo_programado").insert(registros_a_insertar).execute()
        print(f"✅ Se han generado {len(registros_a_insertar)} turnos exitosamente.")

if __name__ == "__main__":
    generar_malla_semanal(date.today())