# llama_langgraph_react_agent.py

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from langchain.agents import create_react_agent, AgentExecutor
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableLambda
from langchain_core.agents import AgentFinish

# OPTIONAL: Use this if you have a local LLaMA model via LlamaCpp
from langchain_community.llms import LlamaCpp

# 1. Define Tool and Input Schema
class WeatherInput(BaseModel):
    city: str = Field(description="The city to get weather for")

def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny with 25°C."  # Mocked result

weather_tool = StructuredTool.from_function(
    func=get_weather,
    name="get_weather",
    description="Returns the current weather for a given city.",
    args_schema=WeatherInput,
    return_direct=True,
)

# 2. Load LLaMA Model (adjust path and params as needed)
llm = LlamaCpp(
    model_path="your_model_path/llama-2-7b-chat.gguf",  # 🧠 Replace with your model path
    temperature=0.7,
    max_tokens=512,
    n_ctx=2048,
    verbose=True,
)

# 3. Create Agent Executor with ReAct Style
tools = [weather_tool]
agent = create_react_agent(llm=llm, tools=tools)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# 4. Define State Type
class AgentState(dict):
    pass

# 5. Define Agent Step Node
def run_agent(state: AgentState) -> AgentState:
    input_text = state.get("input", "")
    result = executor.invoke({"input": input_text})
    return {"input": input_text, "output": result}

# 6. Wrap Step Node as Runnable
agent_node = RunnableLambda(run_agent)

# 7. Build Graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.set_entry_point("agent")
workflow.set_finish_point("agent")  # One-shot for simplicity

app = workflow.compile()

# 8. Run It
if __name__ == "__main__":
    query = "What's the weather in Toronto?"
    result = app.invoke({"input": query})
    print("Result:", result["output"])
