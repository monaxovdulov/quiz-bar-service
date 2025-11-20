from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # Ollama
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    
    # Logic
    SEARCH_LIMIT: int = 10
    FETCH_TIMEOUT: int = 5
    
    class Config:
        env_file = ".env"

settings = Settings()