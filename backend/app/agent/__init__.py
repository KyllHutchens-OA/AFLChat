"""AFL Analytics Agent module."""

__all__ = ["agent"]


def __getattr__(name):
    # Lazy so importing app.agent.v3 (or the llm helper from background jobs)
    # does not pull in the LangGraph v2 pipeline.
    if name == "agent":
        from app.agent.graph import agent
        return agent
    raise AttributeError(name)
