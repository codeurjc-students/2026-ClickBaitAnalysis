


from mcp.server.fastmcp import FastMCP
from backend.integrations.weather.client import WeatherAPI



def register(mcp: FastMCP):
    
    api = WeatherAPI()
    
    
    @mcp.tool()
    async def get_alerts(state: str) -> str | dict:
        """Get weather alerts for a US state.

        Args:
            state: Two-letter US state code (e.g. CA, NY)
        """
        response = await api.get_alerts_API(state)
        if not response.has_content():
            return response.error or "Error fetching alerts"
        
        
        return response.data # type: ignore
        


    @mcp.tool()
    async def get_forecast(latitude: float, longitude: float) -> str:
        """Get weather forecast for a location.

        Args:
            latitude: Latitude of the location
            longitude: Longitude of the location
        """
        # First get the forecast grid endpoint
        zone_url = await api.get_zone_by_points(latitude, longitude)
        
        if not zone_url.has_content():
            return zone_url.error or "Unknown error while fetching zone"
            

        # Get the forecast URL from the points response
        response = await api.get_forecast_API(zone_url.data) # type: ignore
        if not response.has_content():
            return response.error or "Unknown error while retreiving forecast"
        
        
        periods = response.data.get("properties", {}).get("periods") # type: ignore
        forecasts = []
        for period in periods[:5]:  # Only show next 5 periods
            forecast = f"""
    {period["name"]}:
    Temperature: {period["temperature"]}°{period["temperatureUnit"]}
    Wind: {period["windSpeed"]} {period["windDirection"]}
    Forecast: {period["detailedForecast"]}
    """
            forecasts.append(forecast)
        

        return "\n---\n".join(forecasts)


