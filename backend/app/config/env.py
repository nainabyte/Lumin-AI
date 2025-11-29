# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Now you can access the variables
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Set huggingface token
# Fix: Added 'or ""' to prevent crash if HF_TOKEN is missing
os.environ["HF_TOKEN"] = os.getenv("HF_TOKEN") or ""

# Set Langsmith traces
# Fix: Added 'or ""' here as well for safety
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT") or ""

# Enable tracing
os.environ["LANGCHAIN_TRACING_V2"] = "false"