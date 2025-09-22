from typing import List
from langchain_core.messages import BaseMessage, ToolMessage
from chains import revisor_chain, first_responder_chain
from execute_tools import execute_tools
from langgraph.graph import MessageGraph, END

graph = MessageGraph()
MAX_ITERATIONS = 1

graph.add_node("draft", first_responder_chain)
graph.add_node("execute_tools", execute_tools)
graph.add_node("revisor", revisor_chain)

graph.add_edge("draft", "execute_tools")
graph.add_edge("execute_tools", "revisor")

def event_loop(state: List[BaseMessage]) -> str:
    num_tool_calls = sum(isinstance(msg, ToolMessage) for msg in state)
    if num_tool_calls >= MAX_ITERATIONS:
        return END
    del state[:-2]
    return "execute_tools"

graph.add_conditional_edges("revisor", event_loop)
graph.set_entry_point("draft")

app = graph.compile()
