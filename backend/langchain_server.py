import os
from typing import Annotated
from typing_extensions import TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages  # ✅ correct place

load_dotenv()

class State(TypedDict):
    messages: Annotated[list, add_messages]

llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)

def chat(state: State):
    ai_msg = llm.invoke(state["messages"])
    return {"messages": [ai_msg]}

builder = StateGraph(State)
builder.add_node("chat", chat)
builder.set_entry_point("chat")
builder.add_edge("chat", END)

graph = builder.compile()  # ✅ export `graph`