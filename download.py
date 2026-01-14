import requests
import json
import re
import sys
import os
import http.cookiejar

def get_video_id(url):
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def load_cookies(filename="cookies.txt"):
    """Loads Netscape format cookies from a file."""
    if not os.path.exists(filename):
        print(f"⚠️ Warning: '{filename}' not found. Script will run without login.")
        return None

    try:
        # MozillaCookieJar is standard for cookies.txt files
        jar = http.cookiejar.MozillaCookieJar(filename)
        jar.load(ignore_discard=True, ignore_expires=True)
        print(f"✅ Cookies loaded successfully from {filename}")
        return jar
    except Exception as e:
        print(f"❌ Error loading cookies: {e}")
        return None

def download_video(video_id):
    # 0. Load Cookies
    cookies = load_cookies()

    # 1. Get the Stream Data
    url = "https://www.youtube.com/youtubei/v1/player"
    payload = {
        "videoId": video_id,
        "context": {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "19.29.35",
                "androidSdkVersion": 30,
                "userAgent": "com.google.android.youtube/19.29.35 (Linux; U; Android 11) gzip",
                "hl": "en",
                "gl": "US",
                "utcOffsetMinutes": 0
            }
        }
    }

    print("Fetching video details...")
    # PASS COOKIES HERE -> To get permission to see the video
    res = requests.post(url, json=payload, cookies=cookies)
    data = res.json()

    if 'streamingData' not in data:
        # Debugging info if it fails
        if 'playabilityStatus' in data:
            print(f"❌ Error Status: {data['playabilityStatus'].get('status')}")
            print(f"   Reason: {data['playabilityStatus'].get('reason')}")
        else:
            print("❌ Error: Could not get streaming data.")
        return

    # 2. Find the Best Progressive Stream (Video + Audio combined)
    formats = data['streamingData'].get('formats', [])
    stream_url = None

    # We prefer itag 18 (360p) because it is reliable and always has audio
    for fmt in formats:
        if fmt.get('itag') == 18:
            stream_url = fmt['url']
            break

    # Fallback to any available format if itag 18 is missing
    if not stream_url and formats:
        stream_url = formats[0]['url']

    if not stream_url:
        print("❌ No direct download link found (only adaptive streams available).")
        return

    title = data.get('videoDetails', {}).get('title', 'video')
    filename = f"{re.sub(r'[\\/*?:\"<>|]', '', title)}.mp4"

    # 3. Download the Content
    print(f"✅ Found stream! Downloading '{filename}'...")

    try:
        # PASS COOKIES HERE -> To get permission to download the file
        with requests.get(stream_url, stream=True, cookies=cookies) as r:
            if r.status_code == 403:
                print("❌ Error 403: Forbidden. YouTube rejected the download.")
                print("   Try adding headers to the request or checking your cookies.")
                return

            r.raise_for_status()
            total_length = int(r.headers.get('content-length', 0))
            downloaded = 0

            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_length > 0:
                            done = int(50 * downloaded / total_length)
                            sys.stdout.write(f"\r[{'=' * done}{' ' * (50-done)}] {downloaded//1024//1024}MB")
                            sys.stdout.flush()

        print(f"\n\n🎉 Download Complete: Saved as {filename}")

    except Exception as e:
        print(f"\n❌ Download Error: {e}")

# --- Run ---
video_url = input("Enter YouTube video URL: ")
vid_id = get_video_id(video_url)

if vid_id:
    download_video(vid_id)
else:
    print("Invalid URL")
