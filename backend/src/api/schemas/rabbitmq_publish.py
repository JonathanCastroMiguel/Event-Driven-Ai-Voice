"""Schemas for RabbitMQ publish endpoint."""
 
from typing import Literal
from pydantic import BaseModel
 
class RabbitMQPublishRequest(BaseModel):
    """Request model for RabbitMQ publish endpoint."""
 
    event_type: str
    payload: dict
 
class RabbitMQPublishResponse(BaseModel):
    """Response model for RabbitMQ publish endpoint."""
 
    status: Literal["success", "failure"]
    event_type: str