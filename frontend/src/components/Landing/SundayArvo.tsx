import { useNavigate } from 'react-router-dom';
import { useLiveGames } from '../../hooks/useLiveGames';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';
import Countdown from '../LiveGames/Countdown';

// Estimated Round 1 start (AFL seasons typically open mid-March); flagged as
// an estimate rather than a confirmed fixture.
const NEXT_SEASON_ESTIMATE = '2027-03-12T19:00:00+11:00';

const SundayArvo = () => {
  const navigate = useNavigate();
  const { games, loading } = useLiveGames();
  const { hideScores } = useSpoilerMode();
  const liveGames = games.filter((g) => g.status === 'live');

  if (loading) return null;

  if (liveGames.length > 0) {
    return (
      <section className="bg-white py-14 sm:py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-8 lg:px-10">
          <div className="flex items-center gap-2 mb-6">
            <span className="w-2 h-2 rounded-full bg-sherrin animate-breathe" />
            <h2 className="font-display text-3xl text-ink">Sunday arvo.</h2>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {liveGames.map((g) => (
              <button
                key={g.id}
                onClick={() => navigate('/live')}
                className="card p-4 text-left hover:shadow-card-md transition-shadow"
              >
                <div className="text-xs text-warm-600 mb-2">{g.round} &middot; {g.venue}</div>
                <div className="flex items-center justify-between font-display text-2xl text-ink tabular-nums">
                  <span>{g.home_team.abbreviation}</span>
                  <span>{hideScores ? '• •' : `${g.home_goals}.${g.home_behinds} (${g.home_score})`}</span>
                </div>
                <div className="flex items-center justify-between font-display text-2xl text-ink tabular-nums">
                  <span>{g.away_team.abbreviation}</span>
                  <span>{hideScores ? '• •' : `${g.away_goals}.${g.away_behinds} (${g.away_score})`}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="relative bg-oval text-white py-14 sm:py-20 overflow-hidden">
      <svg className="absolute inset-0 w-full h-full opacity-20" preserveAspectRatio="none" viewBox="0 0 400 200" aria-hidden="true">
        <ellipse cx="200" cy="100" rx="190" ry="90" fill="none" stroke="white" strokeWidth="2" />
        <line x1="200" y1="10" x2="200" y2="190" stroke="white" strokeWidth="1.5" />
        <circle cx="200" cy="100" r="30" fill="none" stroke="white" strokeWidth="1.5" />
      </svg>
      <div className="relative max-w-7xl mx-auto px-4 sm:px-8 lg:px-10 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.25em] text-nightgame mb-3">
          Season 2026: done and dusted
        </p>
        <h2 className="font-display text-4xl sm:text-5xl mb-4">Brisbane Lions, premiers.</h2>
        <p className="text-white/80 mb-8">14.12 (96) def. Fremantle 12.17 (89) &middot; 26 September 2026</p>
        <div className="bg-white/10 backdrop-blur-sm rounded-xl p-6 inline-block mb-6">
          <p className="text-xs text-white/60 mb-3 uppercase tracking-wider">Next season starts in (estimated)</p>
          <Countdown targetDate={NEXT_SEASON_ESTIMATE} />
        </div>
        <div>
          <button
            onClick={() => navigate('/ask?q=' + encodeURIComponent('How did the 2026 season go for my team?'))}
            className="btn-primary"
          >
            Ask about the 2026 season
          </button>
        </div>
      </div>
    </section>
  );
};

export default SundayArvo;
