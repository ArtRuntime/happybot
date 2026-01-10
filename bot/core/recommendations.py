# Copyright (c) 2025 alex5402.t.me
# Licensed under the MIT License.
# This file is part of happybot

"""
TF-IDF based content recommendation engine for YouTube videos.
Provides intelligent song recommendations based on content similarity.
"""

import os
import pandas as pd
from pathlib import Path
from typing import List, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from bot import logger


class RecommendationEngine:
    """
    Content-based recommendation system using TF-IDF and cosine similarity.
    
    Features:
    - Lazy initialization (loads only when first used)
    - MongoDB or CSV data source (MongoDB preferred)
    - Robust exception handling
    - Memory-efficient caching
    - Graceful degradation when dataset unavailable
    """
    
    def __init__(self, dataset_path: str = "bot/data/recommendations_dataset.csv", 
                 mongo_db=None, collection_name: str = "recommendations"):
        """
        Initialize the recommendation engine.
        
        Args:
            dataset_path: Path to the CSV dataset (fallback if MongoDB unavailable)
            mongo_db: MongoDB database instance (if None, uses CSV)
            collection_name: MongoDB collection name for recommendations
        """
        self.dataset_path = dataset_path
        self.mongo_db = mongo_db
        self.collection_name = collection_name
        self.df: Optional[pd.DataFrame] = None
        self.tfidf_matrix = None
        self.cosine_sim = None
        self.indices = None
        self.initialized = False
        self.enabled = True
        self.data_source = None  # Will be 'mongodb' or 'csv'
        
        # Determine data source
        if mongo_db is not None:
            self.data_source = 'mongodb'
            logger.info("Recommendation engine configured to use MongoDB")
        elif Path(dataset_path).exists():
            self.data_source = 'csv'
            logger.info(f"Recommendation engine configured to use CSV: {dataset_path}")
        else:
            logger.warning(f"No data source available. MongoDB: {mongo_db is not None}, CSV exists: {Path(dataset_path).exists()}")
            self.enabled = False
    
    async def _load_from_mongodb(self) -> bool:
        """
        Load dataset from MongoDB (async).
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Loading recommendations from MongoDB collection '{self.collection_name}'...")
            
            # Get collection
            collection = self.mongo_db[self.collection_name]
            
            # Count documents (async operation)
            count = await collection.count_documents({})
            if count == 0:
                logger.error(f"MongoDB collection '{self.collection_name}' is empty")
                return False
            
            logger.info(f"Found {count} documents in collection")
            
            # Load all documents into DataFrame (async cursor)
            cursor = collection.find({}, {
                '_id': 0,  # Exclude MongoDB _id
                'video_id': 1,
                'title': 1,
                'text_soup': 1,
                'channel_title': 1,
                'view_count': 1,
                'published_year': 1,
            })
            
            # Convert async cursor to list
            documents = await cursor.to_list(length=None)
            self.df = pd.DataFrame(documents)
            logger.info(f"✅ Loaded {len(self.df)} videos from MongoDB")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load from MongoDB: {e}")
            return False
    
    def _load_from_csv(self) -> bool:
        """
        Load dataset from CSV file.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Loading recommendations from CSV: {self.dataset_path}")
            self.df = pd.read_csv(self.dataset_path)
            logger.info(f"✅ Loaded {len(self.df)} videos from CSV")
            return True
        except FileNotFoundError:
            logger.error(f"Dataset file not found: {self.dataset_path}")
            return False
        except pd.errors.EmptyDataError:
            logger.error(f"Dataset file is empty: {self.dataset_path}")
            return False
        except Exception as e:
            logger.error(f"Failed to load CSV: {e}")
            return False
    
    async def _lazy_init(self) -> bool:
        """
        Lazy initialization - loads dataset and builds TF-IDF matrix on first use (async).
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        if self.initialized:
            return True
        
        if not self.enabled:
            return False
        
        try:
            logger.info("Initializing TF-IDF recommendation engine...")
            
            # Load dataset from preferred source
            if self.data_source == 'mongodb':
                success = await self._load_from_mongodb()
                if not success and Path(self.dataset_path).exists():
                    logger.info("MongoDB load failed, falling back to CSV...")
                    success = self._load_from_csv()
            elif self.data_source == 'csv':
                success = self._load_from_csv()
            else:
                logger.error("No data source available")
                self.enabled = False
                return False
            
            if not success:
                logger.error("Failed to load dataset from any source")
                self.enabled = False
                return False
            
            # Validate required columns
            required_cols = ['title', 'text_soup']
            missing_cols = [col for col in required_cols if col not in self.df.columns]
            if missing_cols:
                logger.error(f"Dataset missing required columns: {missing_cols}")
                self.enabled = False
                return False
            
            # Fill NaN values in text_soup
            self.df['text_soup'] = self.df['text_soup'].fillna('')
            
            # Remove rows with empty text_soup
            original_len = len(self.df)
            self.df = self.df[self.df['text_soup'].str.strip() != '']
            if len(self.df) < original_len:
                logger.warning(f"Removed {original_len - len(self.df)} rows with empty text_soup")
            
            if len(self.df) == 0:
                logger.error("No valid data in dataset after cleaning")
                self.enabled = False
                return False
            
            # Build TF-IDF matrix with multilingual support
            try:
                logger.info("Building TF-IDF matrix...")
                # Multilingual TF-IDF configuration
                # - No language-specific stop words (supports Hindi, Bengali, etc.)
                # - Use n-grams for better phrase matching
                # - Increased max_features for more vocabulary coverage
                tfidf = TfidfVectorizer(
                    stop_words=None,  # Support all languages
                    max_features=15000,  # Increased for multilingual
                    ngram_range=(1, 2),  # Use unigrams and bigrams
                    min_df=2,  # Ignore very rare terms
                    max_df=0.8,  # Ignore very common terms
                )
                self.tfidf_matrix = tfidf.fit_transform(self.df['text_soup'])
                logger.info(f"TF-IDF matrix shape: {self.tfidf_matrix.shape}")
            except MemoryError:
                logger.error("Not enough memory to build TF-IDF matrix")
                self.enabled = False
                return False
            except Exception as e:
                logger.error(f"Failed to build TF-IDF matrix: {e}")
                self.enabled = False
                return False
            
            # Compute cosine similarity
            try:
                logger.info("Computing cosine similarity matrix...")
                self.cosine_sim = linear_kernel(self.tfidf_matrix, self.tfidf_matrix)
                logger.info(f"Cosine similarity matrix computed: {self.cosine_sim.shape}")
            except MemoryError:
                logger.error("Not enough memory to compute cosine similarity")
                self.enabled = False
                return False
            except Exception as e:
                logger.error(f"Failed to compute cosine similarity: {e}")
                self.enabled = False
                return False
            
            # Create title-to-index mapping
            self.indices = pd.Series(self.df.index, index=self.df['title'].str.lower())
            
            self.initialized = True
            logger.info("✅ TF-IDF recommendation engine initialized successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Unexpected error during initialization: {e}", exc_info=True)
            self.enabled = False
            return False
    
    def _fuzzy_match_title(self, title: str, threshold: float = 0.7) -> Optional[str]:
        """
        Try to find a fuzzy match for the title in the dataset.
        
        Args:
            title: Title to search for
            threshold: Minimum similarity threshold (0-1)
        
        Returns:
            Matched title from dataset or None
        """
        if self.df is None:
            return None
        
        title_lower = title.lower().strip()
        
        # Try exact match first
        if title_lower in self.indices.index:
            return title_lower
        
        # Try partial matching
        for dataset_title in self.df['title'].str.lower():
            if title_lower in dataset_title or dataset_title in title_lower:
                return dataset_title
        
        # TODO: Could add more sophisticated fuzzy matching (e.g., Levenshtein distance)
        # For now, return None if no match found
        return None
    
    async def get_recommendations(self, title: str, limit: int = 10) -> List[str]:
        """
        Get content-based recommendations for a given video title (async).
        
        Args:
            title: Title of the video to find similar content for
            limit: Maximum number of recommendations to return
        
        Returns:
            List of recommended video titles (empty list if no recommendations)
        """
        # Lazy initialization (async)
        if not await self._lazy_init():
            logger.debug("Recommendation engine not available")
            return []
        
        try:
            # Try to find the title in the dataset
            title_lower = title.lower().strip()
            
            # Try exact match
            if title_lower not in self.indices.index:
                # Try fuzzy match
                matched_title = self._fuzzy_match_title(title)
                if matched_title:
                    logger.info(f"Fuzzy matched '{title}' to '{matched_title}'")
                    title_lower = matched_title
                else:
                    logger.debug(f"Title '{title}' not found in dataset")
                    return []
            
            # Get the index of the video
            idx = self.indices[title_lower]
            
            # Handle duplicate titles (take first occurrence)
            if isinstance(idx, pd.Series):
                idx = idx.iloc[0]
            
            # Get similarity scores for this video
            sim_scores = list(enumerate(self.cosine_sim[idx]))
            
            # Sort by similarity (descending)
            sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
            
            # Get top N similar videos (excluding the input video itself)
            sim_scores = sim_scores[1:limit+1]
            
            # Get video indices
            video_indices = [i[0] for i in sim_scores]
            
            # Return titles
            recommendations = self.df['title'].iloc[video_indices].tolist()
            
            logger.info(f"Found {len(recommendations)} recommendations for '{title}'")
            return recommendations
            
        except KeyError:
            logger.debug(f"Title '{title}' not found in indices")
            return []
        except Exception as e:
            logger.error(f"Error getting recommendations: {e}", exc_info=True)
            return []
    
    def get_status(self) -> dict:
        """
        Get the current status of the recommendation engine.
        
        Returns:
            Dictionary with status information
        """
        return {
            "enabled": self.enabled,
            "initialized": self.initialized,
            "dataset_path": self.dataset_path,
            "dataset_size": len(self.df) if self.df is not None else 0,
            "matrix_shape": self.tfidf_matrix.shape if self.tfidf_matrix is not None else None,
        }
