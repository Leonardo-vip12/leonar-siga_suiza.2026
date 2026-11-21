from pydantic_settings import BaseSettings
from typing import List, Optional
from pydantic import Field

class CoreSettings(BaseSettings):
    """Configuración centralizada del Core con resiliencia"""
    
    # Core Identity
    app_name: str = "SIGA Core"
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    debug: bool = True
    
    # Database (Solo para Identity del Core)
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "dariana"
    DB_NAME: str = "siga_suiza_2026"
    DATABASE_URL: Optional[str] = None
    
    # Module Registry
    modules_auto_discover: bool = True
    modules_validate_on_start: bool = True
    modules_discovery_sources: List[str] = ["local", "database", "kubernetes"]
    
    # Communication
    http_proxy_timeout: int = 30
    
    # Security
    token_expire_minutes: int = 30
    module_token_expire_hours: = 24
    
    # NATS Event Bus
    enable_nats: bool = Field(default=True, description="Habilitar NATS Event Bus")
    nats_url: str = Field(default="nats://localhost:4222", description="URL de NATS")
    
    # 🔄 RESILIENCIA - Configuraciones nuevas
    # Cache distribuido
    cache_enabled: bool = Field(default=True, description="Habilitar cache distribuido")
    redis_url: Optional[str] = Field(default=None, description="URL completa de Redis (sobreescribe host/port)")
    redis_host: str = Field(default="localhost", description="Host de Redis")
    redis_port: int = Field(default=6379, description="Puerto de Redis")
    redis_password: Optional[str] = Field(default=None, description="Password de Redis")
    cache_default_ttl: int = Field(default=300, description="TTL por defecto en segundos")
    
    # Health Monitoring
    health_check_enabled: bool = Field(default=True, description="Habilitar monitoreo de salud")
    health_check_interval: int = Field(default=30, description="Intervalo de health checks en segundos")
    
    # Fallback System
    fallback_enabled: bool = Field(default=True, description="Habilitar sistema de fallback")
    
    # Circuit Breaker
    circuit_breaker_enabled: bool = Field(default=True, description="Habilitar circuit breaker")
    circuit_breaker_failure_threshold: int = Field(default=5, description="Umbral de fallos para abrir circuito")
    circuit_breaker_recovery_timeout: int = Field(default=60, description="Tiempo de recuperación en segundos")
    
    # CORS Configuration
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "https://leonar-sigasuiza2026.vercel.app",
        ],
        description="Lista de orígenes permitidos para CORS (separados por coma en variable de entorno)"
    )
    
    # 🔄 RESILIENCIA - Configuraciones nuevas (continua)
    # Health Monitoring
    health_check_enabled: bool = Field(default=True, description="Habilitar monitoreo de salud")
    health_check_interval: int = Field(default=30, description="Intervalo de health checks en segundos")
    
    # Fallback System
    fallback_enabled: bool = Field(default=True, description="Habilitar sistema de fallback")
    
    # Circuit Breaker
    circuit_breaker_enabled: bool = Field(default=True, description="Habilitar circuit breaker")
    circuit_breaker_failure_threshold: int = Field(default=5, description="Umbral de fallos para abrir circuito")
    circuit_breaker_recovery_timeout: int = Field(default=60, description="Tiempo de recuperación en segundos")
    
    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def database_sync_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql+asyncpg://"):
                url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return url
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def redis_url_effective(self) -> str:
        """Retorna la URL efectiva de Redis: redis_url si está definida, o construida desde host/port"""
        if self.redis_url:
            return self.redis_url
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Instancia global
settings = CoreSettings()

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pydantic import BaseModel
import logging
import os
import uuid

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="SIGA Core - Sistema Modular Ultraligero",
    debug=settings.debug,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS configurado usando orígenes explícitos desde variable de entorno
# CORS_ORIGINS: comma-separated list (ej: "http://localhost:5173,https://tu-app.vercel.app")
# Si está vacío, usa una lista segura que incluye dominios comunes de desarrollo
# y patrones para Vercel/Railway al desplegar
allowed_origins_str = os.getenv("CORS_ORIGINS", "")
if allowed_origins_str:
    allow_origins = [origin.strip() for origin in allowed_origins_str.split(",")]
else:
    # Por defecto: permite dominios de desarrollo comunes
    # Al desplegar en Vercel/Railway, establece CORS_ORIGINS en el panel de variables
    allow_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "https://leonar-sigasuiza2026.vercel.app",
        # Lo siguiente se sobreescribirá con CORS_ORIGINS en producción:
        # "https://tu-app.vercel.app",
        # "https://tu-app.up.railway.app"
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    # Ya no usamos regex para evitar problemas de matching;
    # en su lugar usamos origenes explícitos desde CORS_ORIGINS env var
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Authorization"],
)