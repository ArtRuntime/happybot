import httpx
from http.cookies import SimpleCookie
from telegraph.aio import Telegraph

telegraph = Telegraph()
TELEGRAPH_TOKEN = None

async def get_telegraph_token():
    global TELEGRAPH_TOKEN
    if not TELEGRAPH_TOKEN:
        await telegraph.create_account(short_name="HappyBot")
        TELEGRAPH_TOKEN = telegraph.get_access_token()
    return TELEGRAPH_TOKEN

async def post_to_telegraph(title, text):
    token = await get_telegraph_token()
    # Telegraph lib handles token internally if set, but async wrapper might need setup
    # Actually telegraph.create_account sets the token in the instance
    
    try:
        response = await telegraph.create_page(
            title=title,
            html_content=text.replace("\n", "<br>"),
            author_name="HappyBot"
        )
        return response["url"]
    except Exception as e:
        return None

async def rentry(text):
    async with httpx.AsyncClient() as client:
        # Get cookies
        resp = await client.get("https://rentry.co")
        cookie = SimpleCookie()
        # httpx cookies are in resp.cookies
        
        # MissKaty logic manually parses cookies. httpx handles them in session (client)
        # But we need to extract csrftoken for payload
        
        csrftoken = resp.cookies.get("csrftoken")
        if not csrftoken:
             # Fallback if not found directly
             return None
             
        headers = {"Referer": "https://rentry.co"}
        payload = {"csrfmiddlewaretoken": csrftoken, "text": text}
        
        post_resp = await client.post(
            "https://rentry.co/api/new",
            data=payload,
            headers=headers
        )
        
        try:
             return post_resp.json().get("url")
        except:
             return None
