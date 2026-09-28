// AFL club metadata. Kept for Part 2 club theming (was the /welcome team grid).
export interface Club {
  name: string;
  abbreviation: string;
  nickname: string;
  primaryColor: string;
  secondaryColor: string;
}

export const CLUBS: Club[] = [
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
