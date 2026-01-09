import asyncio
import os
import socket
import sys
import dns.resolver
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess
import threading
import time

# --- DNS & Connection Checks ---

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    pass

app = FastAPI(lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return """
    <html>
        <head><title>Bot Status</title></head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
            <h1>Bot Running</h1>
            <p>Status: Active</p>
        </body>
    </html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
