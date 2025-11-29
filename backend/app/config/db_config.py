from typing import List, Dict, Any
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from langchain_openai import OpenAIEmbeddings
from app.config.logging_config import get_logger
from langchain_postgres.vectorstores import PGVector
from fastapi import HTTPException
# FIX: Updated import from langchain.schema to langchain_core.documents
from langchain_core.documents import Document
import pandas as pd
from app.config.env import (DATABASE_URL)
from typing import List, Optional

logger = get_logger(__name__)


class DB:
    def __init__(self, db_url: str):
        """
        Initialize the database connection.

        Args:
            db_url (str): Database URL
        """
        self.engine = create_engine(db_url)
        self.session = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine)
        self.inspector = inspect(self.engine)

    def execute_query(self, query: str) -> list:
        print("======== execute_query ========")
        with self.session() as session:
            result = session.execute(text(query))
            # return result
            if result.returns_rows:
                # Convert RowProxy to dict
                return [row for row in result.fetchall()]
            else:
                # For non-SELECT queries, commit the transaction and return an empty list
                session.commit()
                return []

    def create_session(self) -> Session:
        return self.session()

    def get_schemas(self, table_names: List[str]) -> List[Dict]:
        try:
            # Create an inspector object
            inspector = inspect(self.engine)

            # Initialize an array to hold the schema information for all tables
            schemas_info = []

            for table_name in table_names:
                schema_info = {
                    "table_name": table_name,
                    "schema": []
                }

                # Get the columns for the specified table
                columns = inspector.get_columns(table_name)
                # Collect column information
                for column in columns:
                    schema_info["schema"].append({
                        "name": column['name'],
                        "type": str(column['type']),
                        "nullable": column['nullable']
                    })

                # Append the schema information for the current table to the list
                schemas_info.append(schema_info)

            # Return the schema information for all tables
            return schemas_info

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return []  # Return an empty list in case of an error

    async def insert_dataframe(self, df: pd.DataFrame, table_name: str) -> Dict[str, Any]:
        """Insert pandas DataFrame into database"""
        try:
            with self.session() as session:
                df.to_sql(
                    name=table_name,
                    con=session.get_bind(),
                    if_exists='replace',
                    index=False
                )
                return {
                    "message": f"Successfully inserted data into table {table_name}",
                    "rows_processed": len(df)
                }
        except Exception as e:
            logger.error(f"Data insertion error: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Failed to insert data into database")


class VectorDB:
    def __init__(self):
        """Initialize VectorDB with connection string"""
        self.connection_string = DATABASE_URL
        self._embedding: Optional[OpenAIEmbeddings] = None

    def initialize_embedding(self, model_name: str = "text-embedding-3-large"):
        """
        Initialize the embedding model.
        """
        if self._embedding is None:
            self._embedding = OpenAIEmbeddings(model=model_name)
            return "Embedding model initialized successfully."
        return "Embedding model already initialized."

    @property
    def embedding(self):
        if self._embedding is None:
            raise ValueError(
                "Embedding model not initialized. Call initialize_embedding() first.")
        return self._embedding

    async def insert_data(self, documents: List[Document], collection_name: str) -> PGVector:
        """Insert documents into vector store"""
        try:
            return PGVector.from_documents(
                embedding=self.embedding,
                documents=documents,
                collection_name=collection_name,
                connection=self.connection_string,
            )
        except Exception as e:
            logger.error(f"Vector store insertion error: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Failed to insert documents into vector store")

    def get_vector_store(self, collection_name: str) -> PGVector:
        """Get existing vector store"""
        try:
            return PGVector(
                connection=self.connection_string,
                embeddings=self.embedding,
                collection_name=collection_name,
                pre_delete_collection=False
            )
        except Exception as e:
            logger.error(f"Vector store retrieval error: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Failed to retrieve vector store")