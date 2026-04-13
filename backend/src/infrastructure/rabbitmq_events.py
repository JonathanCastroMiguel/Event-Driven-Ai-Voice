"""RabbitMQ event models"""
 
from pydantic import BaseModel
 
 
class BaseRabbitMQEvent(BaseModel):
    """Base model for RabbitMQ events.
 
    All events published to or consumed from RabbitMQ should inherit from this base model.
    """
    event_type: str
 
 
class RawRabbitMQEvent(BaseRabbitMQEvent):
    """Temporary event model for unstructured payloads.
 
    Used until domain-specific event types are defined.
    """
    payload: dict
 