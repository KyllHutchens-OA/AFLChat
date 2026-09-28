import { Link, useLocation } from 'react-router-dom';

interface TabLink {
  path: string;
  label: string;
  aliases?: string[];
  icon: React.ReactNode;
}

const ASK_ICON = (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8-1.06 0-2.076-.163-3.02-.462L3 20l1.518-4.55C3.55 14.155 3 12.648 3 11c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
  </svg>
);

const LIVE_ICON = (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="12" r="3" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M8.5 8.5a5 5 0 000 7M15.5 8.5a5 5 0 010 7M5.5 5.5a9 9 0 000 13M18.5 5.5a9 9 0 010 13" />
  </svg>
);

const ABOUT_ICON = (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="12" r="9" strokeWidth={2} />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 16v-4M12 8h.01" />
  </svg>
);

const TABS: TabLink[] = [
  { path: '/ask', label: 'Ask', aliases: ['/afl', '/aflagent'], icon: ASK_ICON },
  { path: '/live', label: 'Live', icon: LIVE_ICON },
  { path: '/about', label: 'How it works', icon: ABOUT_ICON },
];

// Bottom tab bar, mobile only. Replaces the top-nav links so there's room
// for the logo up top; the club picker and spoiler toggle move into the
// settings sheet (MobileSettingsSheet) instead of competing for space here.
const MobileTabBar = () => {
  const location = useLocation();

  const isActive = (tab: TabLink) => {
    if (tab.aliases?.some((a) => location.pathname.startsWith(a))) return true;
    return location.pathname.startsWith(tab.path);
  };

  return (
    <nav
      aria-label="Primary"
      className="sm:hidden fixed bottom-0 inset-x-0 z-30 bg-paper/95 backdrop-blur-brand border-t border-warm-200/60"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="flex items-stretch justify-around h-14">
        {TABS.map((tab) => {
          const active = isActive(tab);
          return (
            <Link
              key={tab.path}
              to={tab.path}
              aria-current={active ? 'page' : undefined}
              className={`flex-1 flex flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-colors
                ${active ? 'text-sherrin' : 'text-warm-600 hover:text-ink'}`}
            >
              {tab.icon}
              {tab.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
};

export default MobileTabBar;
