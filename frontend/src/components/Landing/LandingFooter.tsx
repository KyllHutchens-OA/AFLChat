import { Link } from 'react-router-dom';
import { useState } from 'react';
import LogoMark from '../Layout/LogoMark';

const LandingFooter = () => {
  const [sirenPlayed, setSirenPlayed] = useState(false);

  return (
    <footer className="bg-ink text-white/70 py-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 lg:px-10">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 mb-6">
          <div className="flex items-center gap-2">
            <LogoMark className="w-6 h-6" />
            <span className="font-display text-sm tracking-wide text-white">FOOTY-NAC</span>
          </div>
          <p className="text-sm max-w-md">
            Built by a data scientist who wanted real numbers behind footy debates.
          </p>
        </div>

        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm mb-6">
          <Link to="/about" className="hover:text-white transition-colors">About</Link>
          <a href="https://github.com/KyllHutchens-OA/AFLChat" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">GitHub</a>
          <a href="https://instagram.com/footy.nac" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">Instagram</a>
        </div>

        <button
          onClick={() => setSirenPlayed(true)}
          aria-label="Full time"
          title="Full time"
          className="text-xs text-white/40 hover:text-nightgame transition-colors"
        >
          {sirenPlayed ? 'FT. Thanks for reading.' : 'Siren'}
        </button>
      </div>
    </footer>
  );
};

export default LandingFooter;
