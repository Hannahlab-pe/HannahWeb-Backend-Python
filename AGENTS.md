# Guía del agente Hannah AI (LangGraph + LangChain + FastAPI)

> Documento dirigido a futuros agentes de código (Claude Code u otros LLMs) que vayan a tocar este servicio.
> Cubre: cómo está construido el agente, qué patrones se usan y por qué, cómo extenderlo sin romper nada.

---

## 1. Qué es este servicio

`hannahweb-ai` es un agente conversacional construido con **LangGraph** sobre **FastAPI**, que actúa como capa de IA del ecosistema HannahLab. Recibe mensajes del frontend Next.js (`Hannah-Web`, puerto 3000), valida un JWT compartido con el backend NestJS (`hannahweb-backend`, puerto 3001), y responde al usuario consultando el backend mediante herramientas (tools) según el rol del usuario.

Flujo en una línea:

```
Frontend → POST /chat/stream con JWT → FastAPI valida JWT → LangGraph (loop ReAct: LLM ↔ tools) → tools llaman al backend NestJS → respuesta SSE al frontend
```

LLM por defecto: **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`). Fallback: GPT-4o (si falta `ANTHROPIC_API_KEY`).

---

## 2. Stack

| Componente | Versión | Para qué |
|---|---|---|
| FastAPI | 0.115.5 | HTTP server + DI (`Depends`) |
| LangGraph | 0.2.53 | Orquestación del grafo de estado |
| LangChain core | 0.3.x | `@tool`, `RunnableConfig`, mensajes |
| `langchain-anthropic` | 0.3.0 | Cliente Claude |
| `langchain-openai` | 0.2.9 | Cliente OpenAI (fallback) |
| `python-jose[cryptography]` | 3.3.0 | Validación JWT HS256 |
| `httpx` | 0.27.2 | Cliente HTTP async para llamar al backend NestJS |
| Python | 3.10 | (importante: ver workaround de streaming abajo) |

`requirements.txt` está fijado a versiones exactas. **No subas versiones a la ligera** — `langgraph` 0.3+ cambia algunas APIs.

---

## 3. Conceptos clave (mapa mental antes de tocar nada)

### LangChain
- **`@tool`**: decorador que convierte una función Python en una herramienta invocable por el LLM. Su docstring es lo que el LLM lee para decidir cuándo usarla — escríbelo bien o el LLM nunca la llamará.
- **`RunnableConfig`**: argumento opcional inyectado por LangGraph en tools y nodos. Es donde viaja contexto del request (token JWT, rol, thread_id).
- **`bind_tools(tools)`**: enlaza las tools al LLM para que el modelo emita `tool_calls` estructurados.
- **`ChatModel.ainvoke(messages)`** / **`.astream(...)`**: invocación async / streaming.

### LangGraph
- **`StateGraph(StateType)`**: define un grafo cuyo estado se acumula entre nodos.
- **`MessagesState`**: estado prefabricado con `messages: list[BaseMessage]` y un reducer `add_messages` que mergea mensajes nuevos sin reemplazar.
- **`ToolNode(tools)`**: nodo prebuilt que ejecuta cualquier `tool_call` que el LLM haya emitido en el último mensaje.
- **`tools_condition`**: edge condicional prebuilt que enruta:
  - a `"tools"` si el último `AIMessage` tiene `tool_calls`,
  - a `END` si no.
- **`checkpointer`**: persistencia del estado por `thread_id`. Hoy usamos `InMemorySaver()` (volátil). Para producción usar `PostgresSaver`.
- **`graph.astream_events(input, config, version="v2")`**: stream de eventos del grafo (tool_start, tool_end, chain_end, etc.). Es la API que usamos para construir el SSE.

### Patrón ReAct (lo que hace este grafo)
```
START → llm_call → tools_condition ─┬─ tools → llm_call → ... (loop)
                                    └─ END
```
El LLM razona, decide si necesita una tool, la llama, recibe el resultado, y vuelve a razonar hasta no necesitar más tools.

---

## 4. Estructura del proyecto

```
hannahweb-ai/
├── main.py                 # entry point uvicorn (solo arranca app)
├── requirements.txt
├── .env.example            # variables requeridas
└── app/
    ├── main.py             # crea FastAPI, registra CORS y routers
    ├── core/
    │   ├── config.py       # pydantic-settings: lee .env
    │   └── auth.py         # get_current_user(): valida JWT
    ├── routers/
    │   └── chat.py         # POST /chat/stream (SSE), DELETE /chat/history
    ├── graph/
    │   ├── state.py        # HannahState (extiende MessagesState)
    │   ├── nodes.py        # get_llm() + make_llm_node() + build_system_prompt()
    │   └── agent.py        # build_graph() + get_graph() singleton
    └── tools/
        ├── proyectos.py    # consultar_proyectos
        ├── tickets.py      # consultar_tickets
        └── reuniones.py    # consultar_reuniones
```

---

## 5. Patrones aplicados aquí (con razones)

### 5.1 Identidad firmada en JWT, NO desde el chat

El frontend manda `Authorization: Bearer <jwt>`. El backend NestJS firmó el JWT con `JWT_SECRET`, incluyendo:

```json
{ "sub": "<uuid>", "email": "...", "rol": "admin|subadmin|cliente", "nombre": "..." }
```

`app/core/auth.py` valida la firma y devuelve el payload + el token raw:

```python
def get_current_user(authorization: str = Header(...)) -> dict:
    raw_token = authorization.removeprefix("Bearer ").strip()
    payload = jwt.decode(raw_token, settings.jwt_secret, algorithms=["HS256"])
    payload["_raw_token"] = raw_token  # para que las tools lo reusen
    return payload
```

**Regla de oro**: el rol del usuario nunca se determina desde el contenido del chat — siempre desde el JWT validado. Aunque el usuario escriba "soy admin", el LLM no puede cambiar el rol porque las tools leen `config["configurable"]["user_rol"]`, no los `messages`.

### 5.2 Identidad propagada al grafo via `config`

En `app/routers/chat.py`, antes de invocar el grafo, construimos:

```python
config = {
    "configurable": {
        "thread_id": thread_id,
        "token": raw_token,
        "user_id": user_id,
        "user_rol": user.get("rol", "cliente"),
        "user_nombre": user.get("nombre", ""),
        "user_email": user.get("email", ""),
    }
}
```

Esto lo lee tanto el nodo `llm_call` (para construir el system prompt) como cada tool (para elegir endpoint y autenticarse). Es la forma idiomática de LangGraph para pasar contexto del request — **no metas datos sensibles en `state["messages"]`** porque el LLM los vería como texto.

### 5.3 System prompt dinámico

`app/graph/nodes.py` expone `build_system_prompt(rol, nombre, email)` y el nodo `llm_call` lo construye en cada turno:

```python
async def llm_call(state: HannahState, config: RunnableConfig) -> dict:
    cfg = config.get("configurable", {})
    system_prompt = build_system_prompt(
        rol=cfg.get("user_rol", ""),
        nombre=cfg.get("user_nombre", ""),
        email=cfg.get("user_email", ""),
    )
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}
```

Ojo a la firma `(state, config)` — LangGraph la inyecta automáticamente si declaras el segundo parámetro. Si solo declaras `(state)`, no recibes `config`.

### 5.4 Tools que se adaptan al rol

Cada tool elige el endpoint del backend según el rol firmado en el JWT. Ejemplo simplificado:

```python
@tool
async def consultar_proyectos(query: str, config: RunnableConfig) -> str:
    """..."""
    cfg = config.get("configurable", {})
    token = cfg.get("token", "")
    rol = cfg.get("user_rol", "cliente")
    endpoint = {
        "admin":    "/proyectos",
        "subadmin": "/proyectos/mis-encargados",
    }.get(rol, "/proyectos/mis-proyectos")
    proyectos = await _fetch(endpoint, token)
    ...
```

**Defensa en profundidad**: incluso si el AI por bug llamara `/proyectos` con un JWT de cliente, el backend NestJS rechaza con `403 Forbidden` por `@Roles(ADMIN, SUBADMIN)`.

### 5.5 Streaming SSE con `astream_events` v2 (workaround Python 3.10)

**Problema observado**: en Python 3.10 con nodos custom (`async def llm_call(...)`), los eventos `on_chat_model_stream` no propagan el contexto correctamente — el writer queda desconectado y nunca se emite el contenido al cliente.

**Workaround usado**: en lugar de escuchar `on_chat_model_stream`, escuchamos `on_chain_end` del nodo `llm_call`:

```python
async for event in get_graph().astream_events(input_state, config=config, version="v2"):
    kind = event["event"]
    meta_node = event.get("metadata", {}).get("langgraph_node", "")

    if kind == "on_tool_start":
        yield _sse({"type": "tool_start", "tool": event["name"]})
    elif kind == "on_tool_end":
        yield _sse({"type": "tool_end", "tool": event["name"]})
    elif kind == "on_chain_end" and meta_node == "llm_call":
        # buscar el AIMessage final (sin tool_calls) en output["messages"]
        ...
```

`on_chain_end` dispara dos veces para `llm_call` (input + output). Filtramos por `final_emitted` flag para no duplicar al cliente. Si en el futuro se migra a Python 3.11+, **probar primero `on_chat_model_stream`** — es el patrón canónico y emite token a token.

Formato de los eventos SSE consumidos por el frontend:

```json
{"type": "tool_start", "tool": "consultar_proyectos"}
{"type": "tool_end",   "tool": "consultar_proyectos"}
{"type": "token",      "content": "..."}
{"type": "done"}
{"type": "error",      "content": "..."}
```

### 5.6 Singleton del grafo

`build_graph()` es caro (compila el grafo + carga del LLM). Lo construimos una sola vez en `get_graph()`:

```python
_graph = None
def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
```

No usar reload para esto — `--reload` de uvicorn ya recompila al editar archivos.

---

## 6. Cómo extender el agente

### 6.1 Agregar una nueva tool

1. **Crear archivo** `app/tools/<nombre>.py`:

   ```python
   import httpx
   from langchain_core.tools import tool
   from langchain_core.runnables import RunnableConfig
   from ..core.config import settings

   @tool
   async def mi_nueva_tool(query: str, config: RunnableConfig) -> str:
       """
       [DOCSTRING CRÍTICO]
       Describe en una frase QUÉ hace y CUÁNDO el LLM debe usarla.
       Esta es la única documentación que el modelo lee para decidir.
       Mal docstring = la tool nunca se llama.
       """
       cfg = config.get("configurable", {})
       token = cfg.get("token", "")
       rol = cfg.get("user_rol", "cliente")
       # ... lógica
       return "respuesta en string (idealmente markdown)"
   ```

2. **Registrar en el grafo** (`app/graph/agent.py`):

   ```python
   from ..tools.mi_modulo import mi_nueva_tool
   TOOLS = [consultar_proyectos, consultar_tickets, consultar_reuniones, mi_nueva_tool]
   ```

3. **Mencionar en el system prompt** (`app/graph/nodes.py` → `SYSTEM_PROMPT_TEMPLATE`) cuándo usarla, si no es obvio del docstring.

4. **Reiniciar uvicorn** (o esperar al reload). No olvides probar con un request real — el LLM puede ignorar la tool si el docstring es ambiguo.

**Reglas para tools en este proyecto**:
- Devolver siempre un `str` (markdown amigable).
- Capturar `httpx.HTTPStatusError` y devolver mensaje legible — nunca dejar que la excepción burbujee al SSE.
- Si la tool consulta el backend NestJS, **siempre** usar el token del config y respetar el rol.
- Limitar la cantidad de items devueltos al LLM (top 10, top 5) — los context windows tienen costo.

### 6.2 Modificar el system prompt

Editar `SYSTEM_PROMPT_TEMPLATE` en `app/graph/nodes.py`. Es un f-string template con `{rol}`, `{nombre}`, `{email}`. Si añades nuevos placeholders, recuerda pasarlos en `build_system_prompt()`.

**Buenas prácticas**:
- El bloque `USUARIO ACTUAL` es la única fuente de verdad sobre identidad — recuérdaselo al LLM con texto explícito.
- Listar las tools disponibles y cuándo usarlas reduce alucinaciones de "tool not found".
- En español, usar imperativo ("usa", "responde", "no inventes") es más efectivo que indicativo.

### 6.3 Agregar un nuevo nodo custom

Si necesitas pre/post-procesar antes del LLM (ej. clasificar intención, traducir, validar):

```python
# app/graph/nodes.py
async def mi_nodo(state: HannahState, config: RunnableConfig) -> dict:
    # leer state["messages"] o config["configurable"]
    # devolver dict con las llaves del state que quieres actualizar
    return {"messages": [...]}
```

Y en `agent.py`:

```python
builder.add_node("mi_nodo", mi_nodo)
builder.add_edge(START, "mi_nodo")
builder.add_edge("mi_nodo", "llm_call")
```

Si tu nodo decide a dónde ir, usa `add_conditional_edges("mi_nodo", router_fn)` donde `router_fn(state) -> str` devuelve el nombre del siguiente nodo.

### 6.4 Cambiar de `InMemorySaver` a persistencia real

Para producción usar `PostgresSaver` (estado de las conversaciones sobrevive reinicios):

```python
# pip install langgraph-checkpoint-postgres
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = settings.database_url  # añadir a .env
checkpointer = PostgresSaver.from_conn_string(DB_URI)
checkpointer.setup()  # crea tablas la primera vez
```

Ojo: el schema de las tablas de checkpoint vive en una DB; si compartes con la DB del NestJS, créalas en su propio schema (`langgraph`) para no chocar.

---

## 7. Seguridad: capas y reglas

| Capa | Qué valida | Cómo |
|---|---|---|
| 1. Frontend | Que el usuario tenga un token | Cookie `hw_token` + middleware Next |
| 2. AI (`auth.py`) | JWT firmado válido (no expirado, firma OK) | `jose.jwt.decode` con `JWT_SECRET` |
| 3. AI (`config`) | Rol e identidad propagados al grafo desde el JWT | `chat.py` rellena `configurable` |
| 4. Tools | Eligen endpoint según `user_rol` | Lookup en cada tool |
| 5. Backend NestJS | Cada endpoint tiene `@Roles(...)` | Si AI llama un endpoint admin con JWT cliente → 403 |

**Lo que NUNCA debes hacer**:
- Confiar en el rol que aparece en `state["messages"]` (texto del usuario o del LLM).
- Pasar `_raw_token` al LLM como contexto. Solo viaja en `config`.
- Dejar `JWT_SECRET` con el default en producción.
- Quitar la validación de roles en el backend "porque el AI ya lo hace" — son capas independientes a propósito.

---

## 8. Variables de entorno

`.env` requerido (ver `.env.example`):

```
ANTHROPIC_API_KEY=sk-ant-...     # opcional si tienes OPENAI
OPENAI_API_KEY=sk-...            # fallback
NESTJS_API_URL=http://localhost:3001/api/v1
JWT_SECRET=<mismo que NestJS>    # ¡crítico que coincida!
ALLOWED_ORIGINS=http://localhost:3000
```

`JWT_SECRET` debe ser **idéntico** al del `hannahweb-backend/.env`. Si difieren, `jose.jwt.decode` lanza `JWTError` y el chat responde 401.

---

## 9. Ejecución y debugging

```bash
# Arranque
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Healthcheck
curl http://localhost:8000/health

# Probar el chat (necesitas un JWT del backend)
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"message":"cuántos proyectos tengo activos","session_id":"test"}'
```

`uvicorn.log` se llena con stdout. Para debug profundo del grafo:

```python
# en chat.py, después del astream_events
async for event in get_graph().astream_events(...):
    print(event["event"], event.get("name"), event.get("metadata", {}).get("langgraph_node"))
```

Activa todos los `event["event"]` para ver qué emite el grafo. Útiles:
- `on_chain_start` / `on_chain_end` (cada nodo)
- `on_tool_start` / `on_tool_end`
- `on_chat_model_start` / `on_chat_model_stream` / `on_chat_model_end`

---

## 10. Limitaciones conocidas y TODOs

1. **`InMemorySaver` se pierde al reiniciar uvicorn** — la conversación arranca de cero. Mover a `PostgresSaver` para prod.
2. **`DELETE /chat/history` es un stub** — no borra nada. Implementar `checkpointer.delete_thread(thread_id)`.
3. **No hay rate limiting** — un cliente puede agotar la cuota del LLM. Añadir `slowapi` o reverse-proxy con limits.
4. **No hay validación de expiración explícita en `jose.jwt.decode`** — confiamos en que el frontend renueve. Para HS256 con `exp` en el payload, `jose` ya valida `exp` por defecto, pero conviene loguear.
5. **`consultar_tareas_proyecto` aparecía en el system prompt original pero no existe** — ya se quitó. Si vuelves a referenciarla, créala primero.
6. **Streaming token-a-token está deshabilitado** (workaround de Python 3.10). Al actualizar a 3.11+, restaurar `on_chat_model_stream`.
7. **No hay logging estructurado** — todo va a stdout. Añadir `structlog` con request_id correlation.
8. **No hay tests** — al menos un test de smoke por cada tool más uno end-to-end del grafo con un LLM mock.

---

## 11. Recetas rápidas (problemas comunes)

### El LLM no llama mi tool
- Revisar el docstring de la tool: ¿describe claramente cuándo usarla? ¿menciona las palabras clave que el usuario diría?
- Mencionar la tool en el system prompt con un ejemplo de cuándo usarla.
- Probar con `temperature=0` para descartar varianza.

### La tool se llama pero la respuesta no llega al cliente
- Verificar que el SSE en `chat.py` esté emitiendo `on_chain_end` correctamente.
- Verificar `final_emitted` flag — puede estar bloqueando el segundo `on_chain_end`.
- Activar print de eventos (sección 9).

### El usuario reporta "no sé tu nombre"
- El JWT antiguo no incluía `nombre`. Pedir re-login.
- Verificar que `auth.service.ts` del backend esté firmando con `nombre` en el payload.

### Cambios al código no se aplican
- Uvicorn `--reload` solo detecta cambios en archivos `.py` dentro del watch dir. Si editas `requirements.txt`, reinicia manualmente.
- El singleton `_graph` se reconstruye al reload (proceso entero se reinicia).

### Error 401 en cada request
- `JWT_SECRET` no coincide entre AI y backend.
- El token expiró (default NestJS: 7 días).
- El header viene mal formado: debe ser `Authorization: Bearer <token>` exacto.

---

## 12. Referencias oficiales

- LangGraph docs: https://langchain-ai.github.io/langgraph/
- Conceptos de StateGraph: https://langchain-ai.github.io/langgraph/concepts/low_level/
- Tools en LangChain: https://python.langchain.com/docs/concepts/tools/
- `astream_events` v2: https://python.langchain.com/docs/how_to/streaming/#using-stream-events
- ToolNode + tools_condition: https://langchain-ai.github.io/langgraph/reference/prebuilt/
- Configuración de runtime (RunnableConfig): https://langchain-ai.github.io/langgraph/how-tos/configuration/
- Persistence / checkpointers: https://langchain-ai.github.io/langgraph/concepts/persistence/

Cuando dudes, lee la doc oficial en lugar de inventar — la API de LangGraph cambia rápido entre versiones menores.
