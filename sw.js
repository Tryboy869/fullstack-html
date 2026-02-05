// P2P Reality DB - Service Worker
// Intercepte les requêtes HTTP et les traite avec IndexedDB

const CACHE_NAME = 'p2p-reality-v1';
const DB_NAME = 'p2p-reality-db';
const DB_VERSION = 1;

// =================================================================
// INDEXEDDB HELPERS
// =================================================================

function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result);
        
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains('collections')) {
                const store = db.createObjectStore('collections', { 
                    keyPath: 'id', 
                    autoIncrement: true 
                });
                store.createIndex('collection', 'collection', { unique: false });
                store.createIndex('timestamp', 'timestamp', { unique: false });
            }
        };
    });
}

async function insertDocument(collection, data) {
    const db = await openDB();
    const tx = db.transaction(['collections'], 'readwrite');
    const store = tx.objectStore('collections');
    
    const document = {
        collection,
        data,
        timestamp: Date.now(),
        size: new Blob([JSON.stringify(data)]).size
    };
    
    return new Promise((resolve, reject) => {
        const request = store.add(document);
        request.onsuccess = () => resolve({ id: request.result, ...document });
        request.onerror = () => reject(request.error);
    });
}

async function queryDocuments(collection) {
    const db = await openDB();
    const tx = db.transaction(['collections'], 'readonly');
    const store = tx.objectStore('collections');
    const index = store.index('collection');
    
    return new Promise((resolve, reject) => {
        const request = index.getAll(collection);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function updateDocument(id, updates) {
    const db = await openDB();
    const tx = db.transaction(['collections'], 'readwrite');
    const store = tx.objectStore('collections');
    
    return new Promise((resolve, reject) => {
        const getRequest = store.get(parseInt(id));
        
        getRequest.onsuccess = () => {
            const document = getRequest.result;
            if (!document) {
                reject(new Error('Document not found'));
                return;
            }
            
            document.data = { ...document.data, ...updates };
            document.timestamp = Date.now();
            
            const putRequest = store.put(document);
            putRequest.onsuccess = () => resolve(document);
            putRequest.onerror = () => reject(putRequest.error);
        };
        getRequest.onerror = () => reject(getRequest.error);
    });
}

async function deleteDocument(id) {
    const db = await openDB();
    const tx = db.transaction(['collections'], 'readwrite');
    const store = tx.objectStore('collections');
    
    return new Promise((resolve, reject) => {
        const request = store.delete(parseInt(id));
        request.onsuccess = () => resolve({ success: true });
        request.onerror = () => reject(request.error);
    });
}

async function getCollections() {
    const db = await openDB();
    const tx = db.transaction(['collections'], 'readonly');
    const store = tx.objectStore('collections');
    
    return new Promise((resolve, reject) => {
        const request = store.getAll();
        request.onsuccess = () => {
            const docs = request.result;
            const collectionsMap = new Map();
            
            docs.forEach(doc => {
                if (!collectionsMap.has(doc.collection)) {
                    collectionsMap.set(doc.collection, { count: 0, size: 0 });
                }
                const stats = collectionsMap.get(doc.collection);
                stats.count++;
                stats.size += doc.size;
            });
            
            const collections = Array.from(collectionsMap.entries()).map(([name, stats]) => ({
                name,
                ...stats
            }));
            
            resolve(collections);
        };
        request.onerror = () => reject(request.error);
    });
}

// =================================================================
// API ROUTER
// =================================================================

async function handleAPIRequest(request) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;
    
    console.log(`[SW] ${method} ${path}`);
    
    try {
        // GET /api/collections
        if (method === 'GET' && path === '/api/collections') {
            const collections = await getCollections();
            return jsonResponse({ success: true, data: collections });
        }
        
        // GET /api/:collection
        if (method === 'GET' && path.startsWith('/api/') && path.split('/').length === 3) {
            const collection = path.split('/')[2];
            const docs = await queryDocuments(collection);
            return jsonResponse({ success: true, data: docs });
        }
        
        // POST /api/:collection
        if (method === 'POST' && path.startsWith('/api/') && path.split('/').length === 3) {
            const collection = path.split('/')[2];
            const body = await request.json();
            const result = await insertDocument(collection, body);
            return jsonResponse({ success: true, data: result });
        }
        
        // PUT /api/:collection/:id
        if (method === 'PUT' && path.startsWith('/api/') && path.split('/').length === 4) {
            const [, , collection, id] = path.split('/');
            const body = await request.json();
            const result = await updateDocument(id, body);
            return jsonResponse({ success: true, data: result });
        }
        
        // DELETE /api/:collection/:id
        if (method === 'DELETE' && path.startsWith('/api/') && path.split('/').length === 4) {
            const [, , collection, id] = path.split('/');
            const result = await deleteDocument(id);
            return jsonResponse({ success: true, data: result });
        }
        
        // Not found
        return jsonResponse({ success: false, error: 'Route not found' }, 404);
        
    } catch (error) {
        console.error('[SW] Error:', error);
        return jsonResponse({ success: false, error: error.message }, 500);
    }
}

function jsonResponse(data, status = 200) {
    return new Response(JSON.stringify(data), {
        status,
        headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
    });
}

// =================================================================
// SERVICE WORKER EVENT HANDLERS
// =================================================================

self.addEventListener('install', (event) => {
    console.log('[SW] Installing...');
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    console.log('[SW] Activating...');
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    // Handle CORS preflight
    if (event.request.method === 'OPTIONS') {
        event.respondWith(
            new Response(null, {
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                }
            })
        );
        return;
    }
    
    // Intercept API requests
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(handleAPIRequest(event.request));
        return;
    }
    
    // Pass through other requests
    event.respondWith(fetch(event.request));
});
