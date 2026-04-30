"""
Ensambla el StateGraph de Hannah AI.
Arquitectura: llm_call ↔ tools_node (loop ReAct)
"""
from langgraph.graph import StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver
from .state import HannahState
from .nodes import get_llm, make_llm_node
from ..tools.proyectos import consultar_proyectos
from ..tools.tickets import consultar_tickets, crear_ticket
from ..tools.reuniones import consultar_reuniones
from ..tools.miembros import consultar_miembros_proyecto

# Lista de tools disponibles para el agente
TOOLS = [consultar_proyectos, consultar_tickets, crear_ticket, consultar_reuniones, consultar_miembros_proyecto]

# Checkpointer en memoria (dev). En prod: PostgresSaver
checkpointer = InMemorySaver()


def build_graph():
    """
    Construye y compila el StateGraph del agente.
    Se llama una sola vez al arrancar la app (singleton).
    """
    llm_with_tools = get_llm(TOOLS)
    llm_node = make_llm_node(llm_with_tools)

    builder = StateGraph(HannahState)

    # Nodos
    builder.add_node("llm_call", llm_node)
    builder.add_node("tools", ToolNode(TOOLS))

    # Edges
    builder.add_edge(START, "llm_call")
    # tools_condition: si el LLM hizo tool_calls → "tools", sino → END
    builder.add_conditional_edges("llm_call", tools_condition)
    # Después de ejecutar tools, vuelve al LLM
    builder.add_edge("tools", "llm_call")

    return builder.compile(checkpointer=checkpointer)


# Instancia global del grafo — se compila lazily en el primer request
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# Alias para importar directamente (compatibilidad)
graph = None  # se inicializa en lifespan de FastAPI
