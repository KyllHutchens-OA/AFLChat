"""Check status of scoring events."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.data.database import get_session
from app.data.models import LiveGameEvent
from sqlalchemy import func

with get_session() as session:
    # Count events without player
    without = session.query(func.count(LiveGameEvent.id)).filter(
        LiveGameEvent.player_name == None,
        LiveGameEvent.event_type.in_(['goal', 'behind'])
    ).scalar()

    # Count events with player
    with_player = session.query(func.count(LiveGameEvent.id)).filter(
        LiveGameEvent.player_name != None,
        LiveGameEvent.event_type.in_(['goal', 'behind'])
    ).scalar()

    print(f'Scoring events WITH player: {with_player}')
    print(f'Scoring events WITHOUT player: {without}')

    if without == 0:
        print('\nSuccess! All scoring events now have player names!')
    else:
        print(f'\nStill have {without} events without players')
