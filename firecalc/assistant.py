"""LangGraph-backed explanations with tools for the calculator's saved data."""

from __future__ import annotations

import json
import operator
from typing import Annotated, Any, TypedDict


class ChatState(TypedDict):
    history: list[dict[str, str]]
    question: str
    context: str
    answer: str
    messages: Annotated[list[Any], operator.add]


SYSTEM_PROMPT = """You are a careful explainer for an India-focused FIRE planning calculator. Explain calculations and help users explore assumptions. Treat supplied values as user-entered planning estimates, not verified facts. Do not provide individualized investment, legal, or tax advice. Do not invent current Indian tax rules or return/inflation forecasts. Ground analysis in supplied values and use the context tools when comparing sections or when details are needed. Explain uncertainty plainly and never claim you changed an app input."""


def build_assistant_graph(
    provider: str,
    model_name: str,
    api_key: str,
    tool_context: dict[str, Any] | None = None,
    base_url: str | None = None,
):
    """Build a LangGraph agent that can retrieve saved spending, FIRE, and goal data."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from langchain_core.tools import tool
    from langgraph.graph import END, START, StateGraph
    from langgraph.prebuilt import ToolNode, tools_condition

    if provider == "Gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.2,
            request_timeout=45,
            retries=1,
        )
    elif provider == "OpenRouter":
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0.2,
            timeout=45,
            max_retries=1,
        )
    elif provider == "OpenCode":
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url or "https://opencode.ai/inference/openai/v1",
            temperature=0.2,
            timeout=45,
            max_retries=1,
        )
    else:
        raise ValueError("Choose Gemini or OpenRouter")

    data = tool_context or {}

    @tool
    def get_spending_context() -> str:
        """Retrieve saved expense categories, amounts, frequencies, and inflation assumptions."""
        return json.dumps(data.get("spending", {}), ensure_ascii=False, default=str)

    @tool
    def get_investment_context() -> str:
        """Retrieve FIRE assumptions, portfolio projections, corpus coverage, and SWP results."""
        return json.dumps(data.get("investments", {}), ensure_ascii=False, default=str)

    @tool
    def get_goals_context() -> str:
        """Retrieve saved goals, their inflation-adjusted future costs, and savings estimates."""
        return json.dumps(data.get("goals", {}), ensure_ascii=False, default=str)

    tools = [get_spending_context, get_investment_context, get_goals_context]
    agent_model = model.bind_tools(tools)

    def prepare(state: ChatState) -> dict[str, list[Any]]:
        try:
            payload = json.loads(state["context"] or "{}")
            section_prompt = payload.get("section_prompt_template", "")
        except (TypeError, json.JSONDecodeError):
            section_prompt = ""
        system_prompt = SYSTEM_PROMPT
        if section_prompt:
            system_prompt += f"\n\nSection-specific guidance: {section_prompt}"
        messages = [SystemMessage(content=system_prompt)]
        for item in state["history"][-12:]:
            if item["role"] == "assistant":
                messages.append(AIMessage(content=item["content"]))
            elif item["role"] == "user":
                messages.append(HumanMessage(content=item["content"]))
        context = state["context"] or "No calculator summary was shared for this turn."
        messages.append(HumanMessage(content=f"Calculator context:\n{context}\n\nUser question:\n{state['question']}"))
        return {"messages": messages}

    def call_model(state: ChatState) -> dict[str, Any]:
        response = agent_model.invoke(state["messages"])
        content_text = ""
        if isinstance(response.content, str):
            content_text = response.content
        elif isinstance(response.content, list):
            content_text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in response.content)
        answer = content_text if not getattr(response, "tool_calls", None) else state.get("answer", "")
        return {"messages": [response], "answer": answer}

    graph = StateGraph(ChatState)
    graph.add_node("prepare", prepare)
    graph.add_node("assistant", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "assistant")
    graph.add_conditional_edges("assistant", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "assistant")
    return graph.compile()
