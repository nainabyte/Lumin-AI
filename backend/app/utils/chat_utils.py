# backend/app/utils/chat_utils.py
"""
Fully streaming, robust chat utilities.
- Uses the WorkflowManager to stream events back to client.
- Handles DB connection options (system_db or db_url).
- Provides safe saves to DB and error handling.
"""

import json
import logging
from typing import List, Optional, Iterator, Any, Dict

from fastapi.responses import StreamingResponse, JSONResponse
from fastapi import HTTPException

from app.config.logging_config import get_logger
from app.config.llm_config import LLM
from app.config.db_config import DB, VectorDB

# Use typed PromptTemplate from langchain_core if available, else fallback-to-dict
try:
    from langchain_core.prompts import PromptTemplate  # type: ignore
except Exception:
    PromptTemplate = None  # type: ignore

logger = get_logger(__name__)

llm_instance = LLM()
vectorDB_instance = VectorDB()


def _safe_jsonify(obj: Any) -> Any:
    """Serialize objects that might be non-JSON-native."""
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        try:
            return str(obj)
        except Exception:
            return {"unserializable": True}


def execute_workflow(
    question: str,
    conversation_id: int,
    table_list: List[str],
    llm_model: Optional[str] = "gemma2-9b-it",
    system_db: Optional[DB] = None,
    db_url: Optional[str] = None,
) -> StreamingResponse:
    """
    Returns a StreamingResponse (text/event-stream) that yields JSON lines.
    Each yielded line is a JSON object with shape: {"data": <event>}
    """

    # Resolve DB: prefer explicit system_db, else create one from db_url
    if system_db is not None:
        logger.info("Using existing DB Connection")
        db = system_db
    elif db_url:
        logger.info("Creating new DB connection from URL")
        db = DB(db_url)
    else:
        raise ValueError("Either system_db or db_url must be provided")

    # Initialize llm (wrap safely)
    try:
        llm = llm_instance.groq(llm_model)
    except Exception as e:
        logger.exception("Failed to initialize LLM: %s", e)
        # Return an immediate error stream to client
        def err_gen():
            yield json.dumps({"error": "Failed to initialize LLM", "detail": str(e)}) + "\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    schema = []
    try:
        schema = db.get_schemas(table_names=table_list)
    except Exception as e:
        logger.exception("Failed to fetch schema: %s", e)
        def err_gen():
            yield json.dumps({"error": "Failed to fetch schema", "detail": str(e)}) + "\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    workflow = None
    try:
        from app.langgraph.workflows.sql_workflow import WorkflowManager
        workflow = WorkflowManager(llm, db)
    except Exception as e:
        logger.exception("Failed to initialize WorkflowManager: %s", e)
        def err_gen():
            yield json.dumps({"error": "Workflow not available", "detail": str(e)}) + "\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    app = workflow.create_workflow().compile()

    def event_stream() -> Iterator[str]:
        all_responses = []
        try:
            stream_fn = getattr(app, "stream", None)
            if stream_fn is None:
                # Fallback: try .run or return minimal response
                run_fn = getattr(app, "run", None)
                if callable(run_fn):
                    out = run_fn({"question": question, "schema": schema})
                    yield json.dumps({"data": out}) + "\n"
                    all_responses.append(out)
                else:
                    yield json.dumps({"data": {"message": "stream not available"}}) + "\n"
                    all_responses.append({"message": "stream not available"})
            else:
                for event in stream_fn({"question": question, "schema": schema}):
                    # Make sure event is JSON serializable
                    safe_event = _safe_jsonify(event)
                    all_responses.append(safe_event)
                    yield json.dumps({"data": safe_event}) + "\n"

            # After streaming, try to persist the aggregated answer as one message
            try:
                if system_db:
                    # Use existing db session helpers to save message
                    from app.api.controllers.data_pipeline_controller import save_message as _save_msg  # only if defined there
                    # If that save_message isn't present, fall back to models usage
                    try:
                        _save_msg(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=json.dumps({"answer": all_responses}),
                            db=system_db
                        )
                    except Exception:
                        # fallback: attempt to import chat_utils' internal save or write minimal row
                        from app.api.db.models import Messages
                        with system_db.session() as session:
                            m = Messages(
                                conversation_id=conversation_id,
                                role="assistant",
                                content=json.dumps({"answer": all_responses}),
                            )
                            session.add(m)
                            session.commit()
                else:
                    logger.debug("No system_db provided; skipping saving of assistant message.")
            except Exception as e:
                logger.exception("Failed to save assistant message: %s", e)
                yield json.dumps({"error": "Failed to save message", "detail": str(e)}) + "\n"

        except Exception as e:
            logger.exception("Error during streaming: %s", e)
            yield json.dumps({"error": str(e)}) + "\n"
        finally:
            # close stream if available
            try:
                close_fn = getattr(app, "stream", None)
                if close_fn and hasattr(close_fn, "close"):
                    close_fn.close()  # type: ignore
            except Exception:
                # non-fatal
                logger.debug("Stream close raised exception (ignored).")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def execute_document_chat(question: str, embedding_model: str, table_name: str):
    """
    Short helper to run document retrieval QA using VectorDB and LLM.
    Returns JSONResponse or raises HTTPException on error.
    """
    try:
        vectorDB_instance.initialize_embedding(embedding_model)
        vector_store = vectorDB_instance.get_vector_store(table_name)
        llm = llm_instance.groq("gemma2-9b-it")

        # Build simple prompt dynamically if PromptTemplate available
        if PromptTemplate:
            template = "You are Lumin... Context: {context}\nQuestion: {question}\nAnswer:"
            PROMPT = PromptTemplate(template=template, input_variables=["context", "question"])
        else:
            PROMPT = None

        # Use a minimal retrieval + llm invocation if langchain API pieces missing
        try:
            from langchain.chains import RetrievalQA
            if PROMPT:
                qa = RetrievalQA.from_chain_type(
                    llm=llm,
                    chain_type="stuff",
                    retriever=vector_store.as_retriever(search_kwargs={"k": 2}),
                    return_source_documents=True,
                    chain_type_kwargs={"prompt": PROMPT},
                )
            else:
                qa = RetrievalQA.from_chain_type(
                    llm=llm,
                    chain_type="stuff",
                    retriever=vector_store.as_retriever(search_kwargs={"k": 2}),
                    return_source_documents=True,
                )

            res = qa({"query": question})
            docs = res.get("source_documents", [])
            serialized_docs = [{"page_content": d.page_content, "metadata": getattr(d, "metadata", {})} for d in docs]
            return JSONResponse(status_code=200, content={"answer": res.get("result"), "source_documents": serialized_docs})
        except Exception as e:
            logger.exception("LangChain RetrievalQA failed: %s", e)
            # fallback: run naive vector store search if available
            try:
                hits = vector_store.similarity_search(question, k=2)
                serialized_docs = [{"page_content": getattr(h, "page_content", ""), "metadata": getattr(h, "metadata", {})} for h in hits]
                # Try to ask llm directly for an answer based on concatenated context
                context = "\n\n".join([d["page_content"] for d in serialized_docs])
                prompt = f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
                answer = llm.invoke(prompt) if hasattr(llm, "invoke") else str(prompt)
                return JSONResponse(status_code=200, content={"answer": str(answer), "source_documents": serialized_docs})
            except Exception as ex2:
                logger.exception("Fallback document chat failed: %s", ex2)
                raise HTTPException(status_code=500, detail=str(ex2))

    except Exception as e:
        logger.exception("execute_document_chat top-level error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
