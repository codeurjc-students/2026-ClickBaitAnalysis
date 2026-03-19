
# Constants
from typing import Optional

import httpx

from backend.models import ToolResult
from datetime import date
from datetime import timedelta



GUARDIAN_URL = "https://content.guardianapis.com/"
GUARDIAN_API_KEY = "bd23a1f1-6f0a-4bc8-a757-a68a996c3d4b"
TIMEOUT=30


async def make_request(
    endpoint: str,
    method: str,
    params : dict | None = None
    ) -> ToolResult:
    """Make a request to the  API with proper error handling."""
    headers = {"Accept": "application/json"}

    params = {"api-key": GUARDIAN_API_KEY} | (params or {})
        
    url = f"{GUARDIAN_URL}{endpoint}"
    
    async with httpx.AsyncClient() as client:
        try:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=params, timeout=TIMEOUT)
                response.raise_for_status()
                return ToolResult.ok(response.json())
            return ToolResult.fail(f"Unsupported HTTP method: {method}")
        except httpx.TimeoutException:
            return ToolResult.fail("Request timed out.")
        except httpx.HTTPStatusError as e:
            return ToolResult.fail(f"HTTP error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            return ToolResult.fail(f"An error occurred: {str(e)}")
        
    
#TODO: Make topic optional
async def get_news_this_week_call(topic: str) -> ToolResult:
    today = date.today()
    new_date = today - timedelta(days=7)
    params = {"q": topic, 
              "from-date": new_date 
    }
              
    endpoint = f"search"
    response = await make_request(endpoint, "get", params)
    
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