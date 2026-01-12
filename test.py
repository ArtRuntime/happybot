import requests
import re
import json

def extract_yt_initial_data(video_url):
    headers = {
        'User-Agent': 'Mozilla/5.0'
    }

    res = requests.get(video_url, headers=headers)
    if res.status_code != 200:
        print("Failed to fetch page.")
        return None

    html = res.text

    # Extract the ytInitialPlayerResponse JSON
    initial_data_pattern = r'var ytInitialPlayerResponse = ({.*?});'
    match = re.search(initial_data_pattern, html)

    if not match:
        print("Could not extract ytInitialPlayerResponse.")
        return None

    yt_initial_data = json.loads(match.group(1))
    return yt_initial_data

def extract_video_streams(yt_initial_data):
    try:
        streaming_data = yt_initial_data['streamingData']
        formats = streaming_data.get('formats', [])
        adaptive_formats = streaming_data.get('adaptiveFormats', [])

        print("\n--- Available Formats ---\n")
        for fmt in formats + adaptive_formats:
            if 'url' in fmt:
                print(f"Quality: {fmt.get('qualityLabel', 'audio')}")
                print(f"MIME Type: {fmt['mimeType']}")
                print(f"URL: {fmt['url']}")
                print('-' * 60)
            elif 'signatureCipher' in fmt:
                print(f"⚠️ Encrypted URL (requires deciphering):")
                print(f"Quality: {fmt.get('qualityLabel', 'audio')}")
                print(f"Signature Cipher: {fmt['signatureCipher'][:100]}...")
                print('-' * 60)
    except KeyError:
        print("Could not find streamingData in the initial data.")

# 👇 Replace with any YouTube video URL
video_url = input("Enter YouTube video URL: ")
yt_data = extract_yt_initial_data(video_url)

if yt_data:
    title = yt_data.get('videoDetails', {}).get('title', 'Unknown Title')
    print(f"\nVideo Title: {title}")
    extract_video_streams(yt_data)
