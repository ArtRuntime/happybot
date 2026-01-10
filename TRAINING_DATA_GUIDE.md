# Training Data Collection Guide

## 🎯 Overview

This guide explains how to collect multilingual YouTube data to train your recommendation system for Hindi, Bengali, Tamil, Telugu, and English songs.

## 📋 Prerequisites

1. ✅ YouTube Data API v3 key (you have: `AIzaSyD9l-q6GwIy-9cE5rir-S0RMHtJ7B_eQjI`)
2. ✅ Python packages: `pip install google-api-python-client pandas`

## 🚀 Quick Start

### Step 1: Install Dependencies

```bash
pip install google-api-python-client
```

### Step 2: Run Data Collection

```bash
python collect_training_data.py
```

This will:
- Search for 500+ videos across multiple languages
- Collect video metadata (title, description, tags)
- Save to `multilingual_recommendations.csv`

**Expected time:** 5-10 minutes  
**API quota used:** ~600 units (out of 10,000 daily)

### Step 3: Import to MongoDB

```bash
# Option A: Use migration script (updates filename)
python migrate_recommendations_to_mongo.py

# Option B: Copy to default location
cp multilingual_recommendations.csv bot/data/recommendations_dataset.csv
python migrate_recommendations_to_mongo.py
```

### Step 4: Restart Bot

```bash
python -m bot
```

## 📊 What Gets Collected

### Hindi Songs (12 queries × 50 videos = ~600)
- Arijit Singh, Jubin Nautiyal, Neha Kakkar
- Bollywood, Punjabi, Romantic songs
- Devotional and Party songs

### Bengali Songs (8 queries × 50 videos = ~400)
- Rabindra Sangeet, Modern songs
- Arijit Singh, Shreya Ghoshal Bengali songs
- Folk songs, Durga Puja songs

### English Songs (8 queries × 50 videos = ~400)
- Pop, Rock, Hip Hop, EDM
- Taylor Swift, The Weeknd, Bruno Mars

### Tamil & Telugu (4 queries each = ~400)
- AR Rahman, Anirudh, DSP, Thaman
- Latest 2024 releases

**Total: ~1,800 unique videos** (after removing duplicates)

## 🔧 Customization

### Adjust Videos Per Query

Edit `collect_training_data.py`:

```python
VIDEOS_PER_QUERY = 100  # Increase for more data (uses more quota)
```

### Add More Languages

Add to `SEARCH_QUERIES` dictionary:

```python
SEARCH_QUERIES = {
    # ... existing ...
    'kannada': [
        'kannada songs 2024',
        'armaan malik kannada songs',
    ],
    'malayalam': [
        'malayalam songs 2024',
        'vineeth sreenivasan songs',
    ],
}
```

### Custom Search Terms

Add your favorite artists or genres:

```python
'hindi': [
    'hindi songs 2024',
    'king songs',  # Add specific artist
    'hindi rap songs',  # Add specific genre
    # ... more
],
```

## 📈 API Quota Management

YouTube API has **10,000 units/day** quota:

- **Search**: 100 units per request
- **Video details**: 1 unit per request

With default settings:
- ~13 searches × 100 = 1,300 units
- ~1,800 videos × 1 = 1,800 units (batch requests)
- **Total: ~3,100 units** (30% of daily quota)

### If You Hit Quota Limit

1. **Reduce videos per query**: `VIDEOS_PER_QUERY = 30`
2. **Remove language categories**: Comment out languages you don't need
3. **Wait 24 hours**: Quota resets at midnight Pacific Time
4. **Use multiple API keys**: Create additional keys and rotate

## 🎓 Advanced: Continuous Updates

### Option 1: Schedule Weekly Collection

```bash
# Add to crontab (runs every Sunday at 2 AM)
0 2 * * 0 cd /path/to/bot && python collect_training_data.py && python migrate_recommendations_to_mongo.py
```

### Option 2: Incremental Updates

Modify script to only fetch latest videos:

```python
search_params = {
    # ... existing ...
    'publishedAfter': '2024-01-01T00:00:00Z',  # Only recent videos
}
```

## 🐛 Troubleshooting

### "API quota exceeded"
**Solution**: Wait 24 hours or use a different API key

### "No videos collected"
**Solution**: Check internet connection and API key validity

### "Permission denied" error
**Solution**: Make file executable: `chmod +x collect_training_data.py`

### Recommendations still not working for Hindi
**Solution**: 
1. Verify data imported: Check MongoDB has new data
2. Restart bot to reload TF-IDF
3. Check logs for "Loaded X videos from MongoDB"

## ✅ Verification

After collection and import:

1. **Check CSV file:**
   ```bash
   wc -l multilingual_recommendations.csv
   # Should show ~1800+ lines
   ```

2. **Check MongoDB:**
   ```bash
   # In mongo shell
   use HappyBot
   db.recommendations.count()
   # Should show ~1800+ documents
   ```

3. **Test recommendations:**
   - Play a Hindi song
   - Enable autoplay: `/autoplay smart`
   - Next song should be similar Hindi song
   - Check logs for "TF-IDF Recommendation SUCCESS"

## 🎉 Expected Results

### Before
- Hindi song → Random English song ❌
- Bengali song → Generic pop song ❌

### After
- Hindi song → Similar Hindi song ✅
- Bengali song → Similar Bengali song ✅
- Arijit Singh → More Arijit Singh songs ✅
- Keeps language consistency ✅

## 📝 Notes

- **Dataset grows over time**: Re-run monthly to keep fresh
- **Storage**: ~500KB per 1000 videos
- **Memory**: TF-IDF matrix needs ~300-400 MB RAM
- **Performance**: Negligible impact on bot speed

---

**Questions?** Check bot logs for detailed TF-IDF processing info!
