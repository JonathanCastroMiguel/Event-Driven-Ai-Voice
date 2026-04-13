"""Publish events to RabbitMQ endpoint."""
 
import structlog
 
from fastapi import APIRouter, Depends, status
 
from src.api.rabbitmq import get_publisher
from src.api.schemas.rabbitmq_publish import RabbitMQPublishRequest, RabbitMQPublishResponse
from src.infrastructure.rabbitmq_events import RawRabbitMQEvent
from src.infrastructure.rabbitmq_publisher import RabbitMQPublisher
 
logger = structlog.get_logger(__name__)
 
router = APIRouter(prefix="/v1/rabbitmq", tags=["rabbitmq"])
 
 
@router.post(
        "/publish",
        status_code=status.HTTP_200_OK,
        response_model=RabbitMQPublishResponse
        )
async def publish_event(
    request: RabbitMQPublishRequest,
    publisher: RabbitMQPublisher = Depends(get_publisher),
) -> RabbitMQPublishResponse:
    """Endpoint to publish events to RabbitMQ."""
 
    logger.info("Publishing event to RabbitMQ", event_type=request.event_type, payload=request.payload)
 
    event = RawRabbitMQEvent(event_type=request.event_type, payload=request.payload)
    await publisher.publish(event)
 
    return RabbitMQPublishResponse(status="success", event_type=request.event_type)