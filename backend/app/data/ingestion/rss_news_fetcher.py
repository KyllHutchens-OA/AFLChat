"""
RSS News Fetcher - Fetch AFL news from RSS feeds with LLM-based enrichment.

Instead of keyword matching, each article is classified and enriched by a cheap
LLM (GPT-5-nano) at ingestion time. The LLM determines AFL relevance, extracts
teams/players, categorises the article, and writes a one-line summary.
"""
import feedparser
import requests
import json
import os
import logging
from datetime import datetime
from openai import OpenAI

from app.data.database import Session
from app.data.models import NewsArticle

logger = logging.getLogger(__name__)

# Batch size for LLM enrichment (multiple articles per call to save cost)
ENRICHMENT_BATCH_SIZE = 5


class RSSNewsFetcher:
    """Fetch AFL news from RSS feeds and enrich with LLM classification."""

    RSS_FEEDS = {
        'smh': 'https://www.smh.com.au/rss/sport/afl.xml',
        'theage': 'https://www.theage.com.au/rss/sport/afl.xml',
        'abc': 'https://www.abc.net.au/news/feed/51120/rss.xml',
    }

    @classmethod
    def fetch_all_feeds(cls) -> int:
        """
        Fetch from all RSS feeds, enrich with LLM, return count of new articles.

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
        Fetch a single RSS feed and enrich new articles via LLM.

        Args:
            source: Source name (e.g., 'smh')
            url: RSS feed URL

        Returns:
            int: Number of new articles added
        """
        session = Session()

        try:
            headers = {"User-Agent": "AFL-Analytics-App/1.0"}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            feed = feedparser.parse(response.text)

            # Collect new (unseen) entries first
            new_entries = []
            for entry in feed.entries:
                existing = session.query(NewsArticle).filter_by(url=entry.link).first()
                if existing:
                    continue

                published_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_date = datetime(*entry.published_parsed[:6])
                else:
                    published_date = datetime.utcnow()

                content = None
                if hasattr(entry, 'summary'):
                    content = entry.summary[:1000]

                new_entries.append({
                    'source': source,
                    'title': entry.title,
                    'url': entry.link,
                    'published_date': published_date,
                    'content': content,
                    'author': getattr(entry, 'author', None),
                })

            if not new_entries:
                return 0

            # Enrich articles via LLM in batches
            enriched = cls._enrich_articles_batch(new_entries)

            new_articles = 0
            for entry, enrichment in zip(new_entries, enriched):
                # Skip non-AFL articles (LLM decided it's not relevant)
                if not enrichment.get('is_afl', False):
                    logger.debug(f"Skipping non-AFL article: {entry['title'][:60]}")
                    continue

                article = NewsArticle(
                    source=entry['source'],
                    title=entry['title'],
                    url=entry['url'],
                    published_date=entry['published_date'],
                    content=entry['content'],
                    author=entry['author'],
                    is_afl=True,
                    category=enrichment.get('category', 'other'),
                    summary=enrichment.get('summary', ''),
                    is_injury_related=enrichment.get('category') == 'injury',
                    injury_details=enrichment.get('injury_details'),
                    related_teams=enrichment.get('teams', []),
                    related_players=enrichment.get('players', []),
                    enriched_at=datetime.utcnow(),
                )

                session.add(article)
                new_articles += 1

            session.commit()
            return new_articles

        except Exception as e:
            session.rollback()
            logger.error(f"Error processing feed {source}: {e}")
            raise
        finally:
            session.close()

    @classmethod
    def _enrich_articles_batch(cls, entries: list) -> list:
        """
        Send articles to GPT-5-nano for classification and enrichment.

        Processes in batches of ENRICHMENT_BATCH_SIZE to keep costs low.
        Falls back to a safe default if the LLM call fails.

        Args:
            entries: List of article dicts with 'title' and 'content'

        Returns:
            List of enrichment dicts (same order as entries)
        """
        all_enrichments = []

        for i in range(0, len(entries), ENRICHMENT_BATCH_SIZE):
            batch = entries[i:i + ENRICHMENT_BATCH_SIZE]
            enrichments = cls._call_enrichment_llm(batch)
            all_enrichments.extend(enrichments)

        return all_enrichments

    @classmethod
    def _call_enrichment_llm(cls, batch: list) -> list:
        """
        Call GPT-5-nano to classify a batch of articles.

        Args:
            batch: List of article dicts

        Returns:
            List of enrichment dicts
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set, using fallback enrichment")
            return [cls._fallback_enrichment(e) for e in batch]

        model = os.getenv("NEWS_ENRICHMENT_MODEL", "gpt-5-nano")

        # Build the prompt with all articles in the batch
        articles_text = ""
        for idx, entry in enumerate(batch):
            title = entry['title']
            content = (entry['content'] or '')[:400]
            articles_text += f"\n[Article {idx + 1}]\nTitle: {title}\nContent: {content}\n"

        prompt = f"""Classify each article below. For each, return a JSON object with these fields:
- "is_afl": boolean — is this about AFL (Australian Football League)?
- "teams": list of AFL team names mentioned (full names, e.g. "Collingwood", "Sydney Swans")
- "players": list of player names mentioned
- "category": one of: "match_result", "match_preview", "injury", "trade", "off_field", "analysis", "other"
- "summary": one concise sentence summarising the article for an AFL fan
- "injury_details": if category is "injury", a list of objects with "player", "type", "severity" (e.g. "minor", "moderate", "major", "season-ending"). null otherwise.

Return a JSON array with one object per article, in the same order. Only valid JSON, no markdown.
{articles_text}"""

        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )

            raw = response.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            results = json.loads(raw)

            # Validate we got the right number of results
            if not isinstance(results, list) or len(results) != len(batch):
                logger.warning(
                    f"LLM returned {len(results) if isinstance(results, list) else 'non-list'} "
                    f"results for {len(batch)} articles, using fallback"
                )
                return [cls._fallback_enrichment(e) for e in batch]

            # Sanitise each result
            sanitised = []
            valid_categories = {'match_result', 'match_preview', 'injury', 'trade', 'off_field', 'analysis', 'other'}
            for r in results:
                sanitised.append({
                    'is_afl': bool(r.get('is_afl', False)),
                    'teams': r.get('teams', []) if isinstance(r.get('teams'), list) else [],
                    'players': r.get('players', []) if isinstance(r.get('players'), list) else [],
                    'category': r.get('category', 'other') if r.get('category') in valid_categories else 'other',
                    'summary': str(r.get('summary', ''))[:500],
                    'injury_details': r.get('injury_details') if r.get('category') == 'injury' else None,
                })
            return sanitised

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM enrichment response: {e}")
            return [cls._fallback_enrichment(e) for e in batch]
        except Exception as e:
            logger.error(f"LLM enrichment call failed: {e}")
            return [cls._fallback_enrichment(e) for e in batch]

    @classmethod
    def _fallback_enrichment(cls, entry: dict) -> dict:
        """
        Fallback enrichment when LLM is unavailable.
        Assumes AFL relevance (since feeds are AFL-specific) with minimal metadata.
        """
        return {
            'is_afl': True,
            'teams': [],
            'players': [],
            'category': 'other',
            'summary': entry['title'],
            'injury_details': None,
        }
