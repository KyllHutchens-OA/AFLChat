"""
Resume Chat Agent - Simple chatbot for resume Q&A

A streamlined 2-node LangGraph workflow: RETRIEVE → RESPOND
Single LLM call for fast responses.
"""
from typing import Dict, Any, List, TypedDict, Callable, Optional
from langgraph.graph import StateGraph, END
from openai import OpenAI
import os
import logging
from dotenv import load_dotenv
from app.resume.data import RESUME_DATA, get_resume_context

load_dotenv()
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class ResumeState(TypedDict, total=False):
    """State for the resume chat agent."""
    user_query: str
    conversation_id: str
    context: str
    natural_language_response: str
    confidence: float
    socketio_emit: Optional[Callable]
    conversation_history: List[Dict[str, Any]]
    errors: List[str]


class ResumeAgent:
    """
    Simple agent for resume Q&A.

    Workflow:
    1. RETRIEVE - Load full resume context (fast, in-memory)
    2. RESPOND - Generate natural language response (single LLM call)
    """

    def __init__(self):
        self.graph = self._build_graph()

    @staticmethod
    def _emit_progress(state: ResumeState, step: str, message: str):
        """Emit WebSocket progress update."""
        if state.get("socketio_emit"):
            try:
                state["socketio_emit"]('resume_thinking', {
                    'step': message,
                    'current_step': step
                })
            except Exception as e:
                logger.warning(f"Failed to emit progress: {e}")

    def _build_graph(self) -> StateGraph:
        """Build streamlined 2-node LangGraph workflow: RETRIEVE → RESPOND."""
        workflow = StateGraph(ResumeState)

        workflow.add_node("retrieve", self.retrieve_node)
        workflow.add_node("respond", self.respond_node)

        workflow.add_edge("retrieve", "respond")
        workflow.add_edge("respond", END)

        workflow.set_entry_point("retrieve")

        return workflow.compile()

    async def run(
        self,
        user_query: str,
        conversation_id: str = None,
        socketio_emit: Callable = None,
        conversation_history: List[Dict[str, Any]] = None
    ) -> ResumeState:
        """Run the resume agent workflow."""
        initial_state = ResumeState(
            user_query=user_query,
            conversation_id=conversation_id,
            context="",
            errors=[],
            socketio_emit=socketio_emit,
            conversation_history=conversation_history or []
        )

        final_state = await self.graph.ainvoke(initial_state)
        return final_state

    async def retrieve_node(self, state: ResumeState) -> ResumeState:
        """
        RETRIEVE: Get full resume context (small dataset, no need for selective retrieval).
        """
        self._emit_progress(state, "retrieve", "Loading resume...")
        logger.info("RETRIEVE: Getting full resume context")

        try:
            # With a small static dataset, just include everything
            state["context"] = get_resume_context()
            logger.info("Retrieved full resume context")

        except Exception as e:
            logger.error(f"Error in RETRIEVE: {e}")
            state["context"] = f"Name: {RESUME_DATA['name']}\nTitle: {RESUME_DATA['title']}"
            state["errors"].append(str(e))

        return state

    async def respond_node(self, state: ResumeState) -> ResumeState:
        """
        RESPOND: Generate natural language response.
        """
        self._emit_progress(state, "respond", "Generating response...")
        logger.info("RESPOND: Generating answer")

        try:
            # Build conversation context for continuity
            conversation_context = ""
            history = state.get("conversation_history", [])

            if history and len(history) > 0:
                recent = history[-4:]  # Last 2 exchanges
                conversation_context = "\n## Previous Conversation\n"
                for msg in recent:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")[:200]
                    if role == "user":
                        conversation_context += f"User: {content}\n"
                    elif role == "assistant":
                        conversation_context += f"Assistant: {content}\n"
                conversation_context += "\n"

            # Generate response
            prompt = f"""You are {RESUME_DATA['name']}. Answer briefly.

STRICT RULES:
1. ONE sentence only. No exceptions.
2. Pick ONE fact to share, not a summary of everything.
3. NEVER repeat anything from the previous conversation below - if you already said it, share something different or say "I mentioned that already - anything else you'd like to know?"
4. Only use facts from the resume. Never assume.

{conversation_context}

## Resume
{state['context']}

## Question
{state['user_query']}

One sentence answer:"""

            response = client.responses.create(
                model="gpt-5-nano",
                input=[
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}]
                    }
                ]
            )

            state["natural_language_response"] = response.output_text.strip()
            state["confidence"] = 0.9

            self._emit_progress(state, "respond", "Response ready!")
            logger.info("Response generated successfully")

        except Exception as e:
            logger.error(f"Error in RESPOND: {e}")
            state["natural_language_response"] = (
                "I apologize, but I encountered an issue generating a response. "
                "Please try rephrasing your question."
            )
            state["confidence"] = 0.0
            state["errors"].append(str(e))

        return state


# Global agent instance
resume_agent = ResumeAgent()
