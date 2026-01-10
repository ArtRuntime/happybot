#!/usr/bin/env python3
"""
Build TF-IDF Dataset from Listening History
Creates recommendations_dataset.csv from songs users have played

Usage:
    python build_tfidf_dataset.py
"""

import asyncio
import pandas as pd
from pymongo import AsyncMongoClient
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "HappyBot")


async def build_dataset():
    """Build TF-IDF dataset from listening history"""
    print("=" * 60)
    print("Build TF-IDF Dataset from Listening History")
    print("=" * 60)
    
    # Connect to MongoDB
    print("\n1. Connecting to MongoDB...")
    client = AsyncMongoClient(MONGO_URL)
    db = client[MONGO_DB_NAME]
    
    # Check played_songs collection
    print("\n2. Collecting listening history...")
    played_collection = db['played_songs']
    
    total_count = await played_collection.count_documents({})
    if total_count == 0:
        print("   ❌ No listening history found!")
        print("   Play some songs first, then try again.")
        await client.close()
        return False
    
    print(f"   ✅ Found {total_count} song plays")
    
    # Get last 90 days of unique songs
    date_threshold = datetime.now() - timedelta(days=90)
    
    pipeline = [
        {'$match': {'played_at': {'$gte': date_threshold}}},
        {'$group': {
            '_id': '$video_id',
            'title': {'$first': '$title'},
            'channel': {'$first': '$channel'},
            'play_count': {'$sum': 1},
        }},
        {'$sort': {'play_count': -1}},
    ]
    
    songs = await played_collection.aggregate(pipeline).to_list(length=None)
    
    print(f"   ✅ Found {len(songs)} unique songs")
    
    if len(songs) < 20:
        print(f"   ⚠️  Only {len(songs)} songs - need at least 20 for good TF-IDF")
        print("   Current dataset will work, but play more songs for better results!")
    
    # Build dataset in TF-IDF format
    print("\n3. Building TF-IDF dataset...")
    
    dataset = []
    for song in songs:
        video_id = song['_id']
        title = song.get('title', '')
        channel = song.get('channel', '')
        
        # Create text_soup (important for TF-IDF)
        # Combines title and artist/channel for better matching
        text_soup = f"{title} {channel}".lower().strip()
        
        dataset.append({
            'video_id': video_id,
            'title': title,
            'channel_title': channel,
            'text_soup': text_soup,  # This is what TF-IDF uses!
            'play_count': song.get('play_count', 1),
        })
    
    df = pd.DataFrame(dataset)
    
    print(f"   ✅ Built dataset with {len(df)} songs")
    
    # Insert directly into MongoDB recommendations collection
    print("\n3. Inserting into MongoDB 'recommendations' collection...")
    
    recommendations_collection = db['recommendations']
    
    # Check existing data
    existing_count = await recommendations_collection.count_documents({})
    if existing_count > 0:
        print(f"   ⚠️  Collection has {existing_count} documents")
        print(f"   Do you want to REPLACE all data? (yes/no): ", end="")
        response = input().strip().lower()
        if response == 'yes':
            print("   Dropping existing collection...")
            await recommendations_collection.drop()
            print("   ✅ Dropped")
        else:
            print("   Keeping existing data, adding new songs...")
    
    # Convert DataFrame to list of dicts
    records = df.to_dict('records')
    
    # Insert into MongoDB
    if records:
        await recommendations_collection.insert_many(records)
        print(f"   ✅ Inserted {len(records)} songs into MongoDB")
    
    # Create indexes for better performance
    await recommendations_collection.create_index("video_id")
    await recommendations_collection.create_index("title")
    print("   ✅ Created indexes")
    
    # Show statistics
    print("\n4. Dataset Statistics:")
    print(f"   Total songs in MongoDB: {len(df)}")
    print(f"   Total plays tracked: {df['play_count'].sum()}")
    
    print(f"\n   🎵 Top 10 Most Played:")
    for i, row in df.head(10).iterrows():
        print(f"      {i+1}. {row['title']} ({row['play_count']} plays)")
    
    await client.close()
    
    print("\n" + "=" * 60)
    print("✅ Dataset Imported to MongoDB!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Enable TF-IDF in .env:")
    print("   ENABLE_TFIDF_RECOMMENDATIONS=true")
    print("\n2. Restart bot:")
    print("   python -m bot")
    print("\n3. Bot will use MongoDB recommendations automatically!")
    print("   (No CSV file needed!)")
    
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(build_dataset())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
