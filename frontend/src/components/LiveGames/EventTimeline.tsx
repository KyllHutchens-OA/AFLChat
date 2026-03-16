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
  // Player info
  player_name?: string;
  player_api_sports_id?: number;
}

interface EventTimelineProps {
  events: GameEvent[];
  homeTeamAbbr?: string;
  awayTeamAbbr?: string;
}

// Helper to get relative time
const getRelativeTime = (timestamp: string): string => {
  const now = new Date();
  // Backend sends UTC timestamps - append 'Z' if not present to ensure correct parsing
  const utcTimestamp = timestamp.endsWith('Z') ? timestamp : `${timestamp}Z`;
  const eventTime = new Date(utcTimestamp);
  const diffMs = now.getTime() - eventTime.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 0) return 'Just now'; // Handle slight clock skew
  if (diffMins < 1) return 'Just now';
  if (diffMins === 1) return '1 min ago';
  if (diffMins < 60) return `${diffMins} mins ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours === 1) return '1 hour ago';
  return `${diffHours} hours ago`;
};

// Group events by quarter
const groupByQuarter = (events: GameEvent[]): Map<number, GameEvent[]> => {
  const grouped = new Map<number, GameEvent[]>();

  events.forEach((event) => {
    const quarter = event.quarter || 0;
    if (!grouped.has(quarter)) {
      grouped.set(quarter, []);
    }
    grouped.get(quarter)!.push(event);
  });

  return grouped;
};

const EventTimeline: React.FC<EventTimelineProps> = ({ events, homeTeamAbbr, awayTeamAbbr }) => {
  if (!events || events.length === 0) {
    return (
      <div className="text-center py-12 text-apple-gray-500">
        <div className="text-4xl mb-3">📋</div>
        <p className="font-medium">No scoring events yet</p>
        <p className="text-sm mt-1">Events will appear here as the game progresses</p>
      </div>
    );
  }

  const groupedEvents = groupByQuarter(events);
  const quarters = Array.from(groupedEvents.keys()).sort((a, b) => b - a);

  return (
    <div className="max-h-[500px] overflow-y-auto">
      {quarters.map((quarter) => (
        <div key={quarter} className="mb-6 last:mb-0">
          {/* Quarter Header */}
          <div className="sticky top-0 bg-white/90 backdrop-blur-sm z-10 py-2 mb-3 border-b border-apple-gray-200">
            <h4 className="text-sm font-semibold text-apple-gray-600 uppercase tracking-wide">
              {quarter === 0 ? 'Pre-Game' : `Quarter ${quarter}`}
            </h4>
          </div>

          {/* Events in this quarter */}
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-apple-gray-200" />

            <div className="space-y-3">
              {groupedEvents.get(quarter)!.map((event) => {
                const isGoal = event.event_type === 'goal';
                const isBehind = event.event_type === 'behind';
                const isHomeTeam = event.team?.abbreviation === homeTeamAbbr;

                // Determine colors
                const dotColor = isGoal
                  ? 'bg-apple-green border-apple-green'
                  : isBehind
                  ? 'bg-apple-orange border-apple-orange'
                  : 'bg-apple-gray-400 border-apple-gray-400';

                const cardBg = isGoal
                  ? 'bg-green-50 border-l-4 border-l-apple-green'
                  : isBehind
                  ? 'bg-orange-50 border-l-4 border-l-apple-orange'
                  : 'bg-apple-gray-50';

                return (
                  <div key={event.id} className="relative flex items-start gap-4 pl-2">
                    {/* Timeline dot */}
                    <div
                      className={`relative z-10 w-5 h-5 rounded-full border-2 ${dotColor} flex items-center justify-center flex-shrink-0 mt-3`}
                    >
                      {isGoal && (
                        <span className="text-[8px] font-bold text-white">6</span>
                      )}
                      {isBehind && (
                        <span className="text-[8px] font-bold text-white">1</span>
                      )}
                    </div>

                    {/* Event card */}
                    <div className={`flex-1 ${cardBg} rounded-apple p-3 shadow-sm`}>
                      <div className="flex items-start justify-between gap-3">
                        {/* Left side - Event details */}
                        <div className="flex-1 min-w-0">
                          {/* Team name */}
                          <div className="flex items-center gap-2 mb-1">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                                isGoal
                                  ? 'bg-apple-green text-white'
                                  : isBehind
                                  ? 'bg-apple-orange text-white'
                                  : 'bg-apple-gray-300 text-apple-gray-700'
                              }`}
                            >
                              {isGoal ? 'GOAL' : isBehind ? 'BEHIND' : event.event_type.toUpperCase()}
                            </span>
                            <span className="text-sm font-semibold text-apple-gray-900">
                              {event.team?.name || 'Unknown Team'}
                            </span>
                          </div>

                          {/* Player name */}
                          {event.player_name && (
                            <p className="text-sm text-apple-gray-700 mb-1">
                              {event.player_name}
                            </p>
                          )}

                          {/* Time */}
                          <p className="text-xs text-apple-gray-500">
                            {event.time_str} • {getRelativeTime(event.timestamp)}
                          </p>
                        </div>

                        {/* Right side - Score */}
                        <div className="text-right flex-shrink-0">
                          <div className="flex items-center gap-1 text-lg font-bold">
                            <span className={isHomeTeam && isGoal ? 'text-apple-green' : 'text-apple-gray-700'}>
                              {event.home_score_after}
                            </span>
                            <span className="text-apple-gray-400">-</span>
                            <span className={!isHomeTeam && isGoal ? 'text-apple-green' : 'text-apple-gray-700'}>
                              {event.away_score_after}
                            </span>
                          </div>
                          <p className="text-xs text-apple-gray-500 mt-0.5">
                            {homeTeamAbbr} - {awayTeamAbbr}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default EventTimeline;
