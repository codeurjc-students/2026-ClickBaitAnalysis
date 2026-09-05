from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from backend.core.observability import log_tool_invocation
from backend.integrations.metadata import tool_meta
from backend.integrations.weather.client import WeatherAPI

# Estas dos tools se quedan devolviendo `str`, y NO es una carencia: producen
# prosa formateada para leer, no datos con estructura. Declararles un tipo
# estructurado obligaría a inventar campos que la salida no tiene.


def register(mcp: FastMCP):

    api = WeatherAPI()

    @mcp.tool(meta=tool_meta("Fuentes de contenido", __name__))
    @log_tool_invocation
    async def get_alerts(state: str) -> str:
        """Get weather alerts for a US state.

        Args:
            state: Two-letter US state code (e.g. CA, NY)

        Returns:
            The active alerts as formatted text, or a note saying there are none.

        Raises:
            If the weather API fails.
        """
        response = await api.get_alerts_API(state)
        if not response.has_content():
            raise ToolError(response.error or "Error fetching alerts")

        return response.unwrap()

    @mcp.tool(meta=tool_meta("Fuentes de contenido", __name__))
    @log_tool_invocation
    async def get_forecast(latitude: float, longitude: float) -> str:
        """Get weather forecast for a location.

        Args:
            latitude: Latitude of the location
            longitude: Longitude of the location

        Returns:
            The next five forecast periods as formatted text.

        Raises:
            If the location cannot be resolved or the weather API fails.
        """
        # First get the forecast grid endpoint
        zone_url = await api.get_zone_by_points(latitude, longitude)

        if not zone_url.has_content():
            raise ToolError(zone_url.error or "Unknown error while fetching zone")

        # Get the forecast URL from the points response
        response = await api.get_forecast_API(zone_url.unwrap())
        if not response.has_content():
            raise ToolError(response.error or "Unknown error while retrieving forecast")

        periods = response.unwrap().get("properties", {}).get("periods")
        if not periods:
            raise ToolError("No forecast periods available")

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
