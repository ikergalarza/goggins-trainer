from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    ANTHROPIC_API_KEY: str = ""
    STRAVA_CLIENT_ID: str = ""
    STRAVA_CLIENT_SECRET: str = ""
    STRAVA_REDIRECT_URI: str = "https://goggins-trainer-production.up.railway.app/api/strava/callback"
    # Base del frontend a la que vuelve el callback de Strava. Si no se define,
    # se deriva del redirect_uri (mismo origen que sirve el SPA en Railway).
    FRONTEND_URL: str = ""

    @property
    def frontend_base(self) -> str:
        if self.FRONTEND_URL:
            return self.FRONTEND_URL.rstrip("/")
        # https://host/api/strava/callback -> https://host
        return self.STRAVA_REDIRECT_URI.split("/api/strava/callback")[0].rstrip("/")

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
