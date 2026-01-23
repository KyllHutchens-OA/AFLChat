"""
Test Context Enrichment (Phase 3) and Data Quality (Phase 6)

Verifies:
- Data quality checks and warnings
- Context enrichment (form, venue splits, historical percentiles)
- Efficiency metrics (shooting, margins, quarters)
- Integration with in-depth mode
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
import json
from app.agent.graph import agent

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


async def test_enriched_query():
    """Test query that should trigger full enrichment."""
    query = "Tell me about Geelong's performance from 2020 to 2023"

    logger.info("=" * 80)
    logger.info(f"Testing Context Enrichment")
    logger.info(f"Query: {query}")
    logger.info("=" * 80)

    try:
        result = await agent.run(query)

        # Check mode and analysis types
        logger.info(f"\n📊 Analysis Configuration:")
        logger.info(f"  Mode: {result.get('analysis_mode', 'N/A')}")
        logger.info(f"  Types: {result.get('analysis_types', [])}")

        # Check statistics with data quality
        stats = result.get('statistical_analysis', {})
        if stats.get('success'):
            logger.info(f"\n✅ Statistics Computed:")

            for analysis_type in ['average', 'trend', 'comparison', 'rank']:
                if analysis_type in stats:
                    analysis = stats[analysis_type]
                    if analysis.get('success'):
                        # Check for data quality
                        if 'data_quality' in analysis:
                            quality = analysis['data_quality']
                            logger.info(f"\n  {analysis_type.upper()}:")
                            logger.info(f"    Sample size: {quality.get('sample_size', 'N/A')}")
                            logger.info(f"    Confidence: {quality.get('confidence', 'N/A')}")
                            logger.info(f"    Data completeness: {quality.get('data_completeness', 'N/A')}%")

                            warnings = quality.get('warnings', [])
                            if warnings:
                                logger.info(f"    Warnings: {len(warnings)}")
                                for i, warning in enumerate(warnings[:2], 1):
                                    logger.info(f"      {i}. {warning}")
                            else:
                                logger.info(f"    ✓ No data quality issues")

        # Check context insights
        context = result.get('context_insights', {})
        if context:
            logger.info(f"\n🔍 Context Enrichment:")

            # Form analysis
            if 'form_analysis' in context:
                form = context['form_analysis']
                logger.info(f"  Form Analysis:")
                logger.info(f"    Momentum: {form.get('momentum', 'N/A')}")
                logger.info(f"    Recent games analyzed: {form.get('recent_games', 'N/A')}")

            # Venue splits
            if 'venue_splits' in context:
                splits = context['venue_splits']
                logger.info(f"  Venue Splits:")
                if 'home' in splits:
                    logger.info(f"    Home: {splits['home']['wins']}/{splits['home']['games']} "
                              f"({splits['home']['win_rate']:.1%})")
                if 'away' in splits:
                    logger.info(f"    Away: {splits['away']['wins']}/{splits['away']['games']} "
                              f"({splits['away']['win_rate']:.1%})")
                if 'home_advantage_pct' in splits:
                    logger.info(f"    Home advantage: {splits['home_advantage_pct']:+.1f}%")

            # Historical percentiles
            if 'historical_percentiles' in context:
                percentiles = context['historical_percentiles']
                logger.info(f"  Historical Context:")
                logger.info(f"    Seasons analyzed: {percentiles.get('seasons_analyzed', 'N/A')}")
                if 'best_season' in percentiles:
                    best = percentiles['best_season']
                    logger.info(f"    Best season: {best['year']} ({best['wins']} wins)")

            # Efficiency metrics
            if 'efficiency' in context:
                efficiency = context['efficiency']
                logger.info(f"  Efficiency Metrics:")

                if 'shooting' in efficiency:
                    shooting = efficiency['shooting']
                    logger.info(f"    Shooting accuracy: {shooting['accuracy_percent']:.1f}% "
                              f"({shooting['total_goals']} goals from {shooting['total_shots']} shots)")

                if 'margins' in efficiency:
                    margins = efficiency['margins']
                    logger.info(f"    Average margin: {margins['avg_margin']:+.1f} points")
                    logger.info(f"    Close games: {margins['close_game_pct']:.1f}%")

        else:
            logger.warning(f"\n⚠️  No context enrichment found")

        # Check response quality
        response = result.get('natural_language_summary', '')
        logger.info(f"\n📝 Response Length: {len(response)} characters")

        # Count contextual keywords
        context_keywords = [
            'form', 'momentum', 'home', 'away', 'advantage', 'venue',
            'historical', 'percentile', 'accuracy', 'efficiency', 'margin',
            'confidence', 'sample'
        ]
        keyword_count = sum(1 for kw in context_keywords if kw in response.lower())
        logger.info(f"   Context keywords found: {keyword_count}/{len(context_keywords)}")

        # Show response preview
        logger.info(f"\n📄 Response Preview:")
        preview_length = min(500, len(response))
        logger.info(response[:preview_length] + ("..." if len(response) > preview_length else ""))

        # Save full result
        with open('/tmp/context_enrichment_test.json', 'w') as f:
            result_copy = result.copy()
            if 'query_results' in result_copy and result_copy['query_results'] is not None:
                result_copy['query_results'] = result_copy['query_results'].to_dict()
            json.dump(result_copy, f, indent=2, default=str)

        logger.info(f"\n💾 Full result saved to /tmp/context_enrichment_test.json")

        # Final assessment
        logger.info(f"\n" + "=" * 80)
        logger.info("Assessment:")

        checks = []
        if result.get('analysis_mode') == 'in_depth':
            checks.append("✅ In-depth mode triggered")
        else:
            checks.append("❌ Should be in-depth mode")

        if stats.get('success') and 'trend' in stats:
            checks.append("✅ Trend analysis computed")
        else:
            checks.append("❌ Trend analysis missing")

        if context:
            checks.append("✅ Context enrichment present")
        else:
            checks.append("❌ Context enrichment missing")

        if keyword_count >= 5:
            checks.append("✅ Response includes contextual insights")
        else:
            checks.append("⚠️  Response may lack context")

        for check in checks:
            logger.info(f"  {check}")

        logger.info("=" * 80)

        return result

    except Exception as e:
        logger.error(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    await test_enriched_query()


if __name__ == "__main__":
    asyncio.run(main())
