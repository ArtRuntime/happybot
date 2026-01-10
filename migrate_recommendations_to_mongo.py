#!/usr/bin/env python3
"""
Migration script to import recommendation dataset from CSV to MongoDB.
Run this once to populate the MongoDB collection with recommendation data.

Usage:
    python migrate_recommendations_to_mongo.py
"""

import sys
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configuration
CSV_PATH = "bot/data/recommendations_dataset.csv"
MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "HappyBot")
COLLECTION_NAME = "recommendations"


def migrate_csv_to_mongodb():
    """Migrate CSV dataset to MongoDB"""
    
    print("=" * 60)
    print("Recommendation Dataset Migration: CSV → MongoDB")
    print("=" * 60)
    
    # Step 1: Check if CSV exists
    print(f"\n1. Checking CSV file: {CSV_PATH}")
    if not os.path.exists(CSV_PATH):
        print(f"   ❌ Error: CSV file not found at {CSV_PATH}")
        return False
    print(f"   ✅ CSV file found")
    
    # Step 2: Load CSV
    print("\n2. Loading CSV data...")
    try:
        df = pd.read_csv(CSV_PATH)
        print(f"   ✅ Loaded {len(df)} records from CSV")
        print(f"   Columns: {list(df.columns)}")
    except Exception as e:
        print(f"   ❌ Error loading CSV: {e}")
        return False
    
    # Step 3: Connect to MongoDB
    print(f"\n3. Connecting to MongoDB...")
    if not MONGO_URL:
        print(f"   ❌ Error: MONGO_URL not set in environment variables")
        print(f"   Please set MONGO_URL in your .env file")
        return False
    
    try:
        client = MongoClient(MONGO_URL)
        db = client[MONGO_DB_NAME]
        collection = db[COLLECTION_NAME]
        print(f"   ✅ Connected to MongoDB: {MONGO_DB_NAME}.{COLLECTION_NAME}")
    except Exception as e:
        print(f"   ❌ Error connecting to MongoDB: {e}")
        return False
    
    # Step 4: Check existing data
    print("\n4. Checking existing data...")
    existing_count = collection.count_documents({})
    if existing_count > 0:
        print(f"   ⚠️  Collection already has {existing_count} documents")
        response = input("   Do you want to REPLACE all existing data? (yes/no): ")
        if response.lower() != 'yes':
            print("   Aborted by user")
            return False
        print("   Dropping existing collection...")
        collection.drop()
        print("   ✅ Collection dropped")
    
    # Step 5: Prepare data
    print("\n5. Preparing data for MongoDB...")
    
    # Convert DataFrame to list of dictionaries
    records = df.to_dict('records')
    
    # Clean up NaN values (MongoDB doesn't like NaN)
    for record in records:
        for key, value in record.items():
            if pd.isna(value):
                record[key] = None
    
    print(f"   ✅ Prepared {len(records)} records")
    
    # Step 6: Insert into MongoDB
    print("\n6. Inserting data into MongoDB...")
    try:
        # Insert in batches for better performance
        batch_size = 1000
        total_inserted = 0
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            collection.insert_many(batch, ordered=False)
            total_inserted += len(batch)
            print(f"   Progress: {total_inserted}/{len(records)} records inserted...", end='\r')
        
        print(f"\n   ✅ Successfully inserted {total_inserted} records")
    except Exception as e:
        print(f"\n   ❌ Error inserting data: {e}")
        return False
    
    # Step 7: Create indexes for better performance
    print("\n7. Creating indexes...")
    try:
        collection.create_index("video_id")
        collection.create_index("title")
        print("   ✅ Indexes created on 'video_id' and 'title'")
    except Exception as e:
        print(f"   ⚠️  Warning: Could not create indexes: {e}")
    
    # Step 8: Verify
    print("\n8. Verifying migration...")
    final_count = collection.count_documents({})
    print(f"   MongoDB collection now has: {final_count} documents")
    
    if final_count == len(df):
        print("   ✅ Verification successful!")
    else:
        print(f"   ⚠️  Warning: Count mismatch (CSV: {len(df)}, MongoDB: {final_count})")
    
    # Show sample document
    print("\n9. Sample document:")
    sample = collection.find_one({})
    if sample:
        print(f"   Title: {sample.get('title', 'N/A')}")
        print(f"   Video ID: {sample.get('video_id', 'N/A')}")
        print(f"   Channel: {sample.get('channel_title', 'N/A')}")
        print(f"   Text soup length: {len(sample.get('text_soup', ''))} characters")
    
    print("\n" + "=" * 60)
    print("✅ Migration completed successfully!")
    print("=" * 60)
    print(f"\nYour bot can now use MongoDB for recommendations!")
    print(f"Collection: {MONGO_DB_NAME}.{COLLECTION_NAME}")
    print(f"Documents: {final_count}")
    
    # Cleanup
    client.close()
    return True


if __name__ == "__main__":
    try:
        success = migrate_csv_to_mongodb()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
