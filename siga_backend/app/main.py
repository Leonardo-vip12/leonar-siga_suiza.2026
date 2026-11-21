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
    module_token_expire_hours: int = 24
    
    # NATS Event Bus
    enable_nats: bool = Field(default=True, description="Habilitar NATS Event Bus")
    nats_url: str = Field(default="nats://localhost:4222", description="URL de NATS")
    
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
import uuid
import os

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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Authorization"],
)

# Rutas del core
@app.on_event("startup")
async def startup():
    # Inicializar descubrimiento de módulos
    await module_runtime.discover_modules()
    logger.info("SIGA Core started - module discovery initiated")
    logger.info(f"Modules registered: {len(module_runtime.modules)}")
    for name, mod in module_runtime.modules.items():
        logger.info(f"  - {name}: {mod.status.value}")

# Include routers from core registry
app.include_router(module_runtime.router)

# ===== Authentication Routes =====

from fastapi import HTTPException
from pydantic import BaseModel
from typing import Literal

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/auth/login")
async def login(login_data: LoginRequest):
    """Iniciar sesión con email y contraseña"""
    from ..core.identity.auth_service import AuthService
    from ..core.identity.database import AsyncSessionLocal
    
    async with AsyncSessionLocal() as db:
        auth_service = AuthService(db)
        user = await auth_service.authenticate_user(login_data.email, login_data.password)
    
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    # Generate JWT token
    from ..core.identity.tokens import token_service
    from datetime import timedelta
    
    access_token = token_service.create_user_token(
        user_id=str(user["id"]),
        email=user["email"],
        permissions=user.get("permissions", []),
        role=user.get("role", "estudiante")
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "siga-core",
        "modules_registered": len(module_runtime.modules),
        "healthy_modules": len([m for m in module_runtime.modules.values() if m.status.value == "HEALTHY"])
    }

# OpenAPI customization
@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_func():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# ===== Module Proxy Route =====

@app.api_route("/api/{module_name}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def module_proxy(module_name: str, path: str, request: Request):
    """Proxy inteligente para los siete módulos"""
    from ..core.registry.runtime import module_runtime
    from ..core.gateway.http_proxy import http_gateway
    
    # Verify module exists
    module = module_runtime.get_module(module_name)
    if not module:
        raise HTTPException(status_code=404, detail=f"Módulo '{module_name}' no encontrado")
    
    # Execute proxy
    response = await http_gateway.proxy_to_module(request, module_name, path)
    
    # Add informative headers
    response.headers["X-Module-Name"] = module_name
    response.headers["X-Module-Status"] = module.status.value
    
    return response