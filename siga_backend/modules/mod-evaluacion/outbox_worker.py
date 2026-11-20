import asyncio
import json
import logging
import os
from random import uniform
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import AsyncSessionLocal, OutboxEvent

from ..core.gateway.event_bus import event_bus

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")

logger = logging.getLogger(__name__)


async def outbox_worker():
    """Worker de outbox con conexión NATS controlada y reconexión automática."""

    nc = None
    connected = False
    last_reconnect_attempt = 0
    min_reconnect_wait = 2
    max_reconnect_wait = 30

    # Intento de conexión inicial
    try:
        nc = NATS()
        await nc.connect(NATS_URL, max_reconnect_attempts=0)
        connected = True
        logger.info(f"✅ Outbox Worker mod-evaluacion conectado a NATS: {NATS_URL}")
    except Exception as e:
        logger.error(f"❌ Outbox Worker mod-evaluacion error conectando a NATS: {e}")
        nc = None
        connected = False

    while True:
        try:
            # Verificar y mantener conexión NATS viva
            # Lógica: solo intentar reconectar si no estamos conectados
            if not connected:
                now = asyncio.get_event_loop().time()
                if now - last_reconnect_attempt > min_reconnect_wait + uniform(0, 2):
                    try:
                        nc = NATS()
                        await nc.connect(NATS_URL, max_reconnect_attempts=0)
                        connected = True
                        last_reconnect_attempt = now
                        logger.info("✅ Outbox Worker mod-evaluacion reconectado a NATS")
                    except Exception as e:
                        logger.warning(f"⚠️ Outbox Worker mod-evaluacion reconexión fallida: {e}")
                        min_reconnect_wait = min(max_reconnect_wait, min_reconnect_wait * 1.5)
            elif connected and nc:
                # Estamos conectados en papel, verifica que la conexión esté realmente viva
                try:
                    await nc.ping()  # Ping para verificar que la conexión está viva
                    # Ping exitoso: conexión viva, reinicia el temporizador
                    last_reconnect_attempt = asyncio.get_event_loop().time()
                except Exception:
                    # Ping falló: la conexión murió, necesita reconectar
                    connected = False
                    logger.warning("⚠️ Outbox Worker mod-evaluacion ping fallido, reconectando")
                    min_reconnect_wait = min(max_reconnect_wait, min_reconnect_wait * 1.5)

            # Procesar eventos no publicados
            async with AsyncSessionLocal() as db:
                try:
                    result = await db.execute(
                        select(OutboxEvent)
                        .where(OutboxEvent.published == False)
                        .order_by(OutboxEvent.created_at.asc())
                        .limit(50)
                    )
                    events = result.scalars().all()

                    published_count = 0
                    failed_count = 0

                    for event in events:
                        if connected and nc:
                            try:
                                payload_bytes = json.dumps(event.payload).encode()
                                await nc.publish(event.event_type, payload_bytes)
                                event.published = True
                                published_count += 1
                            except Exception as e:
                                logger.error(f"Error publicando evento {event.id}: {e}")
                                failed_count += 1
                        else:
                            logger.debug(f"🔄 Outbox Worker mod-evaluacion NATS desconectado - evento {event.id} quedará pendiente")
                            failed_count += 1

                    # Commit solo de los eventos que lograron publicarse
                    if published_count > 0:
                        await db.commit()
                    elif failed_count > 0 and published_count == 0:
                        await db.rollback()

                except Exception as e:
                    logger.error(f"Error en sesión DB del Outbox Worker mod-evaluacion: {e}")
                    try:
                        await db.rollback()
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Error crítico en Outbox Worker mod-evaluacion: {e}")
            try:
                async with AsyncSessionLocal() as db:
                    await db.rollback()
            except Exception:
                pass

        # Polling interval con variación aleatoria
        await asyncio.sleep(2 + uniform(0, 1))