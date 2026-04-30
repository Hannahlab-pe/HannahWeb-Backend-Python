import httpx
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from typing import Optional
from ..core.config import settings


@tool
async def crear_ticket(
    titulo: str,
    descripcion: str,
    prioridad: str,
    config: RunnableConfig,
    tipo: Optional[str] = "incidencia",
    proyecto_nombre: Optional[str] = None,
) -> str:
    """
    Crea un ticket de soporte en el sistema HannahLab.

    IMPORTANTE: solo llama esta herramienta DESPUÉS de que el usuario haya
    confirmado explícitamente los datos del ticket.

    Args:
        titulo: Título corto y descriptivo del ticket (máx. 200 caracteres).
        descripcion: Descripción detallada del problema o solicitud.
        prioridad: Urgencia del ticket. Valores válidos: 'baja', 'media', 'alta', 'critica'.
        tipo: Categoría del ticket. Valores válidos: 'bug', 'incidencia', 'comentario', 'aporte'.
              Por defecto 'incidencia'.
        proyecto_nombre: Nombre (parcial) del proyecto relacionado. La herramienta lo resuelve
                         a ID automáticamente. Si hay ambigüedad devuelve las opciones para
                         que el usuario elija. Omitir si el ticket no está ligado a un proyecto.
    """
    cfg = config.get("configurable", {})
    token = cfg.get("token", "")
    rol   = cfg.get("user_rol", "cliente")

    PRIORIDADES_VALIDAS = {"baja", "media", "alta", "critica"}
    TIPOS_VALIDOS       = {"bug", "incidencia", "comentario", "aporte"}

    prioridad_norm = prioridad.lower().strip()
    tipo_norm      = (tipo or "incidencia").lower().strip()

    if prioridad_norm not in PRIORIDADES_VALIDAS:
        return f"Prioridad inválida: '{prioridad}'. Valores válidos: baja, media, alta, critica."
    if tipo_norm not in TIPOS_VALIDOS:
        return f"Tipo inválido: '{tipo}'. Valores válidos: bug, incidencia, comentario, aporte."

    # ── Resolver proyecto_nombre → proyecto_id ────────────────────────
    proyecto_id: Optional[str] = None
    if proyecto_nombre:
        try:
            endpoint = (
                "/proyectos" if rol == "admin"
                else "/proyectos/mis-encargados" if rol == "subadmin"
                else "/proyectos/mis-proyectos"
            )
            async with httpx.AsyncClient(base_url=settings.nestjs_api_url, timeout=10) as client:
                rp = await client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
                rp.raise_for_status()
                proyectos = rp.json()

            busqueda = proyecto_nombre.lower().strip()
            coincidencias = [p for p in proyectos if busqueda in p.get("nombre", "").lower()]

            if not coincidencias:
                nombres = [p["nombre"] for p in proyectos]
                lista   = "\n".join(f"- {n}" for n in nombres)
                return (
                    f"No encontré ningún proyecto con el nombre '{proyecto_nombre}'.\n"
                    f"Proyectos disponibles:\n{lista}\n\n"
                    "Indica el nombre exacto o di 'sin proyecto' para crear el ticket sin proyecto."
                )
            if len(coincidencias) > 1:
                lista = "\n".join(f"- {p['nombre']}" for p in coincidencias)
                return (
                    f"Hay varios proyectos que coinciden con '{proyecto_nombre}':\n{lista}\n\n"
                    "¿A cuál te refieres? Escribe el nombre más completo."
                )

            proyecto_id = coincidencias[0]["id"]

        except Exception:
            pass  # si falla la resolución, creamos el ticket sin proyecto

    body: dict = {
        "titulo":      titulo.strip(),
        "descripcion": descripcion.strip(),
        "prioridad":   prioridad_norm,
        "tipo":        tipo_norm,
    }
    if proyecto_id:
        body["proyectoId"] = proyecto_id

    try:
        async with httpx.AsyncClient(base_url=settings.nestjs_api_url, timeout=10) as client:
            r = await client.post(
                "/tickets",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            ticket = r.json()

        tid           = ticket.get("id", "—")
        proyecto_info = f"\n- **Proyecto:** {coincidencias[0]['nombre']}" if proyecto_id else ""
        return (
            f"Ticket creado exitosamente.\n"
            f"- **ID:** `{tid}`\n"
            f"- **Título:** {ticket.get('titulo')}\n"
            f"- **Prioridad:** {ticket.get('prioridad')}\n"
            f"- **Estado:** {ticket.get('estado', 'abierto')}"
            f"{proyecto_info}\n"
        )

    except httpx.HTTPStatusError as e:
        return f"Error al crear el ticket: {e.response.status_code} — {e.response.text}"
    except Exception as e:
        return f"Error inesperado al crear ticket: {str(e)}"


@tool
async def consultar_tickets(query: str, config: RunnableConfig) -> str:
    """
    Consulta los tickets de soporte: título, estado y prioridad.
    El alcance se ajusta automáticamente al rol del usuario:
    - admin/subadmin: ven todos los tickets del sistema
    - cliente: ve solo sus propios tickets
    """
    cfg = config.get("configurable", {})
    token = cfg.get("token", "")
    rol = cfg.get("user_rol", "cliente")
    endpoint = "/tickets" if rol in ("admin", "subadmin") else "/tickets/mis-tickets"
    try:
        async with httpx.AsyncClient(base_url=settings.nestjs_api_url, timeout=10) as client:
            r = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            tickets = r.json()

        if not tickets:
            return "No hay tickets registrados para este usuario."

        abiertos = [t for t in tickets if t.get("estado") not in ("cerrado", "resuelto")]
        cerrados = [t for t in tickets if t.get("estado") in ("cerrado", "resuelto")]

        lines = [f"Total: {len(tickets)} ticket(s) — {len(abiertos)} abierto(s), {len(cerrados)} cerrado(s)."]

        if abiertos:
            lines.append("\n**Tickets abiertos:**")
            for t in abiertos[:8]:
                prioridad = t.get("prioridad", "—")
                estado = t.get("estado", "—")
                lines.append(f"- [{estado.upper()}] **{t['titulo']}** · prioridad: {prioridad}")

        if cerrados:
            lines.append(f"\n**Cerrados recientemente:** {len(cerrados)}")

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"Error al consultar tickets: {e.response.status_code}"
    except Exception as e:
        return f"Error inesperado al consultar tickets: {str(e)}"
