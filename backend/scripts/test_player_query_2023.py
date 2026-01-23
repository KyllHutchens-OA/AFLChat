"""
Test player query with valid data (2023).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from app.agent.graph import agent

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


async def test_valid_player_query():
    """Test a player query with data that exists."""
    query = "How many disposals did Patrick Cripps average in 2023?"

    logger.info("=" * 80)
    logger.info(f"Testing Valid Player Query")
    logger.info(f"Query: {query}")
    logger.info("=" * 80)

    try:
        result = await agent.run(query)

        # Check response
        response = result.get("natural_language_summary", "")
        if response:
            logger.info(f"✅ Response generated ({len(response)} chars)")
            logger.info(f"\n📝 Response:\n{response}\n")

            # Check if it contains a number (should have actual data)
            import re
            numbers = re.findall(r'\d+\.?\d*', response)
            if numbers:
                logger.info(f"✅ Response contains numbers: {numbers}")
            else:
                logger.warning("⚠️  Response doesn't contain any numbers (expected for 2023)")
        else:
            logger.warning("⚠️  No response generated")

        # Check confidence
        confidence = result.get("confidence", 0)
        logger.info(f"Confidence: {confidence}")

        # Check data
        data = result.get("query_results")
        if data is not None:
            logger.info(f"\nData returned:\n{data.to_string()}")

        logger.info("=" * 80)
        return result

    except Exception as e:
        logger.error(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    await test_valid_player_query()


if __name__ == "__main__":
    asyncio.run(main())
