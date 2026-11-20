import asyncio
import json
import logging
from random import uniform
from typing import Callable, Dict, List, Optional
from nats.aio.client import Client as NATS
from nats.errors import TimeoutError, NoServersError

from ..config import settings
from .event_schemas import BaseEvent, EventFactory

logger = logging.getLogger(__name__)


class NATSEventBus:
    """Bus de eventos usando NATS para comunicación entre microservicios"""

    def __init__(self):
        self.nc = NATS()
        self.connected = False
        self.subscriptions: Dict[str, List[Callable]] = {}
        self._connect_attempts = 0
        self._max_connect_attempts = 10
        self._last_connect_attempt = 0

        # Callbacks para eventos de conexión
        self._disconnected_callbacks: List[Callable] = []
        self._reconnected_callbacks: List[Callable] = []
        self._closed_callbacks: List[Callable] = []

    def on_disconnect(self, callback: Callable):
        """Registra un callback que se ejecuta al desconectar"""
        self._disconnected_callbacks.append(callback)

    def on_reconnect(self, callback: Callable):
        """Registra un callback que se ejecuta al reconectar"""
        self._reconnected_callbacks.append(callback)

    def on_close(self, callback: Callable):
        """Registra un callback que se ejecuta al cerrar la conexión"""
        self._closed_callbacks.append(callback)

    async def connect(self) -> bool:
        """Conecta al servidor NATS con reconexión controlada"""
        if self.connected:
            return True

        self._connect_attempts += 1
        self._last_connect_attempt = asyncio.get_event_loop().time()

        # Limitar intentos de conexión para evitar bucles infinitos
        if self._connect_attempts > self._max_connect_attempts:
            logger.error("❌ Máximo de intentos de conexión NATS alcanzado (" + str(self._max_connect_attempts) + ")")
            return False

        try:
            # Configuración robusta de conexión NATS
            # NOTA: nats-py usa ping_interval y max_outstanding_pings, no reconnect_wait
            connect_kwargs = {
                "servers": [settings.nats_url],
                # max_reconnect_attempts=0 desactiva la reconexión automática del cliente
                # para controlarlo nosotros con logging estructurado
                "ping_interval": 30,        # Enviar ping cada 30 segundos
                "max_outstanding_pings": 128,  # Max 128 pings sin respuesta antes de considerar caída
            }

            await asyncio.wait_for(
                self.nc.connect(**connect_kwargs),
                timeout=10
            )

            self.connected = True
            self._connect_attempts = 0  # Reset counter on successful connection
            logger.info("✅ NATS Event Bus conectado")

            # Ejecutar callbacks de reconectar
            for callback in self._reconnected_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception as e:
                    logger.warning("Error en callback de reconexión: " + str(e))

            return True

        except (NoServersError, asyncio.TimeoutError) as e:
            logger.error("❌ No se pudo conectar a NATS - Verifica que el servidor esté ejecutándose: " + str(e))
            self.connected = False
            # Ejecutar callbacks de desconexión
            for callback in self._disconnected_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception:
                    pass
            return False

        except Exception as e:
            logger.error("❌ Error conectando a NATS: " + str(e))
            self.connected = False
            for callback in self._disconnected_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception:
                    pass
            return False

    async def disconnect(self):
        """Cierra la conexión NATS de manera ordenada"""
        if self.connected:
            self.connected = False
            try:
                await self.nc.close()
            except Exception as e:
                logger.error("Error cerrando conexión NATS: " + str(e))

            # Ejecutar callbacks de cierre
            for callback in self._closed_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception:
                    pass

            logger.info("🔌 NATS Event Bus desconectado")

    async def publish(self, event: BaseEvent) -> bool:
        """Publica un evento en el bus con verificación de conexión"""
        if not self.connected:
            # Intentar reconexión rápida
            if not await self.connect():
                logger.warning("⚠️ Event Bus no conectado - Evento no publicado")
                return False

        try:
            # Publicar en el subject correspondiente al tipo de evento
            subject = "events." + event.event_type.value
            message = event.model_dump_json()

            # Publicar en NATS
            await self.nc.publish(subject, message.encode())

            logger.debug("📨 Evento publicado: " + event.event_type + " -> " + subject)
            return True

        except Exception as e:
            logger.error("❌ Error publicando evento: " + str(e))
            self.connected = False  # Marcar como desconectado ante error de publicación
            return False

    async def publish_raw(self, subject: str, data: Dict) -> bool:
        """Publica datos crudos en un subject específico"""
        if not self.connected:
            if not await self.connect():
                return False

        try:
            message = json.dumps(data).encode()
            await self.nc.publish(subject, message)
            return True
        except Exception as e:
            logger.error("❌ Error en publish_raw: " + str(e))
            self.connected = False
            return False

    async def subscribe(self, event_type: str, callback: Callable) -> bool:
        """Suscribe una función callback a un tipo de evento"""
        if not self.connected:
            if not await self.connect():
                logger.warning("⚠️ Event Bus no conectado - No se puede suscribir")
                return False

        try:
            subject = "events." + event_type

            # Registrar callback localmente
            if event_type not in self.subscriptions:
                self.subscriptions[event_type] = []
            self.subscriptions[event_type].append(callback)

            # Suscribirse en NATS con handler de mensajes
            await self.nc.subscribe(subject, cb=self._create_message_handler(event_type, callback))
            logger.debug("📥 Suscrito a eventos: " + event_type)
            return True

        except Exception as e:
            logger.error("❌ Error suscribiéndose a " + event_type + ": " + str(e))
            return False

    def _create_message_handler(self, event_type: str, callback: Callable):
        """Crea manejador de mensajes para NATS con reconstrucción de eventos"""
        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                # Intentar reconstruir el evento usando BaseEvent o clase específica si fuera necesario
                # Por ahora usamos BaseEvent ya que es la base de todos
                event = BaseEvent(**data)

                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error("❌ Error procesando mensaje en " + event_type + ": " + str(e))

        return message_handler

    async def request(self, subject: str, data: Dict, timeout: float = 5.0) -> Optional[Dict]:
        """Envía una solicitud y espera respuesta (patrón request-reply)"""
        if not self.connected:
            return None

        try:
            message = json.dumps(data).encode()
            response = await self.nc.request(subject, message, timeout=timeout)
            return json.loads(response.data.decode())
        except TimeoutError:
            logger.warning("⏰ Timeout en request: " + subject)
            return None
        except Exception as e:
            logger.error("❌ Error en request " + subject + ": " + str(e))
            self.connected = False
            return None

    def _trigger_disconnected(self):
        """Dispara callbacks de desconexión interna"""
        for callback in self._disconnected_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback())
                else:
                    callback()
            except Exception as e:
                logger.warning("Error ejecutando callback desconexión: " + str(e))

    def _trigger_reconnected(self):
        """Dispara callbacks de reconexión interna"""
        self.connected = True
        self._connect_attempts = 0
        for callback in self._reconnected_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback())
                else:
                    callback()
            except Exception as e:
                logger.warning("Error ejecutando callback reconexión: " + str(e))

    def _trigger_closed(self):
        """Dispara callbacks de cierre interna"""
        self.connected = False
        for callback in self._closed_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback())
                else:
                    callback()
            except Exception as e:
                logger.warning("Error ejecutando callback cierre: " + str(e))


# Instancia global del Event Bus
event_bus = NATSEventBus()