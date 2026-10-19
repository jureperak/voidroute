// Links Sonarr and Radarr to Seerr through Seerr's own API. Runs inside the
// Seerr container during deploy. Idempotent: apps already linked are skipped.
//
// Env: SEERR_API_KEY, SONARR_API_KEY, RADARR_API_KEY

const BASE = 'http://localhost:5055/api/v1';
const SEERR_KEY = process.env.SEERR_API_KEY;

const APPS = [
  {
    type: 'sonarr',
    name: 'Sonarr',
    hostname: 'sonarr',
    port: 8989,
    apiKey: process.env.SONARR_API_KEY,
    profile: 'My series profile',
    root: '/data/media/series',
  },
  {
    type: 'radarr',
    name: 'Radarr',
    hostname: 'radarr',
    port: 7878,
    apiKey: process.env.RADARR_API_KEY,
    profile: 'My movies profile',
    root: '/data/media/movies',
  },
];

async function call(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'X-API-Key': SEERR_KEY, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`${method} ${path} -> ${res.status}: ${text.slice(0, 300)}`);
  }
  return text ? JSON.parse(text) : null;
}

async function waitForSeerr() {
  for (let i = 0; i < 60; i++) {
    try {
      await call('GET', '/status');
      return;
    } catch (e) {
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
  throw new Error('Seerr API is not reachable');
}

async function linkApp(app) {
  if (!app.apiKey) throw new Error(`secret for ${app.name} is not set`);

  const existing = await call('GET', `/settings/${app.type}`);
  if (existing.some((s) => s.hostname === app.hostname)) {
    console.log(`${app.name}: already linked`);
    return;
  }

  const test = await call('POST', `/settings/${app.type}/test`, {
    hostname: app.hostname,
    port: app.port,
    apiKey: app.apiKey,
    useSsl: false,
    baseUrl: '',
  });

  const profile = test.profiles.find((p) => p.name === app.profile);
  if (!profile) throw new Error(`${app.name}: profile "${app.profile}" not found`);
  const folder = test.rootFolders.find((f) => f.path === app.root);
  if (!folder) throw new Error(`${app.name}: root folder ${app.root} not found`);

  const body = {
    name: app.name,
    hostname: app.hostname,
    port: app.port,
    apiKey: app.apiKey,
    useSsl: false,
    baseUrl: '',
    activeProfileId: profile.id,
    activeProfileName: profile.name,
    activeDirectory: folder.path,
    tags: [],
    is4k: false,
    isDefault: true,
    externalUrl: '',
    syncEnabled: false,
    preventSearch: false,
    tagRequests: false,
    overrideRule: [],
  };

  if (app.type === 'sonarr') {
    Object.assign(body, {
      seriesType: 'standard',
      animeSeriesType: 'standard',
      enableSeasonFolders: true,
      monitorNewItems: 'all',
    });
    if (test.languageProfiles && test.languageProfiles[0]) {
      body.activeLanguageProfileId = test.languageProfiles[0].id;
    }
  } else {
    body.minimumAvailability = 'released';
  }

  await call('POST', `/settings/${app.type}`, body);
  console.log(`${app.name}: linked to Seerr`);
}

(async () => {
  if (!SEERR_KEY) throw new Error('SEERR_API_KEY is not set');
  await waitForSeerr();
  for (const app of APPS) {
    await linkApp(app);
  }
})().catch((e) => {
  console.error(`::error::${e.message}`);
  process.exit(1);
});
