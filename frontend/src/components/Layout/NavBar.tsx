import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';
import LogoMark from './LogoMark';
import ClubPicker from './ClubPicker';
import MobileSettingsSheet from './MobileSettingsSheet';
import { CLUB_PICKER_ENABLED } from '../../contexts/ClubContext';

interface NavLink {
  path: string;
  label: string;
  aliases?: string[];
}

const NavBar = () => {
  const location = useLocation();
  const { hideScores, toggleSpoilerMode } = useSpoilerMode();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const isLanding = location.pathname === '/';
  const navLinks: NavLink[] = [
    { path: '/ask', label: 'Ask', aliases: ['/afl', '/aflagent'] },
    { path: '/live', label: 'Live' },
    { path: '/about', label: 'About' },
  ];

  const isActive = (link: NavLink) => {
    if (link.aliases?.some((a) => location.pathname.startsWith(a))) return true;
    return location.pathname.startsWith(link.path);
  };

  return (
    <nav className="sticky top-0 z-30 bg-paper/90 backdrop-blur-brand border-b border-warm-200/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 lg:px-10">
        <div className="flex items-center justify-between h-14">
          <Link to="/" className="flex items-center gap-2 shrink-0 min-w-0">
            <LogoMark className="w-7 h-7 shrink-0" />
            <span className="font-display text-lg tracking-wide text-ink leading-none whitespace-nowrap">
              FOOTY-NAC
            </span>
          </Link>

          {/* Desktop nav: links + club picker + spoiler toggle inline.
              On mobile these links move to the bottom tab bar, and the club
              picker / spoiler toggle move into the settings sheet, so this
              whole block is hidden below sm. */}
          <div className="hidden sm:flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className={`
                  px-3 sm:px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200
                  focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sherrin
                  ${isActive(link)
                    ? 'bg-sherrin text-white shadow-card-sm'
                    : 'text-warm-700 hover:bg-warm-100'
                  }
                `}
              >
                {link.label}
              </Link>
            ))}
            {isLanding && (
              <a
                href="#how-it-thinks"
                className="inline-block px-3 py-2 rounded-lg text-sm font-medium text-warm-700 hover:bg-warm-100 transition-all
                           focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sherrin"
              >
                How it thinks
              </a>
            )}

            {CLUB_PICKER_ENABLED && <ClubPicker />}

            <button
              onClick={toggleSpoilerMode}
              aria-label={hideScores ? 'Scores hidden. Click to show scores.' : 'Scores visible. Click to hide scores.'}
              title={hideScores ? 'Scores hidden - click to show' : 'Scores visible - click to hide'}
              className={`
                ml-1 p-2 rounded-lg transition-all duration-200
                focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sherrin
                ${hideScores ? 'bg-sherrin text-white' : 'text-warm-600 hover:bg-warm-100'}
              `}
            >
              {hideScores ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>

          {/* Mobile: a single settings button opens the settings sheet */}
          <button
            onClick={() => setSettingsOpen(true)}
            aria-label="Open settings"
            className="sm:hidden p-2 rounded-lg text-warm-600 hover:bg-warm-100 transition-colors
                       focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sherrin"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>
      </div>

      {settingsOpen && <MobileSettingsSheet onClose={() => setSettingsOpen(false)} />}
    </nav>
  );
};

export default NavBar;
