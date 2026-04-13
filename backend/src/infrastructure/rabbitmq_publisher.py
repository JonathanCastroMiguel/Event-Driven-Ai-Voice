"""RabbitMQ Consumer for receiving and processing events"""
 
import asyncio
import structlog
 
import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
 
from src.infrastructure.rabbitmq_events import BaseRabbitMQEvent
from src.config import settings
 
logger = structlog.get_logger(__name__)
 
class RabbitMQPublisher:
    """RabbitMQ publisher for sending events to a queue.
 
    Connects to RabbitMQ and publishes message events to a specified queue.
 
    Attributes:
        rabbitmq_url: AMQP connection URL
        queue_name: Name of queue to publish to
    """
    def __init__(
        self,
        rabbitmq_url: str,
        queue_name: str,
        exchange_name: str = "",
    ) -> None:
        """Initialize the publisher.
 
        Args:
            rabbitmq_url: AMQP connection string
            queue_name: Queue to publish to
            exchange_name: Exchange to publish to
        """
        self._rabbitmq_url = rabbitmq_url
        self._queue_name = queue_name
        self._exchange_name = exchange_name
        self._connection: AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._connected = False
 
    @property
    def is_connected(self) -> bool:
        """Check if connected to RabbitMQ.
 
        Returns:
            True if connection is active and not closed.
        """
        return self._connected and self._connection is not None and not self._connection.is_closed
    
    async def connect(self) -> None:
        """Establish connection to RabbitMQ.
 
        Uses aio-pika's RobustConnection for auto-reconnection.
        Connects to an existing queue (does not create it).
 
        Raises:
            ConnectionError: If connection fails
        """
        if self._connected:
            logger.warning(
                "rabbitmq_publisher_already_connected",
                extra={"queue": self._queue_name},
            )
            return
        
        logger.info(
            "rabbitmq_publisher_connecting",
            extra={"queue": self._queue_name, "exchange": self._exchange_name or "default"},
        )
 
        try:
            connection = await aio_pika.connect_robust(
                self._rabbitmq_url,
                timeout=settings.RABBITMQ_TIMEOUT_SECONDS,
            )
            self._connection = connection
 
            # Get channel for publishing
            channel = await connection.channel()
            self._channel = channel
 
            # Get the exchange to use for publishing
            if self._exchange_name:
                # Use named exchange (must already exist - passive=True)
                self._exchange = await channel.get_exchange(
                    self._exchange_name,
                    ensure=False,  # Don't create if it doesn't exist
                )
            else:
                # Use default exchange (empty string name)
                self._exchange = channel.default_exchange
 
            # Verify queue exists (passive=True to avoid creating it)
            await channel.declare_queue(
                self._queue_name,
                passive=True,
            )
 
            self._connected = True
 
            logger.info(
                "rabbitmq_publisher_connected",
                extra={
                    "queue": self._queue_name,
                    "exchange": self._exchange_name or "default",
                },
            )
 
        except Exception as e:
            logger.error(
                "rabbitmq_publisher_connection_failed",
                extra={
                    "queue": self._queue_name,
                    "exchange": self._exchange_name or "default",
                    "error": str(e),
                },
            )
            raise ConnectionError(f"Failed to connect to RabbitMQ: {e}") from e
        
    async def publish(self, event: BaseRabbitMQEvent) -> None:
        """Publish an event to the configured queue.
 
        Args:
            event: Event to publish (TODO)
 
        Raises:
            RuntimeError: If not connected
            Exception: If publish fails
        """
        if not self._connected or self._exchange is None:
            raise RuntimeError("Publisher not connected. Call connect() before publishing.")
 
        try:
            # Serialize event to JSON
            event_json = event.model_dump_json()
            message_body = event_json.encode()
 
            # Create message
            message = aio_pika.Message(
                body=message_body,
                content_type="application/json",
            )
 
            # Publish to the configured exchange with queue name as routing key
            await self._exchange.publish(
                message,
                routing_key=self._queue_name,
            )
 
            logger.info(
                "event_published",
                extra={
                    "queue": self._queue_name,
                    "exchange": self._exchange_name or "default",
                    "event_type": event.event_type
                },
            )
 
        except Exception as e:
            logger.error(
                "event_publish_failed",
                extra={
                    "queue": self._queue_name,
                    "exchange": self._exchange_name or "default",
                    "event_type": event.event_type,
                    "error": str(e),
                },
            )
            raise
 
    async def close(self) -> None:
        """Close the RabbitMQ connection gracefully.
 
        Safe to call multiple times.
        """
        if not self._connected:
            return
 
        logger.info(
            "rabbitmq_publisher_closing",
            extra={
                "queue": self._queue_name,
                "exchange": self._exchange_name or "default",
            },
        )
 
        try:
            if self._connection and not self._connection.is_closed:
                await self._connection.close()
 
            self._connected = False
            self._connection = None
            self._channel = None
            self._exchange = None
 
            logger.info(
                "rabbitmq_publisher_closed",
                extra={
                    "queue": self._queue_name,
                    "exchange": self._exchange_name or "default",
                },
            )
 
        except Exception as e:
            logger.error(
                "rabbitmq_publisher_close_failed",
                extra={
                    "queue": self._queue_name,
                    "exchange": self._exchange_name or "default",
                    "error": str(e),
                },
            )
            # Still mark as disconnected even if close fails
            self._connected = False
            self._connection = None
            self._channel = None
            self._exchange = None
 
    async def return_publisher(self) -> "RabbitMQPublisher":
        """Return the publisher instance.
 
        Useful for dependency injection in FastAPI routes.
 
        Returns:
            The RabbitMQPublisher instance
        """
        return self