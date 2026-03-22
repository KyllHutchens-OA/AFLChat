import { Link, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';

interface NavLink {
  path: string;
  label: string;
  aliases?: string[];
}

const NavBar = () => {
  const location = useLocation();
  const { hideScores, toggleSpoilerMode } = useSpoilerMode();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

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
    <nav className="glass sticky top-0 z-30 border-b border-apple-gray-200/50">
      <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10">
        <div className="flex items-center justify-between h-16">
          {/* Logo/Brand */}
          <Link to="/" className="flex items-center gap-2">
            <span className="text-xl font-semibold text-apple-gray-900">
              Footy-NAC
            </span>
            <span className="hidden sm:inline text-sm text-apple-gray-500">
              Not Another Commentator
            </span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className={`
                  px-4 py-2 rounded-apple text-sm font-medium transition-all duration-200
                  ${isActive(link)
                    ? 'bg-apple-blue-500 text-white shadow-apple-sm'
                    : 'text-apple-gray-700 hover:bg-apple-gray-100'
                  }
                `}
              >
                {link.label}
              </Link>
            ))}

            {/* Spoiler Toggle */}
            <button
              onClick={toggleSpoilerMode}
              className={`
                ml-4 p-2 rounded-apple transition-all duration-200
                ${hideScores
                  ? 'bg-apple-blue-500 text-white'
                  : 'text-apple-gray-500 hover:bg-apple-gray-100'
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

          {/* Mobile menu button */}
          <div className="md:hidden flex items-center gap-2">
            {/* Mobile spoiler toggle */}
            <button
              onClick={toggleSpoilerMode}
              className={`p-2 rounded-apple ${hideScores ? 'bg-apple-blue-500 text-white' : 'text-apple-gray-500'}`}
              title={hideScores ? 'Scores hidden' : 'Scores visible'}
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

            {/* Hamburger */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-apple text-apple-gray-700 hover:bg-apple-gray-100"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {mobileMenuOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        {mobileMenuOpen && (
          <div className="md:hidden py-4 border-t border-apple-gray-200/50">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                onClick={() => setMobileMenuOpen(false)}
                className={`
                  block px-4 py-3 rounded-apple text-base font-medium transition-colors
                  ${isActive(link)
                    ? 'bg-apple-blue-50 text-apple-blue-500'
                    : 'text-apple-gray-700 hover:bg-apple-gray-50'
                  }
                `}
              >
                {link.label}
              </Link>
            ))}
          </div>
        )}
      </div>
    </nav>
  );
};

export default NavBar;
