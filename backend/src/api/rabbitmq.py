"""RabbitMQ dependency for FastAPI routes."""
 
from fastapi import HTTPException, Request, status
 
from src.infrastructure.rabbitmq_publisher import RabbitMQPublisher
 
 
def get_publisher(request: Request) -> RabbitMQPublisher:
    """Retrieve the RabbitMQ publisher from application state.
 
    Args:
        request: The incoming HTTP request
 
    Returns:
        The connected RabbitMQPublisher instance
 
    Raises:
        HTTPException: 503 if the publisher is not connected
    """
    publisher: RabbitMQPublisher = request.app.state.rabbitmq_publisher
    if not publisher.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RabbitMQ publisher not available",
        )
    return publisher