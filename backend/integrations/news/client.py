
# Constants
from typing import Optional

from backend.core.base_api import BaseAPI
from backend.core.models import ToolResult
from datetime import date
from datetime import timedelta



from backend.config.settings import settings



class GuardianAPI(BaseAPI):


    BASE_URL  = "https://content.guardianapis.com/"
    
    API_KEY  = settings.guardian_api_key #Key ya validada
    API_KEY_PARAM = "api-key"
            
        
    #TODO: Make topic optional
    async def get_news_this_week_call(self, topic: str) -> ToolResult:
        today = date.today()
        new_date = today - timedelta(days=7)
        params = {"q": topic, 
                "from-date": new_date 
        }
                
        endpoint = f"search"
        response = await self.make_request(endpoint, "get", params)
        
        if not response.success or not response.has_content():
            return ToolResult.fail("No articles found")
        
        results = response.data.get("response", {}).get("results")
        
        articles = [
        {
            "title": article.get("webTitle"),
            "url": article.get("webUrl"),
            "date": article.get("webPublicationDate"),
        }
        for article in results
        ]

        return ToolResult.ok(articles)