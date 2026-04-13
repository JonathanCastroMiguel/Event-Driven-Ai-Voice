"""RabbitMQ Consumer for receiving and processing events"""
 
import asyncio
import structlog
import json
 
import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
 
from src.config import settings
 
logger = structlog.get_logger(__name__)
 
 
class RabbitMQConsumer:
    """RabbitMQ consumer for processing text routing events.
 
    Connects to RabbitMQ and consumes messages from a queue.
 
    Attributes:
        rabbitmq_url: AMQP connection URL
        queue_name: Name of queue to consume from
        prefetch_count: Number of messages to prefetch
    """
    def __init__(
        self,
        rabbitmq_url: str,
        queue_name: str,
        prefetch_count: int = 10,
    ) -> None:
        """Initialize the consumer.
 
        Args:
            rabbitmq_url: AMQP connection string
            queue_name: Queue to consume from
            prefetch_count: Consumer prefetch count (default: 10)
        """
        self._rabbitmq_url = rabbitmq_url
        self._queue_name = queue_name
        self._prefetch_count = prefetch_count
        self._connection: AbstractRobustConnection | None = None
        self._consuming = False
        self._shutdown_event = asyncio.Event()
 
    @property
    def is_connected(self) -> bool:
        """Check if connected to RabbitMQ.
 
        Returns:
            True if connection is active and not closed.
        """
        return self._connection is not None and not self._connection.is_closed
    
    async def start(self) -> None:
        """Connect to RabbitMQ and begin consuming.
 
        Runs until stop() is called or connection fails permanently.
        """
        try:
            await self._connect()
        except Exception:
            logger.exception("rabbitmq_connection_failed", queue=self._queue_name)
            raise
 
        logger.info("rabbitmq_consumer_started", queue=self._queue_name)
 
        # Wait for shutdown signal
        await self._shutdown_event.wait()
 
    async def stop(self, timeout: float = settings.RABBITMQ_TIMEOUT_SECONDS) -> None:
        """Stop consuming and close connection.
 
        Args:
            timeout: Maximum seconds to wait for in-flight messages
        """
        logger.info("rabbitmq_consumer_stopping")
        self._consuming = False
        self._shutdown_event.set()
 
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("rabbitmq_connection_closed")
 
    async def _connect(self) -> None:
        """Establish robust connection to RabbitMQ.
 
        Uses aio-pika's RobustConnection for auto-reconnection.
        Connects to an existing queue (does not create it).
        """
        logger.info("rabbitmq_connecting", queue=self._queue_name)
 
        connection = await aio_pika.connect_robust(
            self._rabbitmq_url,
            timeout=settings.RABBITMQ_TIMEOUT_SECONDS,
        )
        self._connection = connection
 
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=self._prefetch_count)
 
        # Use passive=True to connect to existing queue without creating it
        queue = await channel.declare_queue(
            self._queue_name,
            passive=True,
        )
 
        self._consuming = True
        await queue.consume(self._on_message)
 
        logger.info("rabbitmq_connected", queue=self._queue_name)
 
    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        """Handle incoming RabbitMQ messages.
 
        Args:
            message: The incoming message to process
        """
        async with message.process():
            logger.info(
                "rabbitmq_message_received",
                extra={"queue": self._queue_name, "message_id": message.message_id},
            )
            try:
                body = json.loads(message.body.decode())
 
                logger.info(
                    "event processed",
                    extra={"queue": self._queue_name, "msg": body},
                )
        
                #TODO - process event
 
            except json.JSONDecodeError as e:
                logger.warning(
                    "message_rejected_invalid_json",
                )
                # Don't raise - acknowledge and skip invalid JSON
                return
 
            except Exception as e:
                logger.error(
                    "message_processing_failed",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
                # Don't raise - acknowledge to prevent infinite reprocessing
                return