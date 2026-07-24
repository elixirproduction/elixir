const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 80;
const ROOT = __dirname;

const MIME = {
  '.html': 'text/html',
  '.js':   'application/javascript',
  '.mjs':  'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif':  'image/gif',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.woff': 'font/woff',
  '.woff2':'font/woff2',
  '.ttf':  'font/ttf',
  '.wasm': 'application/wasm',
  '.mp4':  'video/mp4',
  '.webm': 'video/webm',
  '.mp3':  'audio/mpeg',
  '.wav':  'audio/wav',
  '.json': 'application/json',
  '.webmanifest': 'application/manifest+json',
};

const server = http.createServer((req, res) => {
  // Decode URL and normalize
  let urlPath = decodeURIComponent(req.url.split('?')[0]);
  if (urlPath === '/') urlPath = '/index.html';

  const filePath = path.join(ROOT, urlPath);

  // Security: prevent directory traversal
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  // Check if file exists
  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      // Try index.html for directory
      const indexPath = path.join(filePath, 'index.html');
      fs.readFile(indexPath, (err2, data) => {
        if (err2) {
          res.writeHead(404);
          res.end('Not Found');
        } else {
          sendResponse(res, indexPath, data);
        }
      });
      return;
    }
    fs.readFile(filePath, (err2, data) => {
      if (err2) {
        res.writeHead(500);
        res.end('Server Error');
      } else {
        sendResponse(res, filePath, data);
      }
    });
  });
});

function sendResponse(res, filePath, data) {
  const ext = path.extname(filePath).toLowerCase();
  const contentType = MIME[ext] || 'application/octet-stream';

  const headers = {
    'Content-Type': contentType,
    'Cross-Origin-Resource-Policy': 'cross-origin',
    'Cache-Control': 'no-cache',
  };

  // Only add COEP/COOP to HTML responses for SharedArrayBuffer support
  if (contentType === 'text/html') {
    headers['Cross-Origin-Opener-Policy'] = 'same-origin';
    headers['Cross-Origin-Embedder-Policy'] = 'credentialless';
  }

  res.writeHead(200, headers);
  res.end(data);
}

server.listen(PORT, '0.0.0.0', () => {
  console.log(`elixir static server running at http://localhost:${PORT}`);
  console.log('COEP/COOP/CORP headers enabled for SharedArrayBuffer support');
});
