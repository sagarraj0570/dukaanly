export interface PatnaPlace {
  id: string
  name: string
  area: string
  description: string
  keywords: string[]
  coords: {
    latitude: number
    longitude: number
  }
}

export const PATNA_PLACES: PatnaPlace[] = [
  // Central Patna
  {
    id: 'boring-road',
    name: 'Boring Road / Boring Canal Rd',
    area: 'Central Patna',
    description: 'Near AN College, Panchmukhi Mandir & Alpana Market',
    keywords: ['boring', 'canal', 'an college', 'panchmukhi', 'alpana', 'central'],
    coords: { latitude: 25.6144, longitude: 85.1158 },
  },
  {
    id: 'sk-puri',
    name: 'Sri Krishna Puri (SK Puri)',
    area: 'Central Patna',
    description: 'Near Children Park, Sahdeo Mahto Marg & Basawan Park',
    keywords: ['sk puri', 'sri krishna puri', 'children park', 'sahdeo', 'central'],
    coords: { latitude: 25.616, longitude: 85.111 },
  },
  {
    id: 'patliputra-colony',
    name: 'Patliputra Colony',
    area: 'Central Patna',
    description: 'Near Pataliputra Golambar, Rajiv Nagar & Alpana Market',
    keywords: ['patliputra', 'pataliputra', 'colony', 'golambar', 'rajiv nagar'],
    coords: { latitude: 25.6265, longitude: 85.113 },
  },
  {
    id: 'nageshwar-colony',
    name: 'Nageshwar Colony',
    area: 'Central Patna',
    description: 'Near Boring Canal Road & Budha Colony',
    keywords: ['nageshwar', 'budha colony', 'buddha', 'canal'],
    coords: { latitude: 25.611, longitude: 85.122 },
  },
  {
    id: 'kidwaipuri',
    name: 'Kidwaipuri / Anandpuri',
    area: 'Central Patna',
    description: 'Near Income Tax Golambar, High Court & Vidyapati Marg',
    keywords: ['kidwaipuri', 'anandpuri', 'income tax', 'high court', 'vidyapati'],
    coords: { latitude: 25.612, longitude: 85.129 },
  },
  {
    id: 'r-block',
    name: 'R-Block / Veerchand Patel Path',
    area: 'Central Patna',
    description: 'Near Bihar Vidhan Sabha, Secretariat & GPO',
    keywords: ['r block', 'r-block', 'veerchand', 'patel path', 'secretariat', 'vidhan sabha'],
    coords: { latitude: 25.606, longitude: 85.132 },
  },

  // East & Old Patna
  {
    id: 'rajendra-nagar',
    name: 'Rajendra Nagar Market',
    area: 'East Patna',
    description: 'Near Rajendra Nagar Terminal, Bazar Samiti & Dinkar Golambar',
    keywords: ['rajendra nagar', 'terminal', 'bazar samiti', 'dinkar', 'east'],
    coords: { latitude: 25.6022, longitude: 85.1633 },
  },
  {
    id: 'kadamkuan',
    name: 'Kadamkuan / Sahitya Sammelan',
    area: 'East Patna',
    description: 'Near Hindi Sahitya Sammelan, Nala Road & Thakurbari',
    keywords: ['kadamkuan', 'sahitya sammelan', 'nala road', 'thakurbari'],
    coords: { latitude: 25.609, longitude: 85.155 },
  },
  {
    id: 'patna-junction',
    name: 'Patna Junction / Fraser Road',
    area: 'Central Patna',
    description: 'Near Dak Bungalow Chowk, Maurya Lok Complex & Railway Station',
    keywords: ['patna junction', 'station', 'fraser road', 'dak bungalow', 'maurya lok', 'railway'],
    coords: { latitude: 25.6025, longitude: 85.1375 },
  },
  {
    id: 'exhibition-road',
    name: 'Exhibition Road',
    area: 'Central Patna',
    description: 'Near Big Bazaar, Hotel Maurya & Gandhi Maidan South',
    keywords: ['exhibition road', 'hotel maurya', 'big bazaar', 'south'],
    coords: { latitude: 25.606, longitude: 85.143 },
  },
  {
    id: 'gandhi-maidan',
    name: 'Gandhi Maidan',
    area: 'North-Central Patna',
    description: 'Near Kargil Chowk, Mona Cinema, Golghar & Biscomaun Bhawan',
    keywords: ['gandhi maidan', 'golghar', 'kargil chowk', 'biscomaun', 'mona cinema'],
    coords: { latitude: 25.6185, longitude: 85.144 },
  },
  {
    id: 'ashok-rajpath',
    name: 'Ashok Rajpath / PMCH',
    area: 'North-East Patna',
    description: 'Near Patna Medical College (PMCH), Patna University & Science College',
    keywords: ['ashok rajpath', 'pmch', 'patna university', 'science college', 'medical'],
    coords: { latitude: 25.621, longitude: 85.158 },
  },
  {
    id: 'patna-city',
    name: 'Patna City / Chowk',
    area: 'East Patna',
    description: 'Near Takht Sri Harmandir Sahib (Gurudwara), Mangal Talab & Padri Ki Haveli',
    keywords: ['patna city', 'patna sahib', 'gurudwara', 'chowk', 'mangal talab', 'harmandir'],
    coords: { latitude: 25.594, longitude: 85.228 },
  },
  {
    id: 'agam-kuan',
    name: 'Agam Kuan / Zero Mile',
    area: 'East Patna',
    description: 'Near Historic Ashokan Well, NMCH Hospital & Transport Nagar',
    keywords: ['agam kuan', 'zero mile', 'nmch', 'transport nagar', 'ashoka'],
    coords: { latitude: 25.586, longitude: 85.196 },
  },
  {
    id: 'kumhrar',
    name: 'Kumhrar Archaeological Area',
    area: 'East Patna',
    description: 'Near Mauryan Palace Ruins, Sandalpur & Kankarbagh East',
    keywords: ['kumhrar', 'mauryan', 'sandalpur', 'ancient', 'heritage'],
    coords: { latitude: 25.598, longitude: 85.185 },
  },

  // South Patna
  {
    id: 'kankarbagh',
    name: 'Kankarbagh Main Road',
    area: 'South Patna',
    description: 'Near Tiwary Bechar, Auto Stand, Tempo Stand & Colony Market',
    keywords: ['kankarbagh', 'tiwary bechar', 'auto stand', 'tempo stand', 'south'],
    coords: { latitude: 25.5947, longitude: 85.1588 },
  },
  {
    id: 'hanuman-nagar',
    name: 'Hanuman Nagar / Doctor Colony',
    area: 'South Patna',
    description: 'Near Kankarbagh 90 Feet Road, Munna Chak & Lohia Nagar',
    keywords: ['hanuman nagar', 'doctor colony', '90 feet road', 'munna chak', 'lohia nagar'],
    coords: { latitude: 25.587, longitude: 85.168 },
  },
  {
    id: 'anisabad',
    name: 'Anisabad / Chitkohra',
    area: 'South Patna',
    description: 'Near Chitkohra Golambar, Police Colony & Phulwari Link Road',
    keywords: ['anisabad', 'chitkohra', 'police colony', 'golambar'],
    coords: { latitude: 25.586, longitude: 85.113 },
  },
  {
    id: 'gardanibagh',
    name: 'Gardanibagh',
    area: 'South Patna',
    description: 'Near Gardanibagh Stadium, Government Hospital & Chitkohra Bridge',
    keywords: ['gardanibagh', 'stadium', 'hospital', 'bridge'],
    coords: { latitude: 25.595, longitude: 85.125 },
  },
  {
    id: 'mithapur',
    name: 'Mithapur / Bus Stand Area',
    area: 'South Patna',
    description: 'Near Chandragupt Institute (CIMP), CNLU Law College & Farm Area',
    keywords: ['mithapur', 'bus stand', 'cimp', 'cnlu', 'law college'],
    coords: { latitude: 25.595, longitude: 85.138 },
  },
  {
    id: 'beur',
    name: 'Beur / Bypass Crossing',
    area: 'South Patna',
    description: 'Near Beur Jail Road & Patna New Bypass Connection',
    keywords: ['beur', 'jail road', 'bypass', 'south'],
    coords: { latitude: 25.568, longitude: 85.099 },
  },

  // West Patna & Greater Patna
  {
    id: 'bailey-road',
    name: 'Bailey Road / Raja Bazar',
    area: 'West Patna',
    description: 'Near Paras HMRI Hospital, Pillar 60, Sheikhpura & IGIMS',
    keywords: ['bailey road', 'raja bazar', 'paras', 'igims', 'sheikhpura', 'pillar 60', 'west'],
    coords: { latitude: 25.6083, longitude: 85.0892 },
  },
  {
    id: 'rukanpura',
    name: 'Rukanpura / Jagdeo Path',
    area: 'West Patna',
    description: 'Near DPS Patna, Jagdeo Path Golambar & Bailey Road flyover',
    keywords: ['rukanpura', 'jagdeo path', 'dps', 'flyover', 'west'],
    coords: { latitude: 25.6105, longitude: 85.068 },
  },
  {
    id: 'ashiana-nagar',
    name: 'Ashiana Nagar / Ram Nagri',
    area: 'West-North Patna',
    description: 'Near Ashiana-Digha Road, Passport Office & St. Michael School',
    keywords: ['ashiana nagar', 'ram nagri', 'passport office', 'st michael', 'digha road'],
    coords: { latitude: 25.623, longitude: 85.083 },
  },
  {
    id: 'gola-road',
    name: 'Gola Road (Bailey Road to Danapur)',
    area: 'West Patna',
    description: 'Popular residential & commercial shopping corridor connecting Bailey Road',
    keywords: ['gola road', 'gola', 'shopping', 'residential', 'west'],
    coords: { latitude: 25.615, longitude: 85.045 },
  },
  {
    id: 'saguna-more',
    name: 'Saguna More / Danapur Road',
    area: 'West Patna',
    description: 'Major junction connecting Danapur, Bailey Road & Khagaul',
    keywords: ['saguna more', 'saguna', 'junction', 'danapur road'],
    coords: { latitude: 25.618, longitude: 85.032 },
  },
  {
    id: 'danapur-cantt',
    name: 'Danapur Cantt & Danapur Station',
    area: 'Greater Patna',
    description: 'Near Army Cantonment, Danapur Railway Station & Bus Terminal',
    keywords: ['danapur', 'danapur cantt', 'cantt', 'danapur station', 'railway'],
    coords: { latitude: 25.632, longitude: 85.04 },
  },
  {
    id: 'khagaul',
    name: 'Khagaul / Phulwari Sharif',
    area: 'South-West Patna',
    description: 'Near Historic Khanqah Mujibia, Railway Colony & Phulwari Station',
    keywords: ['khagaul', 'phulwari', 'phulwari sharif', 'khanqah', 'railway colony'],
    coords: { latitude: 25.579, longitude: 85.045 },
  },
  {
    id: 'aiims-patna',
    name: 'AIIMS Patna (Phulwari Sharif)',
    area: 'South-West Patna',
    description: 'All India Institute of Medical Sciences campus & Walmi',
    keywords: ['aiims', 'aiims patna', 'walmi', 'hospital', 'medical sciences'],
    coords: { latitude: 25.561, longitude: 85.042 },
  },
  {
    id: 'digha',
    name: 'Digha / JP Ganga Path',
    area: 'North-West Patna',
    description: 'Near Digha-Sonpur Bridge, Ganga Marine Drive & Digha Ghat',
    keywords: ['digha', 'jp ganga path', 'marine drive', 'ganga', 'sonpur bridge'],
    coords: { latitude: 25.645, longitude: 85.095 },
  },
  {
    id: 'kurji',
    name: 'Kurji / Holy Family Hospital',
    area: 'North Patna',
    description: 'Near Kurji More, St. Xavier College & Ganga Riverfront',
    keywords: ['kurji', 'holy family', 'st xavier', 'riverfront'],
    coords: { latitude: 25.635, longitude: 85.105 },
  },
]

export const searchPatnaPlaces = (query: string): PatnaPlace[] => {
  const q = query.trim().toLowerCase()
  if (!q) return PATNA_PLACES

  const tokens = q.split(/\s+/).filter(Boolean)

  return PATNA_PLACES.filter((place) => {
    const haystack = [
      place.name.toLowerCase(),
      place.area.toLowerCase(),
      place.description.toLowerCase(),
      ...place.keywords,
    ].join(' ')

    // Every token in user query must appear somewhere in place info
    return tokens.every((token) => haystack.includes(token))
  })
}
