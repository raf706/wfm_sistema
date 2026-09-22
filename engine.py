def registrar_incidencia_diaria(fecha_inc: date, id_colab: int, tipo: str, requiere_reemplazo: bool):
    """
    Marca un turno como FALTA/DM/PERMISO y opcionalmente busca a un reemplazo en su día libre.
    """
    # 1. Buscar el turno original programado
    turnos = supabase.table("tareo_programado").select("*").eq("fecha", str(fecha_inc)).eq("colaborador_id", id_colab).execute().data
    turno_valido = None
    for t in turnos:
        if t.get('estado') not in ['FALTA', 'DM', 'PERMISO']:
            turno_valido = t
            break
            
    if not turno_valido:
        return False, "El colaborador no está programado para ese día o ya tenía una incidencia."
        
    # 2. Marcar la ausencia en la base de datos
    supabase.table("tareo_programado").update({"estado": tipo}).eq("id", turno_valido['id']).execute()
    
    # 3. Guardarlo como restricción para que el motor general no lo vuelva a programar si se recalcula
    supabase.table("restricciones_fechas").insert({
        "colaborador_id": id_colab, "fecha_inicio": str(fecha_inc), "fecha_fin": str(fecha_inc), "tipo": tipo
    }).execute()
    
    msg = f"✅ Incidencia ({tipo}) registrada con éxito."
    
    # 4. Lógica de Reemplazo Automático
    if requiere_reemplazo:
        colaboradores = supabase.table("colaboradores").select("*").eq("activo", True).execute().data
        colab_ausente = next((c for c in colaboradores if c['id'] == id_colab), None)
        
        if colab_ausente:
            pos_req = normalizar_posicion(colab_ausente['posicion'])
            sede_req = turno_valido['sede']
            turno_req = turno_valido['turno']
            
            # Buscar quiénes ya están trabajando o bloqueados hoy
            turnos_hoy = supabase.table("tareo_programado").select("colaborador_id").eq("fecha", str(fecha_inc)).execute().data
            ocupados_hoy = [t['colaborador_id'] for t in turnos_hoy]
            restricciones = supabase.table("restricciones_fechas").select("*").execute().data
            
            candidatos = []
            for emp in colaboradores:
                if emp['id'] in ocupados_hoy: continue
                if normalizar_posicion(emp['posicion']) != pos_req: continue
                
                # Check si está de vacaciones
                bloqueado = False
                for r in restricciones:
                    if r['colaborador_id'] == emp['id'] and date.fromisoformat(r['fecha_inicio']) <= fecha_inc <= date.fromisoformat(r['fecha_fin']):
                        bloqueado = True
                        break
                if bloqueado: continue
                
                # Check filtro biológico (No Noche -> Día)
                ayer = fecha_inc - timedelta(days=1)
                t_ayer = supabase.table("tareo_programado").select("turno").eq("fecha", str(ayer)).eq("colaborador_id", emp['id']).execute().data
                if t_ayer and t_ayer[0]['turno'] == "Noche" and turno_req == "Día":
                    continue
                    
                candidatos.append(emp)
                
            if candidatos:
                # Toma al primer disponible para la emergencia
                reemplazo = candidatos[0]
                supabase.table("tareo_programado").insert({
                    "colaborador_id": reemplazo['id'],
                    "fecha": str(fecha_inc),
                    "sede": sede_req,
                    "turno": turno_req,
                    "estado": "PROGRAMADO",
                    "es_hhee": True  # Entra como Hora Extra al ser llamado en su día libre
                }).execute()
                msg += f" Se asignó automáticamente a **{reemplazo['nombre']}** como reemplazo [HE]."
            else:
                msg += " ⚠️ No se encontró a nadie de ese cargo disponible para reemplazar (todos ocupados o con restricción biológica)."

    return True, msg