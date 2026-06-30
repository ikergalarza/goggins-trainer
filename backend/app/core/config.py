from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    ANTHROPIC_API_KEY: str = ""
    STRAVA_CLIENT_ID: str = ""
    STRAVA_CLIENT_SECRET: str = ""
    STRAVA_REDIRECT_URI: str = "https://goggins-trainer-production.up.railway.app/api/strava/callback"

    # Auth / JWT. En producción (Railway) define JWT_SECRET como variable de entorno.
    JWT_SECRET: str = "dev-insecure-secret-change-me"
    JWT_EXPIRE_DAYS: int = 30
    # Maestro a sembrar al arrancar. La contraseña NUNCA va en el código:
    # se define como variable de entorno MASTER_PASSWORD (p.ej. en Railway).
    MASTER_EMAIL: str = "ikergalarza1999@gmail.com"
    MASTER_PASSWORD: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
