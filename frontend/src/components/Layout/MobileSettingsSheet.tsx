import { CLUBS } from '../../constants/clubs';
import { useClub, CLUB_PICKER_ENABLED } from '../../contexts/ClubContext';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';
import Dialog from '../Modal/Dialog';

interface MobileSettingsSheetProps {
  onClose: () => void;
}

// Mobile-only settings sheet: the spoiler toggle (and club picker, when
// enabled) from the desktop nav live here so the mobile top bar stays to just
// the logo and this one button (nav links themselves move to MobileTabBar).
const MobileSettingsSheet: React.FC<MobileSettingsSheetProps> = ({ onClose }) => {
  const { club, setClub } = useClub();
  const { hideScores, toggleSpoilerMode } = useSpoilerMode();

  return (
    <Dialog
      onClose={onClose}
      labelId="mobile-settings-title"
      className="bg-white w-full max-w-sm rounded-xl shadow-card-xl border border-warm-200 p-5 max-h-[85vh] overflow-y-auto"
    >
      <div className="flex items-center justify-between mb-4">
        <h2 id="mobile-settings-title" className="text-lg font-semibold text-ink">Settings</h2>
        <button
          onClick={onClose}
          aria-label="Close settings"
          className="p-1.5 rounded-md text-warm-600 hover:bg-warm-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sherrin"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <section className={CLUB_PICKER_ENABLED ? 'mb-6' : ''}>
        <p className="section-label mb-2">Spoilers</p>
        <button
          onClick={toggleSpoilerMode}
          className={`w-full flex items-center justify-between px-4 py-3 rounded-lg border font-medium text-sm
            ${hideScores ? 'bg-sherrin text-white border-sherrin' : 'bg-white text-ink border-warm-300'}`}
        >
          {hideScores ? 'Scores hidden' : 'Scores visible'}
          <span className="text-xs opacity-80">{hideScores ? 'Tap to show' : 'Tap to hide'}</span>
        </button>
      </section>

      {CLUB_PICKER_ENABLED && (
      <section>
        <p className="section-label mb-2">Pick your colours</p>
        <div className="grid grid-cols-6 gap-2.5">
          {CLUBS.map((c) => (
            <button
              key={c.abbreviation}
              onClick={() => setClub(club?.abbreviation === c.abbreviation ? null : c.abbreviation)}
              aria-label={club?.abbreviation === c.abbreviation ? `${c.name}. Your club. Tap to clear.` : c.name}
              aria-pressed={club?.abbreviation === c.abbreviation}
              className={`w-9 h-9 rounded-full border-2 transition-transform hover:scale-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sherrin ${
                club?.abbreviation === c.abbreviation ? 'border-ink' : 'border-transparent'
              }`}
              style={{ backgroundColor: c.primaryColor }}
            />
          ))}
        </div>
        {club && (
          <button
            onClick={() => setClub(null)}
            className="mt-3 text-xs text-warm-600 hover:text-ink underline"
          >
            Clear ({club.nickname})
          </button>
        )}
      </section>
      )}
    </Dialog>
  );
};

export default MobileSettingsSheet;
