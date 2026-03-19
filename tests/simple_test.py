import asyncio
from backend.api.the_guardian_api import get_news_this_week_call

async def test():
    result = await get_news_this_week_call("technology")
    print(result)

asyncio.run(test())