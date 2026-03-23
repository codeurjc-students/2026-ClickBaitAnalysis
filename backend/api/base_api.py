


import httpx

from backend.models import ToolResult


class BaseAPI:
    BASE_URL: str = ""
    API_KEY: str | None = None
    TIMEOUT: float = 30.0
    API_KEY_PARAM: str = "api-key"
    


    async def make_request(
    self,
    endpoint: str,
    method: str,
    params : dict | None = None
    ) -> ToolResult:
        """Make a request to the  API with proper error handling."""
        
        # Quizás tambíen sea condicional
        headers = {"Accept": "application/json"}

        key_param = {self.API_KEY_PARAM: self.API_KEY} if self.API_KEY else {}
        params = key_param | (params or {})
            
        url = f"{self.BASE_URL}{endpoint}"
        
        async with httpx.AsyncClient() as client:
            try:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=params, timeout=self.TIMEOUT)
                    response.raise_for_status()
                    return ToolResult.ok(response.json())
                return ToolResult.fail(f"Unsupported HTTP method: {method}")
            except httpx.TimeoutException:
                return ToolResult.fail("Request timed out.")
            except httpx.HTTPStatusError as e:
                return ToolResult.fail(f"HTTP error: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                return ToolResult.fail(f"An error occurred: {str(e)}")