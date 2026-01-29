import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

const VISITOR_ID_KEY = 'visitor_id';
const API_URL = 'http://localhost:5001/api/analytics/track';

function getOrCreateVisitorId(): string {
  let visitorId = localStorage.getItem(VISITOR_ID_KEY);
  if (!visitorId) {
    // Generate a simple unique ID
    visitorId = `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
    localStorage.setItem(VISITOR_ID_KEY, visitorId);
  }
  return visitorId;
}

export function useAnalytics() {
  const location = useLocation();
  const lastTrackedPath = useRef<string | null>(null);

  useEffect(() => {
    // Only track if the path actually changed
    if (lastTrackedPath.current === location.pathname) {
      return;
    }
    lastTrackedPath.current = location.pathname;

    const visitorId = getOrCreateVisitorId();

    // Send tracking request (fire and forget)
    fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        visitor_id: visitorId,
        page: location.pathname,
        referrer: document.referrer || null,
        user_agent: navigator.userAgent,
      }),
    }).catch((err) => {
      // Silently fail - analytics shouldn't break the app
      console.debug('Analytics tracking failed:', err);
    });
  }, [location.pathname]);
}
