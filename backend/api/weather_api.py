import httpx
from typing import Any

from backend.models import ToolResult

# Constants
NWS_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"
TIMEOUT=30

#Seguramente mover a un archivo de formatters en el futuro
def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]
    return f"""
Event: {props.get("event", "Unknown")}
Area: {props.get("areaDesc", "Unknown")}
Severity: {props.get("severity", "Unknown")}
Description: {props.get("description", "No description available")}
Instructions: {props.get("instruction", "No specific instructions provided")}
"""


async def make_request(endpoint: str, method: str) -> ToolResult:
    """Make a request to the NWS API with proper error handling."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"} #Posibilidad de añadir token

    url = f"{NWS_BASE}{endpoint}"
    
    async with httpx.AsyncClient() as client:
        try:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, timeout=TIMEOUT)
                response.raise_for_status()
                return ToolResult.ok(response.json())
            return ToolResult.fail(f"Unsupported HTTP method: {method}")
        except httpx.TimeoutException:
            return ToolResult.fail("Request timed out.")
        except httpx.HTTPStatusError as e:
            return ToolResult.fail(f"HTTP error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            return ToolResult.fail(f"An error occurred: {str(e)}")

async def get_alerts_API(state: str) -> ToolResult:
    endpoint = f"/alerts/active/area/{state}"
    response = await make_request(endpoint, "get")
    
    if not response.success:
        return ToolResult.fail(f"Error fetching alerts: {response.error}")

    if not response.data or not response.data.get("features"):
        return ToolResult.ok("No active alerts for this state.")

    alerts = [format_alert(feature) for feature in response.data["features"]]
    return ToolResult.ok("\n---\n".join(alerts))

async def get_zone_by_points(latitude: float, longitude: float) -> ToolResult:
    endpoint = f"/points/{latitude},{longitude}"
    points_json =  await make_request(endpoint, "get")
    
    if not points_json.success or not points_json.data:
        return ToolResult.fail("Unable to find requested zone")
    
    #Eliminamos la URL Base ya que el json contiene la URL completa y no solo el endpoint
    forecast = points_json.data.get("properties", {}).get("forecast")
    if not forecast:
        return ToolResult.fail("Forecast URL not found")
    points_url = forecast.replace(NWS_BASE, "")
    return ToolResult.ok(points_url)

async def get_forecast_API(zone: str) -> ToolResult:
    endpoint = zone
    forecast =  await make_request(endpoint, "get")
    
    if not forecast.success or not forecast.data:
            return ToolResult.fail("Unable to fetch detailed forecast.")
        
    return ToolResult.ok(forecast.data)
