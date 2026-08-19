import express, { Express, Request, Response, NextFunction } from 'express';
import cors from 'cors';
import http from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import dotenv from 'dotenv';
import otpRouter from './routes/otp';
import reportRouter from './routes/report';
import { getClient } from './utils/grpcClient';

dotenv.config();

const app: Express = express();
const PORT = process.env.TU5G_PORT || 8080;

// Express app with CORS, JSON body parser
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Create HTTP server
const server = http.createServer(app);

// WebSocket server for real-time OTP status updates
const wss = new WebSocketServer({ server });

const connectedClients = new Set<WebSocket>();

wss.on('connection', (ws: WebSocket) => {
  connectedClients.add(ws);
  console.log('[WebSocket] Client connected. Total clients:', connectedClients.size);

  ws.send(
    JSON.stringify({
      type: 'connection',
      status: 'connected',
      message: 'Connected to TU5G Gateway real-time updates channel',
      timestamp: new Date().toISOString(),
    })
  );

  ws.on('message', (message: Buffer) => {
    try {
      const parsed = JSON.parse(message.toString());
      if (parsed.type === 'ping') {
        ws.send(JSON.stringify({ type: 'pong', timestamp: new Date().toISOString() }));
      }
    } catch {
      // Ignore non-JSON messages
    }
  });

  ws.on('close', () => {
    connectedClients.delete(ws);
    console.log('[WebSocket] Client disconnected. Total clients:', connectedClients.size);
  });

  ws.on('error', (err) => {
    console.error('[WebSocket] Error:', err);
    connectedClients.delete(ws);
  });
});

// Helper function to broadcast real-time OTP status updates
export function broadcastWs(data: any): void {
  const message = JSON.stringify(data);
  for (const client of connectedClients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  }
}

// Attach WebSocket broadcast method to app
(app as any).broadcastWs = broadcastWs;

// gRPC clients to HAG (hag:50051) and HMAIL (hmail:50051) with TLS
try {
  const hagClient = getClient('hag');
  const hmailClient = getClient('hmail');
  console.log(`[gRPC] Initialized TLS-secured gRPC clients: HAG (${hagClient.address}), HMAIL (${hmailClient.address})`);
} catch (grpcErr: any) {
  console.warn('[gRPC] Client initialization notice:', grpcErr.message);
}

// Health check endpoint at /health
app.get('/health', (req: Request, res: Response) => {
  return res.status(200).json({
    status: 'ok',
    service: 'tu5g-gateway',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  });
});

// Routes mounted at /api/v1/
const apiV1Router = express.Router();
apiV1Router.use('/otp', otpRouter);
apiV1Router.use('/report', reportRouter);

app.use('/api/v1', apiV1Router);

// Global Error Handler
app.use((err: any, req: Request, res: Response, next: NextFunction) => {
  console.error('[TU5G Gateway Error]:', err);
  const statusCode = err.statusCode || err.status || 500;
  return res.status(statusCode).json({
    error: err.message || 'Internal Server Error',
  });
});

// Listens on port 8080 (from TU5G_PORT env var)
server.listen(PORT, () => {
  console.log(`TU5G Gateway service running on port ${PORT}`);
});

// Graceful shutdown handling
function handleGracefulShutdown(signal: string) {
  console.log(`[TU5G] ${signal} signal received. Initiating graceful shutdown...`);

  server.close(() => {
    console.log('[TU5G] HTTP server closed.');

    for (const client of connectedClients) {
      client.close(1001, 'Server shutting down');
    }
    connectedClients.clear();

    wss.close(() => {
      console.log('[TU5G] WebSocket server closed.');
      process.exit(0);
    });
  });

  // Force termination after 10 seconds if connections are stuck
  setTimeout(() => {
    console.error('[TU5G] Shutdown timeout reached. Forcing exit.');
    process.exit(1);
  }, 10000);
}

process.on('SIGTERM', () => handleGracefulShutdown('SIGTERM'));
process.on('SIGINT', () => handleGracefulShutdown('SIGINT'));

export default app;
