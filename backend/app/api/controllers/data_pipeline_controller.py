import pandas as pd
import uuid
from fastapi import UploadFile, File, APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.db.db_session import get_db
from app.config.logging_config import get_logger

router = APIRouter(prefix="/api/data/v1", tags=["Data Pipeline"])
logger = get_logger(__name__)


# ------------------------------------------------------------
# Upload Spreadsheet
# ------------------------------------------------------------
@router.post("/upload-spreadsheet")
async def upload_spreadsheet(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    logger.info(f"Processing file: {file.filename}")

    try:
        # ----------------------------------------------------
        # Load file safely
        # ----------------------------------------------------
        df = pd.read_csv(file.file)

        if df.empty:
            raise HTTPException(400, "Uploaded file is empty.")

        # ----------------------------------------------------
        # Create safe table name
        # ----------------------------------------------------
        base = file.filename.replace(".csv", "").lower()
        table_name = f"{base}_{uuid.uuid4().hex[:8]}"

        # ----------------------------------------------------
        # Create table
        # ----------------------------------------------------
        create_table_query = build_create_table_query(df, table_name)
        db.execute(text(create_table_query))

        # ----------------------------------------------------
        # Insert data efficiently (bulk)
        # ----------------------------------------------------
        df.to_sql(
            table_name,
            db.bind,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=500
        )

        db.commit()

        logger.info(f"Successfully inserted {len(df)} rows into {table_name}")

        return {
            "message": "Successfully inserted data",
            "table_name": table_name,
            "rows_processed": len(df)
        }

    except pd.errors.ParserError:
        raise HTTPException(400, "Invalid CSV format.")

    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error: {str(e)}")
        raise HTTPException(500, "Database operation failed.")

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(500, f"Failed to process file: {str(e)}")


# ------------------------------------------------------------
# Helper — Build CREATE TABLE Query
# ------------------------------------------------------------
def build_create_table_query(df: pd.DataFrame, table_name: str) -> str:
    columns = []
    for col, dtype in df.dtypes.items():
        # Map Pandas dtype → PostgreSQL type
        if "int" in str(dtype):
            pg_type = "INTEGER"
        elif "float" in str(dtype):
            pg_type = "DOUBLE PRECISION"
        else:
            pg_type = "TEXT"

        safe_col = col.replace(" ", "_").replace("-", "_").lower()
        columns.append(f'"{safe_col}" {pg_type}')

    column_str = ", ".join(columns)
    return f'CREATE TABLE "{table_name}" ({column_str});'
