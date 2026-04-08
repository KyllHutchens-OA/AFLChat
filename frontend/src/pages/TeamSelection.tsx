import { useNavigate } from 'react-router-dom';
import { useTeam } from '../contexts/TeamContext';

const TEAMS = [
  { name: 'Adelaide', abbreviation: 'ADE', nickname: 'Crows', primaryColor: '#002B5C', secondaryColor: '#FFD200' },
  { name: 'Brisbane Lions', abbreviation: 'BRI', nickname: 'Lions', primaryColor: '#A30046', secondaryColor: '#0039A6' },
  { name: 'Carlton', abbreviation: 'CAR', nickname: 'Blues', primaryColor: '#001A36', secondaryColor: '#FFFFFF' },
  { name: 'Collingwood', abbreviation: 'COL', nickname: 'Magpies', primaryColor: '#000000', secondaryColor: '#FFFFFF' },
  { name: 'Essendon', abbreviation: 'ESS', nickname: 'Bombers', primaryColor: '#000000', secondaryColor: '#CC2031' },
  { name: 'Fremantle', abbreviation: 'FRE', nickname: 'Dockers', primaryColor: '#2A0D45', secondaryColor: '#FFFFFF' },
  { name: 'Geelong', abbreviation: 'GEE', nickname: 'Cats', primaryColor: '#001F3D', secondaryColor: '#FFFFFF' },
  { name: 'Gold Coast', abbreviation: 'GCS', nickname: 'Suns', primaryColor: '#D4001A', secondaryColor: '#FFD200' },
  { name: 'GWS Giants', abbreviation: 'GWS', nickname: 'Giants', primaryColor: '#F47920', secondaryColor: '#4A4946' },
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
  const { setTeam } = useTeam();

  const handleSelect = (teamName: string) => {
    setTeam(teamName);
    navigate('/aflagent');
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12" style={{ backgroundColor: '#FAF7F2' }}>
      <h1 className="text-3xl font-semibold text-gray-900 mb-2">Welcome to Footy-NAC</h1>
      <p className="text-gray-500 mb-10">Pick your team</p>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-4 max-w-4xl w-full">
        {TEAMS.map((team) => (
          <button
            key={team.name}
            onClick={() => handleSelect(team.name)}
            className="flex flex-col items-center gap-2 p-4 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center text-white font-bold text-sm shadow-md"
              style={{ backgroundColor: team.primaryColor }}
            >
              {team.abbreviation}
            </div>
            <span className="text-sm font-medium text-gray-900">{team.name}</span>
            <span className="text-xs text-gray-500">{team.nickname}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default TeamSelection;
