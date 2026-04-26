"""Text-to-SQL GraphRAG — Core configuration."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OLLAMA = "ollama"
    OPENAI = "openai"
    GOOGLE = "google"


class SQLDialect(str, Enum):
    """Target SQL dialects for generation."""

    POSTGRES = "postgres"
    BIGQUERY = "bigquery"
    SNOWFLAKE = "snowflake"
    TRINO = "trino"
    MYSQL = "mysql"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "text2sql_dev"

    # --- LLM Provider ---
    llm_provider: LLMProvider = LLMProvider.OLLAMA

    # --- Ollama ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"

    # --- OpenAI ---
    openai_api_key: str | None = None
    openai_llm_model: str = "gpt-4o"
    openai_embed_model: str = "text-embedding-3-small"

    # --- Google ---
    google_api_key: str | None = None
    google_llm_model: str = "gemini-1.5-flash"
    google_embed_model: str = "models/text-embedding-004"

    # --- SQL ---
    sql_dialect: SQLDialect = SQLDialect.POSTGRES

    # --- Embedding ---
    embedding_dimensions: int = 768

    # --- dbt ---
    dbt_docs_path: Path = Path("./sample_dbt_docs")

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Logging ---
    log_level: str = "INFO"

    # --- Agent ---
    max_retry_attempts: int = 3
    retrieval_top_k: int = 5
    graph_expansion_hops: int = 2

    def get_llm(self):
        """Factory method to create the configured LLM instance."""
        if self.llm_provider == LLMProvider.OLLAMA:
            from langchain_ollama import ChatOllama

            return ChatOllama(
                base_url=self.ollama_base_url,
                model=self.ollama_llm_model,
                temperature=0,
            )
        elif self.llm_provider == LLMProvider.OPENAI:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                api_key=self.openai_api_key,
                model=self.openai_llm_model,
                temperature=0,
            )
        elif self.llm_provider == LLMProvider.GOOGLE:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                google_api_key=self.google_api_key,
                model=self.google_llm_model,
                temperature=0,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    def get_embeddings(self):
        """Factory method to create the configured embeddings instance."""
        if self.llm_provider == LLMProvider.OLLAMA:
            from langchain_ollama import OllamaEmbeddings

            return OllamaEmbeddings(
                base_url=self.ollama_base_url,
                model=self.ollama_embed_model,
            )
        elif self.llm_provider == LLMProvider.OPENAI:
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                api_key=self.openai_api_key,
                model=self.openai_embed_model,
            )
        elif self.llm_provider == LLMProvider.GOOGLE:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            return GoogleGenerativeAIEmbeddings(
                google_api_key=self.google_api_key,
                model=self.google_embed_model,
            )
        else:
            raise ValueError(f"Unsupported embedding provider: {self.llm_provider}")


# Singleton settings instance
settings = Settings()
