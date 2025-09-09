// 🚀 SERVICE WORKER - NEXUS AXION API REST
// Fichier: sw.js
// Usage: À placer à la racine avec index.html

const SW_VERSION = 'v1.0';
const API_PREFIX = '/api/';

// 🗄️ Base de données simulée
let usersDB = [
    { id: 1, name: 'Alice Johnson', email: 'alice@test.com', age: 28, created: '2024-01-15T10:30:00Z' },
    { id: 2, name: 'Bob Smith', email: 'bob@test.com', age: 35, created: '2024-01-16T14:20:00Z' },
    { id: 3, name: 'Carol Davis', email: 'carol@test.com', age: 42, created: '2024-01-17T09:15:00Z' },
    { id: 4, name: 'David Wilson', email: 'david@test.com', age: 29, created: '2024-01-18T16:45:00Z' },
    { id: 5, name: 'Eva Martinez', email: 'eva@test.com', age: 31, created: '2024-01-19T11:30:00Z' }
];

// 🔥 ESSENCE server!() - Interception HTTP
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);
    
    // Route les requêtes API
    if (url.pathname.startsWith(API_PREFIX)) {
        event.respondWith(handleAPIRequest(event.request));
        return;
    }
    
    // Traite les autres requêtes normalement
    event.respondWith(fetch(event.request));
});

// 🧠 ESSENCE api!() - Routing REST
async function handleAPIRequest(request) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;
    
    console.log(`[SW] ${method} ${path}`);
    
    try {
        // Parse route: /api/resource/id
        const pathParts = path.split('/').filter(p => p);
        const resource = pathParts[1]; // 'users'
        const id = pathParts[2] ? parseInt(pathParts[2]) : null;
        
        if (resource === 'users') {
            return await handleUsersAPI(method, id, request);
        }
        
        return jsonResponse({ 
            error: 'Resource not found',
            available_endpoints: ['/api/users', '/api/users/{id}']
        }, 404);
        
    } catch (error) {
        console.error('[SW] API Error:', error);
        return jsonResponse({ 
            error: 'Internal server error',
            message: error.message,
            timestamp: new Date().toISOString()
        }, 500);
    }
}

// 🗄️ ESSENCE database!() - CRUD Operations
async function handleUsersAPI(method, id, request) {
    switch (method) {
        case 'GET':
            if (id) {
                // GET /api/users/{id}
                const user = usersDB.find(u => u.id === id);
                return user ? 
                    jsonResponse({ 
                        status: 'success', 
                        data: user,
                        timestamp: new Date().toISOString()
                    }) :
                    jsonResponse({ 
                        error: 'User not found',
                        message: `No user with ID ${id}`
                    }, 404);
            } else {
                // GET /api/users
                return jsonResponse({ 
                    status: 'success',
                    data: usersDB,
                    count: usersDB.length,
                    timestamp: new Date().toISOString(),
                    meta: {
                        total: usersDB.length,
                        endpoint: '/api/users',
                        methods: ['GET', 'POST']
                    }
                });
            }
            
        case 'POST':
            // POST /api/users - Créer utilisateur
            try {
                const userData = await request.json();
                
                // Validation basique
                if (!userData.name || !userData.email || !userData.age) {
                    return jsonResponse({ 
                        error: 'Missing required fields',
                        required: ['name', 'email', 'age'],
                        received: userData
                    }, 400);
                }
                
                // Vérifier email unique
                const existingUser = usersDB.find(u => u.email === userData.email);
                if (existingUser) {
                    return jsonResponse({ 
                        error: 'Email already exists',
                        message: `User with email ${userData.email} already exists`
                    }, 409);
                }
                
                const newUser = {
                    id: Math.max(...usersDB.map(u => u.id), 0) + 1,
                    name: userData.name,
                    email: userData.email,
                    age: parseInt(userData.age),
                    created: new Date().toISOString()
                };
                
                usersDB.push(newUser);
                
                return jsonResponse({ 
                    status: 'success',
                    message: 'User created successfully',
                    data: newUser,
                    timestamp: new Date().toISOString()
                }, 201);
                
            } catch (error) {
                return jsonResponse({ 
                    error: 'Invalid JSON data',
                    message: error.message
                }, 400);
            }
            
        case 'PUT':
            // PUT /api/users/{id} - Mettre à jour
            if (!id) {
                return jsonResponse({ 
                    error: 'User ID required for update',
                    usage: 'PUT /api/users/{id}'
                }, 400);
            }
            
            try {
                const userIndex = usersDB.findIndex(u => u.id === id);
                if (userIndex === -1) {
                    return jsonResponse({ 
                        error: 'User not found',
                        message: `No user with ID ${id}`
                    }, 404);
                }
                
                const updateData = await request.json();
                const updatedUser = {
                    ...usersDB[userIndex],
                    ...updateData,
                    id: id, // Empêcher changement d'ID
                    updated: new Date().toISOString()
                };
                
                usersDB[userIndex] = updatedUser;
                
                return jsonResponse({ 
                    status: 'success',
                    message: 'User updated successfully',
                    data: updatedUser,
                    timestamp: new Date().toISOString()
                });
                
            } catch (error) {
                return jsonResponse({ 
                    error: 'Invalid JSON data',
                    message: error.message
                }, 400);
            }
            
        case 'DELETE':
            // DELETE /api/users/{id} - Supprimer
            if (!id) {
                return jsonResponse({ 
                    error: 'User ID required for deletion',
                    usage: 'DELETE /api/users/{id}'
                }, 400);
            }
            
            const deleteIndex = usersDB.findIndex(u => u.id === id);
            if (deleteIndex === -1) {
                return jsonResponse({ 
                    error: 'User not found',
                    message: `No user with ID ${id}`
                }, 404);
            }
            
            const deletedUser = usersDB.splice(deleteIndex, 1)[0];
            
            return jsonResponse({ 
                status: 'success',
                message: 'User deleted successfully',
                data: deletedUser,
                remaining_users: usersDB.length,
                timestamp: new Date().toISOString()
            });
            
        default:
            return jsonResponse({ 
                error: 'Method not allowed',
                allowed_methods: ['GET', 'POST', 'PUT', 'DELETE'],
                received_method: method
            }, 405);
    }
}

// 📡 Helper function pour réponses JSON
function jsonResponse(data, status = 200) {
    return new Response(JSON.stringify(data, null, 2), {
        status: status,
        headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Allow-Credentials': 'true',
            'X-Powered-By': 'NEXUS-AXION-ServiceWorker',
            'X-API-Version': SW_VERSION
        }
    });
}

// 🌐 Gérer CORS preflight requests
self.addEventListener('fetch', event => {
    if (event.request.method === 'OPTIONS') {
        event.respondWith(new Response(null, {
            status: 200,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                'Access-Control-Max-Age': '86400'
            }
        }));
    }
});

// 🔧 Event listeners pour cycle de vie
self.addEventListener('install', event => {
    console.log('[SW] Service Worker installing...');
    self.skipWaiting(); // Active immédiatement
});

self.addEventListener('activate', event => {
    console.log('[SW] Service Worker activated');
    event.waitUntil(self.clients.claim());
});

// 📊 Endpoint de statut du Service Worker
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);
    
    if (url.pathname === '/api/status') {
        event.respondWith(jsonResponse({
            status: 'online',
            message: 'NEXUS AXION Service Worker API active',
            version: SW_VERSION,
            endpoints: [
                'GET /api/users',
                'POST /api/users',
                'GET /api/users/{id}',
                'PUT /api/users/{id}',
                'DELETE /api/users/{id}',
                'GET /api/status'
            ],
            database: {
                users_count: usersDB.length,
                last_modified: new Date().toISOString()
            },
            timestamp: new Date().toISOString()
        }));
    }
});

console.log('🌌 NEXUS AXION Service Worker - API REST Server Ready');
console.log('📡 Endpoints disponibles: /api/users, /api/status');
console.log('🔒 CORS activé pour requêtes externes');