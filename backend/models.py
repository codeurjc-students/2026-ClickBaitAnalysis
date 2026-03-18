from typing import Any

#Usado para validación de campos.
from pydantic import BaseModel

class ToolResult(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None
    
    
    @classmethod
    def ok(cls, data: Any) -> "ToolResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error_message: str) -> "ToolResult":
        return cls(success=False, error=error_message)