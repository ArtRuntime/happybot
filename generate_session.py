import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client

load_dotenv()

async def main():
    print("--- Pyrogram Session String Generator ---")
    
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")

    if not api_id or not api_hash:
        print("API_ID or API_HASH not found in .env.")
        try:
            api_id = int(input("Enter API_ID: "))
            api_hash = input("Enter API_HASH: ")
        except ValueError:
            print("Invalid API_ID. Exiting.")
            return
    else:
        print(f"Found API_ID found in .env: {api_id}")

    print("\nStarting client to generate session...")
    print("You will be asked to enter your phone number and the OTP code sent to your Telegram.")
    
    try:
        app = Client(
            "temp_session_gen",
            api_id=int(api_id),
            api_hash=api_hash,
            in_memory=True
        )
        
        await app.start()
        session_string = await app.export_session_string()
        await app.stop()

        print("\n" + "="*50)
        print("GENERATED SESSION STRING (Copy this to your .env variable SESSION1, SESSION2, etc.):")
        print("\n" + session_string + "\n")
        print("="*50)
        
    except Exception as e:
        print(f"\nError generating session: {e}")

if __name__ == "__main__":
    asyncio.run(main())
