/**
 * TU5G – 5G Gateway Service (Node.js/TS)
 * Exposes REST (OTP, KYC report), WebSocket, and gRPC client to HAG & HMAIL
 */

import express, { Request, Response, NextFunction } from "express";
import http from "http";
import { WebSocketServer } from "ws";
import cors from "cors";
import rateLimit from "express-rate-limit";
import dotenv from "dotenv";

import otpRouter from "./routes/otp";
import reportRouter from "./routes/report";
import { verifyJwt } from "./utils/jwtHelper";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

// Global rate-limit: 100 req/min per IP
app.use(rateLimit({
  windowMs: 60_000,
  max: 100,
  standardHeaders: true,
  legacyHeaders: false,
  message: "Too many requests, please try later."
}));

// JWT verification middleware (RS512)
app.use(async (req: Request, res: Response, next: NextFunction) => {
  const auth = req.headers.authorization;
  if (!auth?.startsWith("Bearer ")) return next();
  try {
    const token = auth.slice(7);
    (req as any).user = await verifyJwt(token);
  } catch (e) {
    console.warn("Invalid JWT", e);
  }
  next();
});

app.use("/api/v1/otp", otpRouter);
app.use("/api/v1/report", reportRouter);
app.get("/healthz", (_req, res) => res.json({ status: "ok", service: "tu5g-gateway", version: "1.0" }));

// WebSocket for real-time notifications
const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: "/ws" });

wss.on("connection", (ws, req) => {
  console.log(`WS client connected: ${req.socket.remoteAddress}`);
  ws.on("message", (msg) => {
    console.log("WS message:", msg.toString());
    ws.send(JSON.stringify({ type: "ack", timestamp: Date.now() }));
  });
  ws.on("close", () => console.log("WS client disconnected"));
});

const PORT = process.env.TU5G_PORT ? parseInt(process.env.TU5G_PORT) : 8080;
server.listen(PORT, () => {
  console.log(`TU5G Gateway listening on :${PORT}`);
  console.log(`TUGS v1.0 ACTIVATED — AM = YOU PROTOCOL ACTIVATED`);
});

// Graceful shutdown
process.on("SIGTERM", () => {
  console.log("SIGTERM received, shutting down...");
  server.close(() => console.log("Server closed"));
  wss.close(() => console.log("WebSocket closed"));
});
