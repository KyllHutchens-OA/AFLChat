import React, { useState, useEffect } from 'react';
import { useLiveGameEvents } from '../../hooks/useLiveGameEvents';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';

interface Notification {
  id: string;
  event_type: 'goal' | 'behind';
  team_name: string;
  team_abbreviation: string;
  home_score: number;
  away_score: number;
  time_str: string;
  timestamp: string;
  // Player info
  player_name?: string;
  jersey_number?: number;
  player_total_goals?: number;
}

interface ScoringPopupProps {
  enabled?: boolean;
}

const ScoringPopup: React.FC<ScoringPopupProps> = ({ enabled = false }) => {
  const { hideScores } = useSpoilerMode();
  const { latestEvent } = useLiveGameEvents(enabled);
  const [notifications, setNotifications] = useState<Notification[]>([]);

  // Don't show notifications when spoiler mode is on
  if (hideScores) {
    return null;
  }

  // Listen for new scoring events
  useEffect(() => {
    if (!latestEvent) return;

    // Create notification
    const notification: Notification = {
      id: `${latestEvent.game_id}-${latestEvent.timestamp}`,
      event_type: latestEvent.event_type,
      team_name: latestEvent.team_name,
      team_abbreviation: latestEvent.team_abbreviation,
      home_score: latestEvent.home_score,
      away_score: latestEvent.away_score,
      time_str: latestEvent.time_str,
      timestamp: latestEvent.timestamp,
      player_name: latestEvent.player_name,
      jersey_number: latestEvent.jersey_number,
      player_total_goals: latestEvent.player_total_goals,
    };

    // Add to notifications (max 3)
    setNotifications((prev) => {
      const updated = [notification, ...prev];
      return updated.slice(0, 3); // Keep only latest 3
    });

    // Auto-dismiss after 6 seconds
    setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== notification.id));
    }, 6000);
  }, [latestEvent]);

  if (notifications.length === 0) {
    return null;
  }

  return (
    <div className="fixed bottom-6 left-6 z-50 space-y-3">
      {notifications.map((notification) => {
        const isGoal = notification.event_type === 'goal';
        const borderColor = isGoal ? 'border-l-apple-green' : 'border-l-apple-orange';
        const iconBg = isGoal ? 'bg-apple-green' : 'bg-apple-orange';
        const icon = isGoal ? '⚽' : '1';

        return (
          <div
            key={notification.id}
            className={`
              glass rounded-apple-lg border-l-4 ${borderColor} p-4
              shadow-apple-lg min-w-[280px] max-w-[320px]
              animate-scale-in
            `}
          >
            <div className="flex items-start gap-3">
              {/* Icon */}
              <div className={`${iconBg} w-10 h-10 rounded-full flex items-center justify-center text-white text-lg font-bold flex-shrink-0`}>
                {icon}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-apple-gray-900 mb-0.5">
                  {isGoal ? 'GOAL!' : 'Behind'} - {notification.team_abbreviation}
                </p>
                {notification.player_name && (
                  <p className="text-sm font-medium text-apple-gray-800 mb-0.5">
                    {notification.jersey_number && `#${notification.jersey_number} `}
                    {notification.player_name}
                    {isGoal && notification.player_total_goals && notification.player_total_goals > 1 && (
                      <span className="text-apple-gray-500 ml-1">
                        ({notification.player_total_goals} goals)
                      </span>
                    )}
                  </p>
                )}
                <p className="text-xs text-apple-gray-600 mb-1">
                  {notification.time_str}
                </p>
                <p className="text-sm font-medium text-apple-gray-700">
                  Score: {notification.home_score} - {notification.away_score}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default ScoringPopup;
