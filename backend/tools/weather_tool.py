


from mcp.server.fastmcp import FastMCP
from api.weather_api import get_alerts_API, get_forecast_API, get_zone_by_points
from backend.models import ToolResult



def register(mcp: FastMCP):
    @mcp.tool()
    async def get_alerts(state: str) -> ToolResult:
        """Get weather alerts for a US state.

        Args:
            state: Two-letter US state code (e.g. CA, NY)
        """
        response = await get_alerts_API(state)
        return response
        


    @mcp.tool()
    async def get_forecast(latitude: float, longitude: float) -> str:
        """Get weather forecast for a location.

        Args:
            latitude: Latitude of the location
            longitude: Longitude of the location
        """
        # First get the forecast grid endpoint
        zone_url = get_zone_by_points(latitude, longitude)

        if not zone_url:
            return "Unable to fetch forecast data for this location."

        # Get the forecast URL from the points response
        response = await get_forecast_API(zone_url)
        
        
        periods = response["properties"]["periods"]
        forecasts = []
        for period in periods[:5]:  # Only show next 5 periods
            forecast = f"""
    {period["name"]}:
    Temperature: {period["temperature"]}°{period["temperatureUnit"]}
    Wind: {period["windSpeed"]} {period["windDirection"]}
    Forecast: {period["detailedForecast"]}
    """
            forecasts.append(forecast)
        

        return response


