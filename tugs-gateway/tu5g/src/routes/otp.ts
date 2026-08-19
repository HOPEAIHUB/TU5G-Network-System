import { Router, Request, Response } from "express";
import rateLimit from "express-rate-limit";
import { createGrpcClient } from "../utils/grpcClient";
import { generateJwt, verifyJwt } from "../utils/jwtHelper";

const router = Router();

/* Rate-limit: 5 OTP requests / hour per phone */
const otpLimiter = rateLimit({
  windowMs: 60 * 60 * 1000,
  max: 5,
  keyGenerator: (req: Request) => req.body.phone || req.ip,
  handler: (_req, res) =>
    res.status(429).json({ error: "Too many OTP requests. Try later." }),
});

/**
 * POST /api/v1/otp/request
 * Body: { phone: string }
 */
router.post("/request", otpLimiter, async (req: Request, res: Response) => {
  const { phone } = req.body;
  if (!phone) return res.status(400).json({ error: "Phone required." });

  const client = createGrpcClient("hag");
  try {
    const response = await new Promise((resolve, reject) => {
      client.sendOtp({ phone }, (err: any, resp: any) => {
        if (err) reject(err);
        else resolve(resp);
      });
    });
    
    const token = await generateJwt({ phone, otpId: (response as any).id });
    res.json({ message: "OTP sent", token });
  } catch (e) {
    console.error("HAG sendOtp error:", e);
    res.status(502).json({ error: "OTP service unavailable" });
  }
});

/**
 * POST /api/v1/otp/verify
 * Body: { phone, otp, token }
 */
router.post("/verify", async (req: Request, res: Response) => {
  const { phone, otp, token } = req.body;
  if (!phone || !otp || !token)
    return res.status(400).json({ error: "Missing fields" });

  try {
    const payload: any = await verifyJwt(token);
    if (payload.phone !== phone) throw new Error("Phone mismatch");
  } catch (e) {
    return res.status(401).json({ error: "Invalid/expired token" });
  }

  const client = createGrpcClient("hag");
  try {
    const response: any = await new Promise((resolve, reject) => {
      client.verifyOtp({ phone, otp }, (err: any, resp: any) => {
        if (err) reject(err);
        else resolve(resp);
      });
    });
    
    if (response.valid) return res.json({ success: true });
    else return res.status(401).json({ success: false, error: "Bad OTP" });
  } catch (e) {
    console.error("HAG verifyOtp error:", e);
    res.status(502).json({ error: "Verification service unavailable" });
  }
});

export default router;
