"""
News API for The Guardian
"""



import json

from mcp.server.fastmcp import FastMCP
from backend.api.the_guardian_api import get_news_this_week_call
from backend.models import ToolResult


#TODO: Implementar validador? Acaso hay campos cerrados
#TODO: Esta tool podría inferir! (Preguntar que temas quiere)
def register(mcp: FastMCP):
    @mcp.tool()
    async def get_news_this_week(topic: str) -> str:
        
        """Get latest news.

        Args:
            topic: the topic to search for
        """
        response = await get_news_this_week_call(topic)
        return json.dumps(response.data)
        
        