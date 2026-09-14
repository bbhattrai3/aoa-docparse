from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    openai_api_key: str = ""  # Used for utility bill extraction only
    auth0_domain: str = ""
    auth0_api_audience: str = ""
    auth0_algorithms: str = "RS256"
    allowed_origins: str = "http://localhost:5173"  # Vite dev server

    class Config:
        env_file = ".env"

settings = Settings()