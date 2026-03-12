import React from 'react';

interface GameEvent {
  id: number;
  event_type: string;
  team: {
    id: number;
    name: string;
    abbreviation: string;
  } | null;
  home_score_after: number;
  away_score_after: number;
  quarter: number;
  time_str: string;
  timestamp: string;
}

interface EventTimelineProps {
  events: GameEvent[];
}

const EventTimeline: React.FC<EventTimelineProps> = ({ events }) => {
  if (!events || events.length === 0) {
    return (
      <div className="text-center py-8 text-apple-gray-500">
        No events yet
      </div>
    );
  }

  return (
    <div className="max-h-96 overflow-y-auto space-y-3">
      {events.map((event) => {
        const isGoal = event.event_type === 'goal';
        const isBehind = event.event_type === 'behind';
        const badgeColor = isGoal
          ? 'bg-apple-green text-white'
          : isBehind
          ? 'bg-apple-orange text-white'
          : 'bg-apple-gray-300 text-apple-gray-700';
        const badgeText = isGoal ? '6' : isBehind ? '1' : '•';

        return (
          <div
            key={event.id}
            className="flex items-center gap-3 p-3 rounded-apple bg-apple-gray-50 hover:bg-apple-gray-100 transition-colors"
          >
            {/* Event badge */}
            <div className={`w-8 h-8 rounded-full ${badgeColor} flex items-center justify-center font-bold text-sm flex-shrink-0`}>
              {badgeText}
            </div>

            {/* Event details */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-apple-gray-900">
                {event.team?.name || 'Unknown Team'}
              </p>
              <p className="text-xs text-apple-gray-600">
                Q{event.quarter} {event.time_str}
              </p>
            </div>

            {/* Score after */}
            <div className="text-right flex-shrink-0">
              <p className="text-sm font-medium text-apple-gray-700">
                {event.home_score_after} - {event.away_score_after}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default EventTimeline;
