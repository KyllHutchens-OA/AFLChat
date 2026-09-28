import { useState, useRef, useEffect } from 'react';
import { CLUBS } from '../../constants/clubs';
import { useClub } from '../../contexts/ClubContext';

// Small club-colour dot in the nav that opens a compact picker popover.
const ClubPicker = () => {
  const { club, setClub } = useClub();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={club ? `Your club: ${club.name}. Change club.` : 'Pick your club'}
        aria-expanded={open}
        className="w-6 h-6 rounded-full border-2 border-warm-300 hover:border-warm-400 transition-colors"
        style={{ backgroundColor: club ? club.primaryColor : '#F6F1E7' }}
      />
      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-64 bg-white rounded-lg shadow-card-lg border border-warm-200 p-3 z-40"
        >
          <p className="section-label mb-2">Pick your colours</p>
          <div className="grid grid-cols-6 gap-2">
            {CLUBS.map((c) => (
              <button
                key={c.abbreviation}
                onClick={() => { setClub(c.abbreviation); setOpen(false); }}
                title={c.name}
                aria-label={c.name}
                className={`w-7 h-7 rounded-full border-2 transition-transform hover:scale-110 ${
                  club?.abbreviation === c.abbreviation ? 'border-ink' : 'border-transparent'
                }`}
                style={{ backgroundColor: c.primaryColor }}
              />
            ))}
          </div>
          {club && (
            <button
              onClick={() => { setClub(null); setOpen(false); }}
              className="mt-3 text-xs text-warm-600 hover:text-ink underline"
            >
              Clear ({club.nickname})
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default ClubPicker;
