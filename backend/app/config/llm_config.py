from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from app.config.env import GROQ_API_KEY, OPENAI_API_KEY


class LLM:
    """
    Factory class for creating LLM clients using Groq or OpenAI.
    Ensures no deprecated or incompatible parameters are used.
    """

    def __init__(self):
        self.llm = None
        self.platform = None

    # ---------------------------
    #        GROQ MODELS
    # ---------------------------
    def groq(self, model: str):
        """
        Initialize Groq LLM using langchain-groq.

        Example models:
        - llama3-8b-8192
        - llama3-70b-8192
        - mixtral-8x7b
        """
        self.llm = ChatGroq(
            api_key=GROQ_API_KEY,
            model=model,
            temperature=0.3,
            max_tokens=2048
        )
        self.platform = "Groq"
        return self.llm

    # ---------------------------
    #        OPENAI MODELS
    # ---------------------------
    def openai(self, model: str):
        """
        Initialize OpenAI LLM using langchain-openai.

        Example models:
        - gpt-4o-mini
        - gpt-4o
        - gpt-4.1
        - gpt-3.5-turbo
        """
        self.llm = ChatOpenAI(
            api_key=OPENAI_API_KEY,
            model=model,
            temperature=0.3,
            max_tokens=2048
        )
        self.platform = "OpenAI"
        return self.llm

    # ---------------------------
    #          GETTER
    # ---------------------------
    def get_llm(self):
        """Return the active LLM instance."""
        return self.llm

    # ---------------------------
    #     DIRECT INVOKE HELPERS
    # ---------------------------
    def invoke(self, messages):
        """
        Wrapper to safely forward prompts to the language model.
        Accepts either a string or a list of messages.
        """
        if isinstance(messages, str):
            return self.llm.invoke([{"role": "user", "content": messages}])

        return self.llm.invoke(messages)
