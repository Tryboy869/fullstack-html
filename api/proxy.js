// CE FICHIER DOIT ÊTRE DANS UN DOSSIER "api" À LA RACINE DU PROJET
// Chemin correct : /api/proxy.js

export default async function handler(request) {
  // Récupère l'URL cible depuis les paramètres de la requête (ex: ?url=https://...)
  const targetUrl = request.nextUrl.searchParams.get('url');

  if (!targetUrl) {
    return new Response('Le paramètre "url" est manquant.', { status: 400 });
  }

  try {
    // Fait un appel direct à l'API externe depuis le serveur de Vercel
    const apiResponse = await fetch(targetUrl, {
      headers: {
        // Transfère certains en-têtes importants si nécessaire
        'User-Agent': 'Vercel-Proxy/1.0',
      },
    });

    // Récupère la réponse de l'API (texte, json, etc.)
    const data = await apiResponse.text();

    // Crée une nouvelle réponse pour le client
    const response = new Response(data, {
      status: apiResponse.status,
      headers: {
        // Copie les en-têtes de l'API d'origine, comme 'Content-Type'
        'Content-Type': apiResponse.headers.get('Content-Type') || 'application/json',
        // Ajoute l'en-tête CORS crucial pour autoriser votre site à lire la réponse
        'Access-Control-Allow-Origin': '*',
      },
    });

    return response;

  } catch (error) {
    return new Response(`Erreur du proxy: ${error.message}`, { status: 500 });
  }
}

// Configuration Vercel Edge (optionnel mais recommandé pour la performance)
export const config = {
  runtime: 'edge',
};
