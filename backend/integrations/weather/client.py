import httpx
from typing import Any

from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult





class WeatherAPI(BaseAPI):

    # Constants
    BASE_URL = "https://api.weather.gov"

    #Seguramente mover a un archivo de formatters en el futuro
    def format_alert(self, feature: dict) -> str:
        """Format an alert feature into a readable string."""
        props = feature["properties"]
        return f"""
    Event: {props.get("event", "Unknown")}
    Area: {props.get("areaDesc", "Unknown")}
    Severity: {props.get("severity", "Unknown")}
    Description: {props.get("description", "No description available")}
    Instructions: {props.get("instruction", "No specific instructions provided")}
    """


    

    async def get_alerts_API(self,state: str) -> ToolResult:
        endpoint = f"/alerts/active/area/{state}"
        response = await self.make_request(endpoint, "get")
        
        if not response.success:
            return ToolResult.fail(f"Error fetching alerts: {response.error}")

        if not response.data or not response.data.get("features"):
            return ToolResult.ok("No active alerts for this state.")

        alerts = [self.format_alert(feature) for feature in response.data["features"]]
        return ToolResult.ok("\n---\n".join(alerts))

    async def get_zone_by_points(self,latitude: float, longitude: float) -> ToolResult:
        endpoint = f"/points/{latitude},{longitude}"
        points_json =  await self.make_request(endpoint, "get")
        
        if not points_json.success or not points_json.has_content():
            return ToolResult.fail("Unable to find requested zone")
        
        #Eliminamos la URL Base ya que el json contiene la URL completa y no solo el endpoint
        forecast = points_json.data.get("properties", {}).get("forecast")
        if not forecast:
            return ToolResult.fail("Forecast URL not found")
        points_url = forecast.replace(f"{self.BASE_URL}/", "")
        return ToolResult.ok(points_url)

    async def get_forecast_API(self, zone: str) -> ToolResult:
        endpoint = zone
        forecast =  await self.make_request(endpoint, "get")
        
        if not forecast.success or not forecast.data:
                return ToolResult.fail("Unable to fetch detailed forecast.")
            
        return ToolResult.ok(forecast.data)
