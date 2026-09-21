from supabase import create_client, Client
from datetime import date, timedelta

# Configuración de conexión
SUPABASE_URL = "https://vsnyqynjaxdmofyewfcq.supabase.co"
# ¡No olvides pegar aquí de nuevo tu clave!
SUPABASE_KEY = "sb_publishable__wmHvw9dfAcu-o78te3iMg_9JqpAb_P" 

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class CalculadorEquidad:
    @staticmethod
    def calcular_score(he_acumuladas: float, dias_deuda: int, es_noche: bool, turnos_semana: int) -> float:
        score = he_acumuladas * 10.0
        if es_noche: score += 15.0
        if dias_deuda > 0: score -= 50.0
        # Balanceo: penalizar levemente si ya tiene turnos asignados para repartir el trabajo
        score += turnos_semana * 20.0 
        return score

def generar_malla_semanal(fecha_inicio: date):
    print(f"\n==================================================")
    print(f" GENERANDO TAREO SEMANAL (RÉGIMEN 4x3)")
    print(f"==================================================\n")

    # Limpiar datos de pruebas anteriores para no duplicar
    supabase.table("tareo_programado").delete().neq("id", 0).execute()

    res = supabase.table("colaboradores").select("*").eq("activo", True).execute()
    colaboradores = res.data

    # Ahora guardamos un historial detallado por día y turno
    historial_semana = {c['id']: [] for c in colaboradores}
    dias = [fecha_inicio + timedelta(days=i) for i in range(7)]
    
    demanda_diaria = [
        {"sede": "Sede 1", "posicion": "A", "turno": "Día"},
        {"sede": "Sede 1", "posicion": "A", "turno": "Noche"},
        {"sede": "Sede 2", "posicion": "B", "turno": "Día"},
        {"sede": "Sede 3", "posicion": "C", "turno": "Día"},
    ]

    registros_a_insertar = []

    for d in dias:
        print(f"📅 {d}:")
        
        for slot in demanda_diaria:
            candidatos_validos = []
            
            for emp in colaboradores:
                # 1. Filtro de Posición
                if emp['posicion'] != slot['posicion']: continue
                
                turnos_del_colaborador = historial_semana[emp['id']]
                
                # 2. REGLA: Máximo 1 turno por día
                ya_trabajo_hoy = any(t['fecha'] == str(d) for t in turnos_del_colaborador)
                if ya_trabajo_hoy: continue
                    
                # 3. REGLA: Régimen 4x3 (Máximo 4 turnos en la semana)
                if len(turnos_del_colaborador) >= 4: continue
                
                # 4. REGLA: Filtro biológico (Prohibido Noche -> Día seguido)
                if turnos_del_colaborador:
                    ultimo_turno = turnos_del_colaborador[-1]
                    ayer = str(d - timedelta(days=1))
                    if ultimo_turno['fecha'] == ayer and ultimo_turno['turno'] == "Noche" and slot['turno'] == "Día":
                        continue # Bloqueado por fatiga

                # Evaluar Score
                score = CalculadorEquidad.calcular_score(
                    he_acumuladas=emp['he_acumuladas'],
                    dias_deuda=emp['dias_pendientes_recuperacion'],
                    es_noche=(slot['turno'] == "Noche"),
                    turnos_semana=len(turnos_del_colaborador) # Para repartir equitativamente
                )
                
                candidatos_validos.append((score, emp))

            # Seleccionar al mejor candidato (menor score)
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
                print(f"   [OK] {slot['sede']} | {slot['turno']} ➔ {ganador['nombre']}")
            else:
                print(f"   [ALERTA ROJA] {slot['sede']} | {slot['turno']} ➔ SIN PERSONAL (Requiere HHEE o retén)")

    if registros_a_insertar:
        print("\nGuardando malla 4x3 en Supabase...")
        supabase.table("tareo_programado").insert(registros_a_insertar).execute()
        print("✅ ¡Malla 4x3 perfecta guardada exitosamente!")

if __name__ == "__main__":
    generar_malla_semanal(date.today())