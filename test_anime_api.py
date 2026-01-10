#!/usr/bin/env python3
"""
Test script to explore Anime API endpoints and response structure.
"""

import httpx
import json
from pprint import pprint

BASE_URL = "https://anime-api2-three.vercel.app"


async def test_api():
    """Test all anime API endpoints."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        print("="*80)
        print("1. TESTING SEARCH ENDPOINT")
        print("="*80)
        
        # Search for naruto
        search_response = await client.get(
            f"{BASE_URL}/api/search",
            params={"keyword": "naruto"}
        )
        search_data = search_response.json()
        print(f"\nSearch Response Status: {search_response.status_code}")
        print(f"Search Data Keys: {search_data.keys()}")
        
        if search_data.get("success"):
            results = search_data.get("results", [])
            print(f"\nResults Type: {type(results)}")
            
            if isinstance(results, dict):
                results = list(results.values())
            
            print(f"Found {len(results)} results")
            
            if results:
                first_result = results[0]
                print(f"\nFirst Result:")
                pprint(first_result, width=120)
                
                anime_id = first_result.get("id", "")
                print(f"\nAnime ID: {anime_id}")
                
                print("\n" + "="*80)
                print("2. TESTING INFO ENDPOINT")
                print("="*80)
                
                # Get anime info
                info_response = await client.get(f"{BASE_URL}/api/info/{anime_id}")
                info_data = info_response.json()
                print(f"\nInfo Response Status: {info_response.status_code}")
                print(f"Info Data Keys: {info_data.keys()}")
                print(f"\nInfo Data:")
                pprint(info_data, width=120)
                
                print("\n" + "="*80)
                print("3. TESTING EPISODES ENDPOINT")
                print("="*80)
                
                # Get episodes
                episodes_response = await client.get(f"{BASE_URL}/api/episodes/{anime_id}")
                episodes_data = episodes_response.json()
                print(f"\nEpisodes Response Status: {episodes_response.status_code}")
                print(f"Episodes Data Keys: {episodes_data.keys()}")
                
                if episodes_data.get("success"):
                    episodes = episodes_data.get("episodes", [])
                    print(f"\nTotal Episodes: {episodes_data.get('totalEpisodes')}")
                    
                    if episodes:
                        first_episode = episodes[0]
                        print(f"\nFirst Episode:")
                        pprint(first_episode, width=120)
                        
                        # Extract episode ID
                        ep_id_str = first_episode.get("id", "")
                        print(f"\nEpisode ID String: {ep_id_str}")
                        
                        if "?ep=" in ep_id_str:
                            ep_id = ep_id_str.split("?ep=")[1]
                            print(f"Extracted Episode ID: {ep_id}")
                            
                            print("\n" + "="*80)
                            print("4. TESTING STREAM ENDPOINT")
                            print("="*80)
                            
                            # Get stream data
                            stream_response = await client.get(
                                f"{BASE_URL}/api/stream",
                                params={
                                    "id": anime_id,
                                    "episode_id": ep_id,
                                    "server": "hd-1",
                                    "type": "sub"
                                }
                            )
                            stream_data = stream_response.json()
                            print(f"\nStream Response Status: {stream_response.status_code}")
                            print(f"Stream Data Keys: {stream_data.keys()}")
                            print(f"\nFull Stream Data:")
                            pprint(stream_data, width=120, depth=5)
                            
                            # Extract streaming link
                            print("\n" + "="*80)
                            print("5. EXTRACTING STREAM URL")
                            print("="*80)
                            
                            streaming_links = stream_data.get("streamingLink", [])
                            print(f"\nStreamingLink Type: {type(streaming_links)}")
                            print(f"StreamingLink Value: {streaming_links}")
                            
                            if isinstance(streaming_links, dict):
                                print("\nIt's a dict! Keys:")
                                for key, value in streaming_links.items():
                                    print(f"  {key}: {type(value)} = {value}")
                            elif isinstance(streaming_links, list):
                                print("\nIt's a list! First item:")
                                if streaming_links:
                                    pprint(streaming_links[0], width=120)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_api())
