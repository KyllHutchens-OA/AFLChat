import { useState, useCallback, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTeam } from '../contexts/TeamContext';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5001';

interface FunStat {
  headline: string;
  detail: string;
  stat_type: string;
}

const TEAMS = [
  { name: 'Adelaide', abbreviation: 'ADE', nickname: 'Crows', primaryColor: '#002B5C', secondaryColor: '#FFD200' },
  { name: 'Brisbane Lions', abbreviation: 'BRI', nickname: 'Lions', primaryColor: '#A30046', secondaryColor: '#0039A6' },
  { name: 'Carlton', abbreviation: 'CAR', nickname: 'Blues', primaryColor: '#001A36', secondaryColor: '#FFFFFF' },
  { name: 'Collingwood', abbreviation: 'COL', nickname: 'Magpies', primaryColor: '#000000', secondaryColor: '#FFFFFF' },
  { name: 'Essendon', abbreviation: 'ESS', nickname: 'Bombers', primaryColor: '#000000', secondaryColor: '#CC2031' },
  { name: 'Fremantle', abbreviation: 'FRE', nickname: 'Dockers', primaryColor: '#2A0D45', secondaryColor: '#FFFFFF' },
  { name: 'Geelong', abbreviation: 'GEE', nickname: 'Cats', primaryColor: '#001F3D', secondaryColor: '#FFFFFF' },
  { name: 'Gold Coast', abbreviation: 'GCS', nickname: 'Suns', primaryColor: '#D4001A', secondaryColor: '#FFD200' },
  { name: 'Greater Western Sydney', abbreviation: 'GWS', nickname: 'Giants', primaryColor: '#F47920', secondaryColor: '#4A4946' },
  { name: 'Hawthorn', abbreviation: 'HAW', nickname: 'Hawks', primaryColor: '#4D2004', secondaryColor: '#FBBF15' },
  { name: 'Melbourne', abbreviation: 'MEL', nickname: 'Demons', primaryColor: '#0F1131', secondaryColor: '#CC2031' },
  { name: 'North Melbourne', abbreviation: 'NOR', nickname: 'Kangaroos', primaryColor: '#003D8E', secondaryColor: '#FFFFFF' },
  { name: 'Port Adelaide', abbreviation: 'POR', nickname: 'Power', primaryColor: '#008AAB', secondaryColor: '#000000' },
  { name: 'Richmond', abbreviation: 'RIC', nickname: 'Tigers', primaryColor: '#000000', secondaryColor: '#FED102' },
  { name: 'St Kilda', abbreviation: 'STK', nickname: 'Saints', primaryColor: '#ED1C24', secondaryColor: '#000000' },
  { name: 'Sydney', abbreviation: 'SYD', nickname: 'Swans', primaryColor: '#ED171F', secondaryColor: '#FFFFFF' },
  { name: 'West Coast', abbreviation: 'WCE', nickname: 'Eagles', primaryColor: '#002B5C', secondaryColor: '#F2A900' },
  { name: 'Western Bulldogs', abbreviation: 'WBD', nickname: 'Bulldogs', primaryColor: '#014896', secondaryColor: '#CC2031' },
];

const TeamSelection = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setTeam } = useTeam();
  const [selectedTeam, setSelectedTeam] = useState<typeof TEAMS[0] | null>(null);
  const [funStats, setFunStats] = useState<FunStat[]>([]);
  const [loading, setLoading] = useState(false);
  const [showStats, setShowStats] = useState(false);
  const [copied, setCopied] = useState(false);

  // Auto-select team from shared URL (?team=Richmond)
  useEffect(() => {
    const teamParam = searchParams.get('team');
    if (teamParam && !selectedTeam) {
      const match = TEAMS.find(t => t.name.toLowerCase() === teamParam.toLowerCase());
      if (match) {
        handleSelect(match);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const getShareUrl = useCallback(() => {
    const base = window.location.origin;
    return `${base}/welcome?team=${encodeURIComponent(selectedTeam?.name || '')}`;
  }, [selectedTeam]);

  const handleShare = async () => {
    const url = getShareUrl();

    if (navigator.share) {
      try {
        await navigator.share({ title: `${selectedTeam?.name} — Footy-NAC`, url });
        return;
      } catch { /* user cancelled or unsupported, fall through to clipboard */ }
    }

    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard failed silently */ }
  };

  const handleSelect = async (team: typeof TEAMS[0]) => {
    setSelectedTeam(team);
    setTeam(team.name);
    setLoading(true);
    setShowStats(false);

    try {
      const res = await fetch(`${BACKEND_URL}/api/teams/${encodeURIComponent(team.name)}/fun-stats`);
      const data = res.ok ? await res.json() : [];
      setFunStats(data);
    } catch {
      setFunStats([]);
    } finally {
      setLoading(false);
      setShowStats(true);
    }
  };

  const handleContinue = () => {
    navigate('/aflagent');
  };

  // --- Loading / Fun Stats Reveal screen ---
  if (selectedTeam && (loading || showStats)) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12">
        {/* Team badge */}
        <div
          className="w-20 h-20 rounded-full flex items-center justify-center text-white font-bold text-xl shadow-lg mb-6 animate-scale-in"
          style={{ backgroundColor: selectedTeam.primaryColor }}
        >
          {selectedTeam.abbreviation}
        </div>

        {loading ? (
          <>
            <h2 className="text-2xl font-semibold text-afl-warm-900 mb-3 animate-fade-in">
              {selectedTeam.nickname}
            </h2>
            <div className="flex items-center gap-3 text-afl-warm-400 animate-fade-in">
              <div className="w-5 h-5 border-2 border-afl-warm-300 border-t-afl-accent rounded-full animate-spin" />
              <span className="text-sm">Pulling up some facts...</span>
            </div>
          </>
        ) : (
          <>
            <h2 className="text-2xl font-semibold text-afl-warm-900 mb-2 animate-fade-in">
              Did you know?
            </h2>
            <p className="text-sm text-afl-warm-500 mb-8 animate-fade-in">
              {selectedTeam.name}
            </p>

            {/* Fun stat cards */}
            <div className="w-full max-w-md space-y-4 mb-8">
              {funStats.map((stat, i) => (
                <div
                  key={stat.stat_type}
                  className="bg-white rounded-xl p-5 shadow-apple border border-afl-warm-100 animate-slide-in-right"
                  style={{ animationDelay: `${i * 150}ms`, animationFillMode: 'both' }}
                >
                  <p className="font-semibold text-afl-warm-900 leading-snug">{stat.headline}</p>
                  <p className="text-sm text-afl-warm-500 mt-1.5">{stat.detail}</p>
                </div>
              ))}
              {funStats.length === 0 && (
                <p className="text-center text-afl-warm-400 text-sm">No stats available yet</p>
              )}
            </div>

            {/* Share + Continue */}
            <div
              className="flex items-center gap-3 animate-fade-in"
              style={{ animationDelay: `${funStats.length * 150 + 200}ms`, animationFillMode: 'both' }}
            >
              {funStats.length > 0 && (
                <button
                  onClick={handleShare}
                  className="px-5 py-3 rounded-xl border border-afl-warm-200 text-afl-warm-600
                             hover:bg-afl-warm-100 transition-all duration-200 text-sm font-medium
                             flex items-center gap-2"
                >
                  {copied ? (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Copied!
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                      </svg>
                      Share
                    </>
                  )}
                </button>
              )}
              <button
                onClick={handleContinue}
                className="btn-apple-primary px-8 py-3 text-base flex items-center gap-2"
              >
                What else can you tell me?
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </button>
            </div>

            {/* Pick different team */}
            <button
              onClick={() => { setSelectedTeam(null); setShowStats(false); setCopied(false); }}
              className="mt-5 text-sm text-afl-warm-400 hover:text-afl-warm-700 transition-colors"
            >
              Pick a different team
            </button>
          </>
        )}
      </div>
    );
  }

  // --- Team grid ---
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12">
      <h1 className="text-3xl font-semibold text-afl-warm-900 mb-2">Welcome to Footy-NAC</h1>
      <p className="text-afl-warm-500 mb-10">Pick your team</p>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-4 max-w-4xl w-full">
        {TEAMS.map((team) => (
          <button
            key={team.name}
            onClick={() => handleSelect(team)}
            className="flex flex-col items-center gap-2 p-4 rounded-lg hover:bg-afl-warm-100 transition-colors"
          >
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center text-white font-bold text-sm shadow-md"
              style={{ backgroundColor: team.primaryColor }}
            >
              {team.abbreviation}
            </div>
            <span className="text-sm font-medium text-afl-warm-900">{team.name}</span>
            <span className="text-xs text-afl-warm-500">{team.nickname}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default TeamSelection;
