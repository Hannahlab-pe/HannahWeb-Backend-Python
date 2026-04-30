# Hannah AI — Funciones del chat

Documento vivo. Actualizar cada vez que se agrega, modifica o elimina una función del agente.

---

## Estado actual: v1.0 — 30 abr 2026

### Stack
- **Modelo**: GPT-4o (OpenAI) — fallback si no hay `ANTHROPIC_API_KEY`
- **Agente**: LangGraph ReAct (StateGraph + ToolNode)
- **Backend de datos**: NestJS en Railway (`NESTJS_API_URL`)
- **Auth**: JWT compartido con NestJS — el rol viene firmado, el usuario no puede manipularlo

---

## Funciones disponibles

### 1. `consultar_proyectos`
**Archivo:** `app/tools/proyectos.py`

Consulta proyectos, módulos (implementaciones) y tareas del tablero kanban.

| Campo devuelto | Descripción |
|---|---|
| Nombre del proyecto | — |
| Estado | activo, pausado, completado, etc. |
| Progreso global | % |
| Fecha de entrega | — |
| Encargado(s) | nombre(s) |
| Cliente | solo visible para admin/subadmin |
| Módulos | lista de implementaciones del proyecto |
| Tareas por módulo | agrupadas por columna: pendiente, en_progreso, en_revision, completado |
| Prioridad de tarea | — |
| Responsable de tarea | — |
| Fecha límite de tarea | — |

**Endpoint según rol:**
- `admin` → `GET /proyectos` (todos los proyectos del sistema)
- `subadmin` → `GET /proyectos/mis-encargados` (proyectos donde es encargado)
- `cliente` → `GET /proyectos/mis-proyectos` (solo los suyos)

**Cuándo se activa:** cualquier pregunta sobre proyectos, módulos, tareas, avance, pendientes, encargados.

---

### 2. `consultar_miembros_proyecto`
**Archivo:** `app/tools/miembros.py`

Devuelve el equipo asignado a un proyecto específico. Acepta el nombre del proyecto (parcial, sin importar mayúsculas).

| Campo devuelto | Descripción |
|---|---|
| Encargados del proyecto | nombre + email |
| Responsables de tareas | agrupados por persona: nombre, email, lista de tareas con módulo y estado |

**Flujo de aclaración integrado:**
- Si el nombre no coincide con ningún proyecto → devuelve lista de proyectos disponibles para que el LLM pida aclaración
- Si hay varias coincidencias parciales → devuelve las opciones y pide que el usuario elija una
- Si hay coincidencia única → devuelve el equipo completo

**Endpoint usado:** mismo que `consultar_proyectos` según rol + `GET /implementaciones/proyecto/:id`

**Cuándo se activa:** "¿quién trabaja en X?", "¿quiénes están asignados a X?", "equipo del proyecto X", "responsables de X".

---

### 3. `consultar_tickets`
**Archivo:** `app/tools/tickets.py`

Consulta tickets de soporte e incidencias.

| Campo devuelto | Descripción |
|---|---|
| Título | — |
| Estado | abierto, en_revision, cerrado, resuelto |
| Prioridad | baja, media, alta, crítica |
| Resumen | total / abiertos / cerrados |

**Endpoint según rol:**
- `admin` / `subadmin` → `GET /tickets` (todos)
- `cliente` → `GET /tickets/mis-tickets` (solo los suyos)

**Cuándo se activa:** preguntas sobre tickets, incidencias, soporte, problemas reportados.

---

### 3. `consultar_reuniones`
**Archivo:** `app/tools/reuniones.py`

Consulta reuniones y agenda. Separa automáticamente próximas vs pasadas.

| Campo devuelto | Descripción |
|---|---|
| Título | — |
| Fecha y hora | formateada `dd/mm/yyyy a las HH:MM` |
| Tipo | videollamada, presencial, etc. |
| Link de acceso | link de Google Meet u otro |
| Proyecto relacionado | si aplica |
| Agenda/descripción | si tiene |

**Ordenamiento:** próximas (más cercana primero, hasta 5), pasadas (más reciente primero, hasta 3).

**Endpoint según rol:**
- `admin` / `subadmin` → `GET /reuniones` (todas)
- `cliente` → `GET /reuniones/mis-reuniones` (solo las suyas)

**Cuándo se activa:** preguntas sobre reuniones, agenda, videollamadas, calendario, "cuándo nos vemos".

---

## Comportamiento del chat

### Identidad del usuario
El chat conoce nombre, email y rol del usuario via JWT. Si alguien pregunta "quién soy", responde con esos datos. El usuario **no puede cambiar su rol** desde el chat — viene firmado en el token.

### Preguntas sobre Hannah AI
Responde quién es, para qué sirve, quién la creó — siempre en contexto HannahLab.

### Temas rechazados
El chat rechaza y redirige (sin elaborar) preguntas sobre:
- Conocimiento general (ciencia, historia, matemáticas, recetas, etc.)
- Metodologías genéricas (Fibonacci, Scrum, Kanban en abstracto, Agile)
- Programación y código
- Noticias, política, clima
- Cualquier tema externo a HannahLab

---

## Funciones pendientes / roadmap

> Agregar aquí las funciones que se quieren implementar a futuro.

- [ ] **Crear ticket** desde el chat — el usuario dicta el problema, la IA abre el ticket
- [ ] **Resumen de sprint** — IA genera un resumen del estado de todas las tareas de un proyecto
- [ ] **Filtrar tareas por responsable** — "¿qué tiene pendiente Stefan?"
- [ ] **Alertas de vencimiento** — "¿qué tareas vencen esta semana?"

---

## Historial de cambios

| Fecha | Cambio |
|---|---|
| 2026-04-28 | v1.0 — deploy inicial en Railway. Tools: proyectos, tickets, reuniones. |
| 2026-04-28 | Seguridad: rol propagado desde JWT firmado, no desde el chat. |
| 2026-04-28 | System prompt: rechazo de temas fuera de HannahLab. |
| 2026-04-29 | Fix: GPT-4o dejaba de responder preguntas válidas sobre proyectos ("base de datos"). |
| 2026-04-30 | Fix: GPT-4o rechazaba preguntas sobre la propia IA ("quién eres", "quién te creó"). |
| 2026-04-30 | Nueva tool `consultar_miembros_proyecto`: equipo por proyecto con flujo de aclaración integrado. |
