// Service Worker — ALERTRAN SGD
const CACHE = 'alertran-v11';

// Assets estáticos que se cachean en la instalación
const PRECACHE = [
  '/',
  '/static/style.css',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/manifest.json',
];

// ── Install: precachear assets ────────────────────────────────────────────────
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

// ── Activate: limpiar caches viejos ──────────────────────────────────────────
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── Fetch: estrategia según tipo de recurso ───────────────────────────────────
self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  // WebSockets y peticiones cross-origin: ignorar
  if (url.protocol === 'ws:' || url.protocol === 'wss:') return;
  if (url.origin !== self.location.origin) return;

  // API calls (/desviaciones, /viajes, /jobs, /config, /ws): network-first
  const API_PATHS = ['/desviaciones', '/viajes', '/jobs', '/config', '/ws'];
  if (API_PATHS.some(p => url.pathname.startsWith(p))) {
    e.respondWith(networkFirst(request));
    return;
  }

  // Assets estáticos (/static/): cache-first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(cacheFirst(request));
    return;
  }

  // Navegación (HTML/SPA): network-first, fallback a cache
  e.respondWith(networkFirst(request));
});

// ── Estrategias ───────────────────────────────────────────────────────────────
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(CACHE);
    cache.put(request, response.clone());
  }
  return response;
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok && request.method === 'GET') {
      const cache = await caches.open(CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    // Offline fallback para navegación
    if (request.mode === 'navigate') {
      return caches.match('/');
    }
    return new Response('Sin conexión', { status: 503 });
  }
}
