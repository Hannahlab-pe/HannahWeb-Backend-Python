import httpx
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from ..core.config import settings


async def _fetch(path: str, token: str):
    async with httpx.AsyncClient(base_url=settings.nestjs_api_url, timeout=10) as client:
        r = await client.get(path, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()


def _endpoint_proyectos(rol: str) -> str:
    """Selecciona el endpoint del backend según el rol firmado en el JWT."""
    if rol == "admin":
        return "/proyectos"                      # todos los proyectos del sistema
    if rol == "subadmin":
        return "/proyectos/mis-encargados"       # proyectos donde es encargado
    return "/proyectos/mis-proyectos"            # cliente: solo los suyos


@tool
async def consultar_proyectos(query: str, config: RunnableConfig) -> str:
    """
    Consulta TODA la información de los proyectos visibles para el usuario actual:
    nombre, estado, progreso, fecha de entrega, encargados, módulos (implementaciones)
    y tareas con su estado actual.

    El alcance se ajusta automáticamente al rol del usuario:
    - admin: ve todos los proyectos del sistema
    - subadmin: ve los proyectos donde es encargado
    - cliente: ve sus propios proyectos

    Úsala para CUALQUIER pregunta sobre proyectos, módulos, tareas, avance o pendientes.
    """
    cfg = config.get("configurable", {})
    token = cfg.get("token", "")
    rol = cfg.get("user_rol", "cliente")

    try:
        proyectos = await _fetch(_endpoint_proyectos(rol), token)

        if not proyectos:
            if rol == "admin":
                return "No hay proyectos registrados en el sistema."
            if rol == "subadmin":
                return "No tienes proyectos asignados como encargado."
            return "No hay proyectos asignados a esta cuenta."

        lines = [f"Se encontraron {len(proyectos)} proyecto(s):\n"]

        for p in proyectos:
            estado = p.get("estado", "—")
            progreso = p.get("progreso", 0)
            fecha = p.get("fechaEntrega")
            fecha_str = fecha[:10] if fecha else "Sin fecha definida"
            encargados = [e["nombre"] for e in p.get("encargados", [])]
            enc_str = ", ".join(encargados) if encargados else "Sin encargado asignado"
            cliente = p.get("cliente", {})
            cliente_nombre = cliente.get("nombre") if isinstance(cliente, dict) else None
            cliente_str = f" | Cliente: {cliente_nombre}" if cliente_nombre and rol in ("admin", "subadmin") else ""

            lines.append(f"== Proyecto: {p['nombre']} =={cliente_str}")
            lines.append(f"Estado: {estado} | Progreso global: {progreso}% | Entrega: {fecha_str}")
            lines.append(f"Encargado(s): {enc_str}")

            impls = p.get("implementaciones", [])
            if not impls:
                lines.append("Sin módulos registrados aún.\n")
                continue

            try:
                impl_list = await _fetch(f"/implementaciones/proyecto/{p['id']}", token)
            except Exception:
                impl_list = []

            impl_map = {i["id"]: i for i in impl_list}

            for impl in impls:
                impl_data = impl_map.get(impl["id"], {})
                tareas = impl_data.get("tareas", [])

                lines.append(f"\n  Modulo: {impl['nombre']}")

                if not tareas:
                    lines.append("  Sin tareas registradas.")
                    continue

                pendientes  = [t for t in tareas if t.get("columna") == "pendiente"]
                en_prog     = [t for t in tareas if t.get("columna") == "en_progreso"]
                en_rev      = [t for t in tareas if t.get("columna") == "en_revision"]
                completadas = [t for t in tareas if t.get("columna") == "completado"]

                lines.append(f"  Resumen: {len(tareas)} tareas total — {len(completadas)} completadas, {len(en_prog)} en progreso, {len(en_rev)} en revision, {len(pendientes)} pendientes")

                def _fmt_tarea(t: dict) -> str:
                    col = t.get("columna", "—")
                    prio = t.get("prioridad", "")
                    resp = t["responsables"][0]["nombre"] if t.get("responsables") else "Sin responsable"
                    fecha_t = t.get("fechaLimite", "")
                    fecha_t_str = f" | limite: {fecha_t}" if fecha_t else ""
                    return f"    - [{col}] {t['titulo']} (prioridad: {prio}, responsable: {resp}{fecha_t_str})"

                activas = pendientes + en_prog + en_rev
                if activas:
                    lines.append("  Tareas activas:")
                    for t in activas[:10]:
                        lines.append(_fmt_tarea(t))
                else:
                    lines.append("  Todas las tareas estan completadas.")

                if completadas:
                    lines.append("  Tareas completadas:")
                    for t in completadas[:20]:
                        lines.append(_fmt_tarea(t))

            lines.append("")

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"Error al consultar proyectos: {e.response.status_code}"
    except Exception as e:
        return f"Error inesperado: {str(e)}"
