import httpx
from typing import Any

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


async def make_request(endpoint: str, method: str) -> dict[str, Any] | None:
    """Make a request to the NWS API with proper error handling."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"} #Posibilidad de añadir token

    url = f"{NWS_BASE}{endpoint}"
    
    async with httpx.AsyncClient() as client:
        try:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, timeout=TIMEOUT)
                response.raise_for_status()
            return response.json()
        except Exception:
            return None
        
        
async def get_alerts_API(state: str) -> str:
    endpoint = f"/alerts/active/area/{state}"
    data = await make_request(endpoint, "get")

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."

    if not data["features"]:
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)