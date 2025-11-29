from pypdf import PdfReader
from langchain_text_splitters import CharacterTextSplitter
# FIX: Updated import from langchain.schema to langchain_core.documents
from langchain_core.documents import Document
from io import BytesIO
from typing import List


text_splitter = CharacterTextSplitter(
    separator="\n",
    chunk_size=750,
    chunk_overlap=50,
    length_function=len,
)


def pdf_to_document(buffer: BytesIO, file_name: str) -> List[Document]:
    pdf_reader = PdfReader(buffer)
    raw_text = "".join(page.extract_text() or "" for page in pdf_reader.pages)
    texts = text_splitter.split_text(raw_text)
    return [Document(page_content=text, metadata={"source": file_name}) for text in texts]


def text_to_document(buffer: BytesIO, file_name: str) -> List[Document]:
    # Read the content of the BytesIO object
    text_content = buffer.getvalue().decode('utf-8')

    # Split the text into chunks
    texts = text_splitter.split_text(text_content)

    # Create Document objects
    return [Document(page_content=text, metadata={"source": file_name}) for text in texts]