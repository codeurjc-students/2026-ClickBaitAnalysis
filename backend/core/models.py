from typing import Any

# Usado para validación de campos.
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

    def has_content(self) -> bool:
        return self.success and self.data is not None

    def unwrap(self) -> Any:
        """El dato, o un fallo explícito si no lo hay.

        `data` es `Any | None` porque un resultado fallido no trae ninguno. El
        precio lo pagaba quien lo consume: las tools hacían `return
        response.data` declarando devolver una forma concreta, y los clientes
        `response.data["clave"]`. Las dos cosas están bien **si el resultado fue
        bien**, y ninguna lo comprobaba en el mismo sitio donde leía.

        Esto lo convierte en una condición explícita. Lo que cambia no es la
        seguridad de tipos —el dato sigue siendo `Any`— sino DÓNDE falla: antes
        un `None` inesperado daba un `TypeError` de subíndice tres marcos más
        abajo, o un modelo Pydantic quejándose de un campo que no existe. Ahora
        dice que el resultado venía vacío, y con el motivo del fallo original.

        Añadido en #139, al encender pyright: era la causa de diez de sus
        veintiséis avisos sobre código servido, todos la misma forma.
        """
        if not self.success or self.data is None:
            raise ValueError(self.error or "El resultado no trae datos.")
        return self.data
