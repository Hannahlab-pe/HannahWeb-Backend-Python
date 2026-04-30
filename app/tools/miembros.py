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
    if rol == "admin":
        return "/proyectos"
    if rol == "subadmin":
        return "/proyectos/mis-encargados"
    return "/proyectos/mis-proyectos"


@tool
async def consultar_miembros_proyecto(nombre_proyecto: str, config: RunnableConfig) -> str:
    """
    Devuelve todos los miembros asignados a un proyecto específico:
    encargados del proyecto y responsables de cada tarea en todos sus módulos.

    Úsala cuando el usuario pregunte:
    - "¿quién trabaja en el proyecto X?"
    - "¿quiénes están asignados a X?"
    - "¿quién es el responsable de X?"
    - "muéstrame el equipo del proyecto X"

    Si no encuentras el proyecto por el nombre dado, devuelves la lista de proyectos
    disponibles para que el usuario pueda aclarar a cuál se refiere.
    """
    cfg = config.get("configurable", {})
    token = cfg.get("token", "")
    rol = cfg.get("user_rol", "cliente")

    try:
        proyectos = await _fetch(_endpoint_proyectos(rol), token)
    except httpx.HTTPStatusError as e:
        return f"Error al obtener proyectos: {e.response.status_code}"
    except Exception as e:
        return f"Error inesperado: {str(e)}"

    if not proyectos:
        return "No hay proyectos visibles para este usuario."

    # Búsqueda por nombre — case insensitive, coincidencia parcial
    nombre_lower = nombre_proyecto.strip().lower()
    coincidencias = [p for p in proyectos if nombre_lower in p["nombre"].lower()]

    if not coincidencias:
        nombres = [p["nombre"] for p in proyectos]
        return (
            f'No encontré ningún proyecto con el nombre "{nombre_proyecto}".\n'
            f"Proyectos disponibles: {', '.join(nombres)}.\n"
            f"¿A cuál te referías?"
        )

    if len(coincidencias) > 1:
        nombres = [p["nombre"] for p in coincidencias]
        return (
            f'Encontré varios proyectos que coinciden con "{nombre_proyecto}":\n'
            + "\n".join(f"- {n}" for n in nombres)
            + "\n¿A cuál te referías exactamente?"
        )

    proyecto = coincidencias[0]
    lines = [f"**Proyecto: {proyecto['nombre']}**\n"]

    # Encargados del proyecto
    encargados = proyecto.get("encargados", [])
    if encargados:
        lines.append("**Encargados del proyecto:**")
        for e in encargados:
            lines.append(f"- {e['nombre']} ({e.get('email', '—')})")
    else:
        lines.append("Sin encargados asignados al proyecto.")

    # Responsables por módulo/tarea
    impls = proyecto.get("implementaciones", [])
    if not impls:
        lines.append("\nSin módulos registrados aún.")
        return "\n".join(lines)

    try:
        impl_list = await _fetch(f"/implementaciones/proyecto/{proyecto['id']}", token)
    except Exception:
        impl_list = []

    impl_map = {i["id"]: i for i in impl_list}

    # Recopilar responsables únicos con sus tareas
    responsables_map: dict[str, dict] = {}  # nombre → {email, tareas[]}

    for impl in impls:
        impl_data = impl_map.get(impl["id"], {})
        tareas = impl_data.get("tareas", [])
        modulo_nombre = impl["nombre"]

        for tarea in tareas:
            for resp in tarea.get("responsables", []):
                nombre = resp.get("nombre", "—")
                email = resp.get("email", "—")
                if nombre not in responsables_map:
                    responsables_map[nombre] = {"email": email, "tareas": []}
                responsables_map[nombre]["tareas"].append(
                    f"{modulo_nombre} › {tarea['titulo']} [{tarea.get('columna', '—')}]"
                )

    if responsables_map:
        lines.append("\n**Responsables de tareas:**")
        for nombre, data in responsables_map.items():
            lines.append(f"\n- **{nombre}** ({data['email']})")
            for t in data["tareas"][:6]:
                lines.append(f"  · {t}")
            if len(data["tareas"]) > 6:
                lines.append(f"  · ...y {len(data['tareas']) - 6} tarea(s) más")
    else:
        lines.append("\nNinguna tarea tiene responsables asignados.")

    return "\n".join(lines)
