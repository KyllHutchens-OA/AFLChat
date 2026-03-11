"""
RSS News Fetcher - Fetch AFL news from RSS feeds with duplicate detection.
"""
import feedparser
from datetime import datetime
from app.data.database import Session
from app.data.models import NewsArticle
import logging

logger = logging.getLogger(__name__)


class RSSNewsFetcher:
    """Fetch AFL news from RSS feeds with duplicate detection."""

    RSS_FEEDS = {
        'afl.com.au': 'https://www.afl.com.au/news/rss',
        'foxsports': 'https://www.foxsports.com.au/afl/rss',
        'theage': 'https://www.theage.com.au/rss/sport/afl.xml',
    }

    INJURY_KEYWORDS = [
        'injury', 'injured', 'hurt', 'out', 'sidelined',
        'hamstring', 'knee', 'concussion', 'suspended',
        'ruled out', 'withdraw', 'medical'
    ]

    @classmethod
    def fetch_all_feeds(cls) -> int:
        """
        Fetch from all RSS feeds, return count of new articles.
        
        Returns:
            int: Number of new articles added
        """
        total_new = 0
        
        for source, url in cls.RSS_FEEDS.items():
            try:
                count = cls._fetch_feed(source, url)
                total_new += count
                logger.info(f"✓ {source}: {count} new articles")
            except Exception as e:
                logger.error(f"✗ Error fetching {source}: {e}")
        
        return total_new

    @classmethod
    def _fetch_feed(cls, source: str, url: str) -> int:
        """
        Fetch a single RSS feed.
        
        Args:
            source: Source name (e.g., 'afl.com.au')
            url: RSS feed URL
            
        Returns:
            int: Number of new articles added
        """
        session = Session()
        new_articles = 0
        
        try:
            feed = feedparser.parse(url)
            
            for entry in feed.entries:
                # Check if URL already exists (prevents duplicates)
                existing = session.query(NewsArticle).filter_by(url=entry.link).first()
                if existing:
                    continue
                
                # Parse published date
                published_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_date = datetime(*entry.published_parsed[:6])
                else:
                    published_date = datetime.utcnow()
                
                # Extract content
                content = None
                if hasattr(entry, 'summary'):
                    content = entry.summary[:1000]  # Limit to 1000 chars
                
                # Detect injury-related articles
                is_injury = cls._is_injury_related(entry.title, content or '')
                
                # Create article
                article = NewsArticle(
                    source=source,
                    title=entry.title,
                    url=entry.link,
                    published_date=published_date,
                    content=content,
                    author=getattr(entry, 'author', None),
                    is_injury_related=is_injury
                )
                
                session.add(article)
                new_articles += 1
            
            session.commit()
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error processing feed {source}: {e}")
            raise
        finally:
            session.close()
        
        return new_articles

    @classmethod
    def _is_injury_related(cls, title: str, content: str) -> bool:
        """
        Check if article is injury-related based on keywords.
        
        Args:
            title: Article title
            content: Article content/summary
            
        Returns:
            bool: True if injury-related
        """
        text = f"{title} {content}".lower()
        return any(keyword in text for keyword in cls.INJURY_KEYWORDS)
