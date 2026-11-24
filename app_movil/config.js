// Dirección del servidor Django que entrega la API de la app (sin "/" al final).
//
// - Publicada junto a la web (Railway, o `runserver` en /app/): la API está en la misma dirección.
// - Abierta con `python -m http.server 5510` (pruebas): la API está en el puerto 8000 del mismo equipo.
// - Si la app se publica en otro dominio, reemplaza la línea por la dirección de la web,
//   por ejemplo: window.ADAPT_API_URL = 'https://adaptacademy.up.railway.app';
window.ADAPT_API_URL = location.port === '5510'
  ? location.protocol + '//' + location.hostname + ':8000'
  : location.origin;
