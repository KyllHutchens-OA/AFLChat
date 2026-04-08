import { Link, useLocation } from 'react-router-dom';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';

interface NavLink {
  path: string;
  label: string;
  aliases?: string[];
}

const NavBar = () => {
  const location = useLocation();
  const { hideScores, toggleSpoilerMode } = useSpoilerMode();
  const navLinks: NavLink[] = [
    { path: '/aflagent', label: 'Chat', aliases: ['/', '/afl'] },
    { path: '/live', label: 'Live' },
    { path: '/about', label: 'About' },
  ];

  const isActive = (link: NavLink) => {
    if (link.aliases?.includes(location.pathname)) return true;
    return location.pathname.startsWith(link.path);
  };

  return (
    <nav className="glass sticky top-0 z-30 border-b border-afl-warm-200/50">
      <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10">
        <div className="flex items-center justify-between h-16">
          {/* Logo/Brand */}
          <Link to="/" className="flex items-center gap-2">
            <span className="text-xl font-semibold text-afl-warm-900">
              Footy-NAC
            </span>
            <span className="hidden sm:inline text-sm text-afl-warm-500">
              Not Another Commentator
            </span>
          </Link>

          {/* Navigation */}
          <div className="flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className={`
                  px-3 sm:px-4 py-2 rounded-apple text-sm font-medium transition-all duration-200
                  ${isActive(link)
                    ? 'bg-afl-accent text-white shadow-apple-sm'
                    : 'text-afl-warm-700 hover:bg-afl-warm-100'
                  }
                `}
              >
                {link.label}
              </Link>
            ))}

            {/* Change Team */}
            <Link
              to="/welcome"
              className="px-2 py-2 rounded-apple text-sm transition-all duration-200 text-afl-warm-400 hover:text-afl-warm-700 hover:bg-afl-warm-100"
              title="Change team"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
            </Link>

            {/* Spoiler Toggle */}
            <button
              onClick={toggleSpoilerMode}
              className={`
                ml-2 sm:ml-4 p-2 rounded-apple transition-all duration-200
                ${hideScores
                  ? 'bg-afl-accent text-white'
                  : 'text-afl-warm-500 hover:bg-afl-warm-100'
                }
              `}
              title={hideScores ? 'Scores hidden - click to show' : 'Scores visible - click to hide'}
            >
              {hideScores ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
};

export default NavBar;
