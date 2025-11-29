# backend/app/langgraph/workflows/sql_workflow.py
"""
Crash-proof SQL workflow wrapper.
- Keeps the same public API surface used by your code:
    WorkflowManager(llm, db) -> .create_workflow(), .run_sql_agent(...)
- Defensive imports: if langgraph or related libs are missing, workflow will still behave gracefully.
"""

from typing import List, Any, Dict, Optional
import logging
import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)

# Defensive imports for langgraph / langchain_core
try:
    from langchain_core.language_models import BaseLLM
except Exception:
    # Provide a minimal stub type for typing only
    class BaseLLM:  # type: ignore
        pass

try:
    from langgraph.graph import START, END, StateGraph
except Exception:
    # Provide a minimal fallback StateGraph implementation so imports won't crash.
    START, END = "START", "END"

    class StateGraph:
        def __init__(self, input=None, output=None):
            self._nodes = {}
            self._edges = []

        def add_node(self, name, func):
            self._nodes[name] = func

        def add_edge(self, a, b):
            self._edges.append((a, b))

        def add_conditional_edges(self, node, fn):
            # minimal placeholder; real branching isn't available, but won't crash
            self._edges.append((node, node))

        def compile(self):
            # Return a dummy object with stream method compatible with usage
            class App:
                def stream(self, state):
                    # Minimal generator: yield the initial state once
                    yield {"result": state}
            return App()

# Import DB type if available for typing clarity
try:
    from app.config.db_config import DB
except Exception:
    class DB:  # type: ignore
        def execute_query(self, q: str):
            raise RuntimeError("DB not available")

# Import SQL agent if available, else provide a light stub
try:
    from app.langgraph.agents.sql_agent import SQLAgent
except Exception:
    class SQLAgent:
        def __init__(self, llm):
            self.llm = llm

        def get_parse_question(self, state):
            # naive parse
            parsed = {"is_relevant": True, "parsed": {"text": state.get("question")}}
            return {"parsed_question": parsed}

        def generate_sql_query(self, state):
            return {"sql_query": "NOT_RELEVANT"}

        def validate_and_fix_sql(self, state):
            return {"sql_valid": True, "sql_issues": ""}

        def format_results(self, state):
            return {"results": state.get("query_result", [])}

        def choose_visualization(self, state):
            return {"recommended_visualization": "table", "visualization_reason": ""}

        def format_visualization_data(self, state):
            return {"formatted_data_for_visualization": {}}

        def conversational_response(self, state):
            return {"answer": "I can't help with that right now."}


class WorkflowManager:
    """
    Workflow manager for SQL-based Q/A with defensive programming:
    - Serializes SQLAlchemy rows to JSON-safe types
    - Runs queries through provided DB abstraction
    """

    def __init__(self, llm: Optional[BaseLLM], db: DB):
        self.llm = llm
        self.db = db
        self.sql_agent = SQLAgent(llm)

    # ---------- serialization helpers ----------
    def serialize_value(self, value):
        if value is None:
            return None
        if isinstance(value, datetime.datetime):
            return value.isoformat()
        if isinstance(value, datetime.date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except Exception:
                return str(value)
        # RowProxy / ORM object handling is delegated to serialize_row
        return value

    def serialize_row(self, row):
        try:
            # SQLAlchemy Row / RowMapping
            if hasattr(row, "_asdict"):
                return {k: self.serialize_value(v) for k, v in row._asdict().items()}
            # ORM instance -> try __dict__
            if hasattr(row, "__dict__"):
                return {k: self.serialize_value(v) for k, v in row.__dict__.items() if not k.startswith("_")}
            # tuple/list
            if isinstance(row, (list, tuple)):
                return [self.serialize_value(v) for v in row]
            return self.serialize_value(row)
        except Exception as e:
            logger.debug("serialize_row error: %s", e)
            return str(row)

    # ---------- core execution ----------
    def run_sql_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes SQL from state['sql_query'] using self.db.
        Returns a dict with 'query_result' (list).
        Non-fatal: catches exceptions and returns an 'error' key instead of raising.
        """
        try:
            query = state.get("sql_query", "")
            if not query or query.strip().upper() == "NOT_RELEVANT":
                return {"query_result": []}

            # Clean up query (minimal sanitization)
            cleaned = query.replace("`", " ").replace("\n", " ").strip()
            # Execute using DB abstraction
            result = self.db.execute_query(cleaned)
            # Convert to JSON-serializable forms
            serialized = [self.serialize_row(r) for r in (result or [])]
            return {"query_result": serialized}
        except Exception as exc:
            logger.exception("Error executing SQL query: %s", exc)
            return {"query_result": [], "error": str(exc)}

    # ---------- workflow builder ----------
    def create_workflow(self):
        workflow = StateGraph(input=None, output=None)

        # Add nodes - use SQLAgent methods but protect against missing attributes
        add_node = getattr(workflow, "add_node", lambda *a, **k: None)
        add_edge = getattr(workflow, "add_edge", lambda *a, **k: None)
        add_conditional_edges = getattr(workflow, "add_conditional_edges", lambda *a, **k: None)

        add_node("parse_question", getattr(self.sql_agent, "get_parse_question", lambda s: {}))
        add_node("generate_sql", getattr(self.sql_agent, "generate_sql_query", lambda s: {}))
        add_node("validate_and_fix_sql", getattr(self.sql_agent, "validate_and_fix_sql", lambda s: {}))
        add_node("execute_sql", self.run_sql_query)
        add_node("format_results", getattr(self.sql_agent, "format_results", lambda s: {}))
        add_node("choose_visualization", getattr(self.sql_agent, "choose_visualization", lambda s: {}))
        add_node("format_data_for_visualization", getattr(self.sql_agent, "format_visualization_data", lambda s: {}))
        add_node("conversational_response", getattr(self.sql_agent, "conversational_response", lambda s: {}))

        add_edge(START, "parse_question")
        add_conditional_edges("parse_question", getattr(self, "should_continue", lambda s: "generate_sql"))
        add_edge("generate_sql", "validate_and_fix_sql")
        add_edge("validate_and_fix_sql", "execute_sql")
        add_edge("execute_sql", "format_results")
        add_edge("execute_sql", "choose_visualization")
        add_edge("choose_visualization", "format_data_for_visualization")
        add_edge("format_data_for_visualization", END)
        add_edge("format_results", END)
        add_edge("conversational_response", END)

        return workflow

    def should_continue(self, state: Dict[str, Any]) -> str:
        parsed = state.get("parsed_question", {})
        if not parsed:
            return "conversational_response"
        if not parsed.get("is_relevant", True):
            return "conversational_response"
        return "generate_sql"

    def returnGraph(self):
        return self.create_workflow().compile()

    def run_sql_agent(self, question: str, schema: List[Dict]) -> dict:
        """
        Run the compiled workflow and collect streamed events.
        This method will not raise if langgraph internals are missing -
        it will instead return a dict with 'error' key or best-effort results.
        """
        try:
            app = self.create_workflow().compile()
            results = []
            # app.stream(...) may not exist in fallback - guard for it
            stream_fn = getattr(app, "stream", None)
            if stream_fn is None:
                # fallback: call stream-like sync generator if available
                if hasattr(app, "run"):
                    out = app.run({"question": question, "schema": schema})
                    return {"result": out}
                return {"result": {"message": "stream not available"}}
            for event in stream_fn({"question": question, "schema": schema}):
                # event is expected to be dict-like; collect safely
                try:
                    if isinstance(event, dict):
                        results.append(event)
                    else:
                        results.append({"value": str(event)})
                except Exception:
                    results.append({"value": "unserializable_event"})
            return {"result": results}
        except Exception as e:
            logger.exception("run_sql_agent failure: %s", e)
            return {"error": str(e)}
