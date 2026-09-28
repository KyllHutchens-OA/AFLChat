import { CLUBS } from '../../constants/clubs';
import { useClub } from '../../contexts/ClubContext';
import GuernseyIcon from './GuernseyIcon';
import { CLUB_PATTERNS } from './clubPatterns';

// Section 2: "Pick your colours" — replaces the old /welcome induction gate.
// No gate, no modal: picking a club re-themes the page live.
const GuernseyStrip = () => {
  const { club, setClub } = useClub();

  return (
    <section className="bg-white py-12 sm:py-16">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 lg:px-10">
        <h2 className="font-display text-3xl text-ink mb-2">Pick your colours.</h2>
        <p className="text-warm-600 mb-8 max-w-2xl">
          Barrack for someone? Pick your colours. (You can change your mind. Unlike your mate who
          went Collingwood.)
        </p>

        <div className="grid grid-cols-6 sm:grid-cols-9 lg:grid-cols-18 gap-3 sm:gap-4">
          {CLUBS.map((c) => {
            const selected = club?.abbreviation === c.abbreviation;
            return (
              <button
                key={c.abbreviation}
                onClick={() => setClub(selected ? null : c.abbreviation)}
                title={c.name}
                aria-pressed={selected}
                aria-label={`${selected ? 'Un-pick' : 'Pick'} ${c.name}`}
                className={`group flex flex-col items-center gap-1.5 p-1.5 rounded-lg transition-all
                            ${selected ? 'bg-warm-100 ring-2 ring-sherrin' : 'hover:bg-warm-50'}`}
              >
                <GuernseyIcon
                  primary={c.primaryColor}
                  secondary={c.secondaryColor}
                  pattern={CLUB_PATTERNS[c.abbreviation] ?? 'solid'}
                  className="w-9 h-11 sm:w-11 sm:h-14 transition-transform group-hover:scale-110"
                />
                <span className="text-[10px] text-warm-600 group-hover:text-ink">{c.abbreviation}</span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
};

export default GuernseyStrip;
