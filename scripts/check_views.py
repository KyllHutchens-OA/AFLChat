#!/usr/bin/env python3
"""
Check website views in the last 24 hours.
Provides visitor analytics including unique visitors, page views, and IP addresses.
"""
import sys
import os
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# AEDT timezone
AEDT = ZoneInfo('Australia/Sydney')

# Disable SQL query logging by setting production mode before imports
os.environ['FLASK_ENV'] = 'production'

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy import func
from app.data.database import Session
from app.data.models import PageView, Conversation


def get_chat_stats(hours=24):
    """Get chat message statistics from the specified time period."""
    from sqlalchemy import text
    session = Session()

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        # Check if chat_type column exists
        has_chat_type = False
        try:
            result = session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'conversations' AND column_name = 'chat_type'"
            ))
            has_chat_type = result.fetchone() is not None
        except:
            pass

        # Get conversations updated in the time period using raw SQL to avoid model issues
        if has_chat_type:
            result = session.execute(text(
                "SELECT id, chat_type, messages, updated_at FROM conversations WHERE updated_at >= :since"
            ), {'since': since})
        else:
            result = session.execute(text(
                "SELECT id, 'afl' as chat_type, messages, updated_at FROM conversations WHERE updated_at >= :since"
            ), {'since': since})

        rows = result.fetchall()

        # Count messages by chat type
        afl_conversations = 0
        afl_messages = 0
        resume_conversations = 0
        resume_messages = 0

        for row in rows:
            chat_type = row[1] if row[1] else 'afl'
            messages = row[2] or []

            # Count only messages sent within the time period
            recent_messages = 0
            for msg in messages:
                msg_time = msg.get('timestamp')
                if msg_time:
                    try:
                        msg_dt = datetime.fromisoformat(msg_time.replace('Z', '+00:00'))
                        if msg_dt.replace(tzinfo=None) >= since:
                            recent_messages += 1
                    except:
                        pass

            if chat_type == 'resume':
                resume_conversations += 1
                resume_messages += recent_messages
            else:
                afl_conversations += 1
                afl_messages += recent_messages

        return {
            'afl_conversations': afl_conversations,
            'afl_messages': afl_messages,
            'resume_conversations': resume_conversations,
            'resume_messages': resume_messages
        }

    finally:
        session.close()


def check_views(hours=24):
    """Check page views from the specified time period."""
    session = Session()

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        # Total page views in last 24 hours
        total_views = session.query(PageView).filter(
            PageView.timestamp >= since
        ).count()

        # Unique visitors (by visitor_id)
        unique_visitors = session.query(
            func.count(func.distinct(PageView.visitor_id))
        ).filter(PageView.timestamp >= since).scalar()

        # Unique IP addresses
        unique_ips = session.query(
            func.count(func.distinct(PageView.ip_address))
        ).filter(
            PageView.timestamp >= since,
            PageView.ip_address.isnot(None)
        ).scalar()

        # Views per page
        views_per_page = session.query(
            PageView.page,
            func.count(PageView.id).label('views')
        ).filter(
            PageView.timestamp >= since
        ).group_by(PageView.page).order_by(func.count(PageView.id).desc()).all()

        # Top IP addresses
        top_ips = session.query(
            PageView.ip_address,
            func.count(PageView.id).label('views')
        ).filter(
            PageView.timestamp >= since,
            PageView.ip_address.isnot(None)
        ).group_by(PageView.ip_address).order_by(func.count(PageView.id).desc()).limit(10).all()

        # Views per hour (last 24 hours)
        hour_trunc = func.date_trunc('hour', PageView.timestamp)
        views_per_hour = session.query(
            hour_trunc.label('hour'),
            func.count(PageView.id).label('views')
        ).filter(
            PageView.timestamp >= since
        ).group_by(hour_trunc).order_by(hour_trunc).all()

        # Get chat stats
        chat_stats = get_chat_stats(hours)

        # Print results
        now_aedt = datetime.now(AEDT)
        since_aedt = since.replace(tzinfo=timezone.utc).astimezone(AEDT)
        print("\n" + "=" * 60)
        print(f"WEBSITE ANALYTICS - LAST {hours} HOURS")
        print("=" * 60)
        print(f"Report generated: {now_aedt.strftime('%Y-%m-%d %H:%M:%S')} AEDT")
        print(f"Data from: {since_aedt.strftime('%Y-%m-%d %H:%M:%S')} AEDT")
        print("-" * 60)

        print(f"\n{'PAGE VIEWS':^60}")
        print("-" * 60)
        print(f"Total Page Views:    {total_views:,}")
        print(f"Unique Visitors:     {unique_visitors:,}")
        print(f"Unique IP Addresses: {unique_ips:,}")

        print(f"\n{'CHAT USAGE':^60}")
        print("-" * 60)
        print(f"Resume Chat:         {chat_stats['resume_messages']:,} messages ({chat_stats['resume_conversations']:,} conversations)")
        print(f"AFL Chat:            {chat_stats['afl_messages']:,} messages ({chat_stats['afl_conversations']:,} conversations)")

        if views_per_page:
            print(f"\n{'VIEWS BY PAGE':^60}")
            print("-" * 60)
            for page, views in views_per_page:
                print(f"  {page:<40} {views:>6} views")

        if top_ips:
            print(f"\n{'TOP 10 IP ADDRESSES':^60}")
            print("-" * 60)
            for ip, views in top_ips:
                print(f"  {ip or 'Unknown':<40} {views:>6} views")

        if views_per_hour:
            print(f"\n{'VIEWS PER HOUR (AEDT)':^60}")
            print("-" * 60)
            for hour, views in views_per_hour:
                if hour:
                    hour_aedt = hour.replace(tzinfo=timezone.utc).astimezone(AEDT)
                    hour_str = hour_aedt.strftime('%Y-%m-%d %H:00')
                else:
                    hour_str = 'Unknown'
                bar = '#' * min(views, 50)
                print(f"  {hour_str}  {views:>4}  {bar}")

        print("\n" + "=" * 60)

        return {
            'total_views': total_views,
            'unique_visitors': unique_visitors,
            'unique_ips': unique_ips,
            'views_per_page': views_per_page,
            'top_ips': top_ips,
            'views_per_hour': views_per_hour
        }

    finally:
        session.close()


def get_all_ip_addresses(hours=24):
    """Get all unique IP addresses from the specified time period."""
    session = Session()

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        ips = session.query(
            PageView.ip_address,
            func.count(PageView.id).label('views'),
            func.min(PageView.timestamp).label('first_seen'),
            func.max(PageView.timestamp).label('last_seen')
        ).filter(
            PageView.timestamp >= since,
            PageView.ip_address.isnot(None)
        ).group_by(PageView.ip_address).order_by(func.count(PageView.id).desc()).all()

        print(f"\n{'ALL IP ADDRESSES (Last ' + str(hours) + ' hours)':^60}")
        print("=" * 60)
        print(f"{'IP Address':<20} {'Views':>8} {'First Seen':>15} {'Last Seen':>15}")
        print("-" * 60)

        for ip, views, first_seen, last_seen in ips:
            if first_seen:
                first = first_seen.replace(tzinfo=timezone.utc).astimezone(AEDT).strftime('%H:%M:%S')
            else:
                first = 'N/A'
            if last_seen:
                last = last_seen.replace(tzinfo=timezone.utc).astimezone(AEDT).strftime('%H:%M:%S')
            else:
                last = 'N/A'
            print(f"{ip or 'Unknown':<20} {views:>8} {first:>15} {last:>15}")

        print("-" * 60)
        print(f"Total unique IPs: {len(ips)}")

        return ips

    finally:
        session.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Check website views analytics')
    parser.add_argument('--hours', type=int, default=24,
                        help='Number of hours to look back (default: 24)')
    parser.add_argument('--ips', action='store_true',
                        help='Show detailed IP address list')

    args = parser.parse_args()

    check_views(args.hours)

    if args.ips:
        get_all_ip_addresses(args.hours)
