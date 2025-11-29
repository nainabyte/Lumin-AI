from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.api.schemas.chat_schema import ChatRequest
from app.utils.chat_utils import execute_workflow
from app.api.db.db_session import get_db
from app.api.db.chat_history import Conversations, Messages
from app.config.logging_config import get_logger
from sqlalchemy.orm import Session

logger = get_logger(__name__)

chat_router = APIRouter(prefix="/api/chat/v1", tags=["Chat"])


# ------------------------------------------------------------
# Initialize Conversation
# ------------------------------------------------------------
@chat_router.post("/initiate-conversations")
def initiate_conversation(db: Session = Depends(get_db)):
    try:
        new_conv = Conversations(title="New Conversation")
        db.add(new_conv)
        db.commit()
        db.refresh(new_conv)

        return {"conversation_id": new_conv.id}

    except SQLAlchemyError as e:
        logger.error(f"DB error while creating conversation: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create conversation."
        )


# ------------------------------------------------------------
# Ask Question
# ------------------------------------------------------------
@chat_router.post("/ask-question")
def ask_question(request: ChatRequest, db: Session = Depends(get_db)):
    """
    Handles Q&A over SQL data using LangGraph workflow.
    """

    logger.info("CHAT REQUEST RECEIVED")

    try:
        # Validate required fields
        if not request.conversation_id:
            raise HTTPException(
                status_code=400,
                detail="Conversation ID is required."
            )

        if not request.table_list:
            raise HTTPException(
                status_code=400,
                detail="table_list cannot be empty."
            )

        # Save user message
        save_user_message(db, request.conversation_id, request.question)

        # Execute backend workflow (LangGraph)
        stream = execute_workflow(
            question=request.question,
            conversation_id=request.conversation_id,
            table_list=request.table_list,
            llm_model=request.model,
            system_db=db
        )

        return stream

    except ValueError as e:
        logger.error(f"ValueError: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail="Database operation failed.")

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(e)}"
        )


# ------------------------------------------------------------
# Helper — Save User Message
# ------------------------------------------------------------
def save_user_message(db: Session, conversation_id: int, content: str):
    try:
        message = Messages(
            conversation_id=conversation_id,
            role="user",
            content=content
        )
        db.add(message)
        db.commit()
    except SQLAlchemyError as e:
        logger.error(f"Failed to save user message: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save message.")
