import { Router, Request, Response } from 'express';
import rateLimit from 'express-rate-limit';
import { signNonce, verifyNonce } from '../utils/jwtHelper';
import { getClient } from '../utils/grpcClient';

const router = Router();

/**
 * Rate limiter: 5 OTP requests per hour per IP address
 */
export const otpRateLimiter = rateLimit({
  windowMs: 60 * 60 * 1000, // 1 hour
  max: 5,
  standardHeaders: true,
  legacyHeaders: false,
  statusCode: 429,
  message: { error: 'Rate limit exceeded: Maximum 5 OTP requests per hour.' },
});

/**
 * POST /api/v1/otp/request
 * Accepts { phone, email? } in body
 * Generates a JWT nonce (jti) with phone number claim
 * Calls HAG gRPC service to send OTP via SMS/USSD
 * Returns { message, token } where token is the signed JWT
 */
router.post('/request', otpRateLimiter, async (req: Request, res: Response) => {
  try {
    const { phone, email } = req.body || {};

    if (!phone) {
      return res.status(400).json({ error: 'Phone number is required' });
    }

    // Generate JWT nonce with phone claim & jti
    const token = signNonce({ phone, email });

    // Verify token to extract jti nonce
    const decoded = verifyNonce(token);
    const nonce = decoded.jti;

    // Call HAG gRPC service to send OTP
    const hagClient = getClient('hag');
    const hagResponse = await hagClient.sendOtp!({
      phone,
      email,
      nonce,
    });

    // Notify WebSocket subscribers if broadcast function is attached
    if (typeof (req.app as any).broadcastWs === 'function') {
      (req.app as any).broadcastWs({
        event: 'otp_requested',
        phone,
        email,
        timestamp: new Date().toISOString(),
      });
    }

    return res.status(200).json({
      message: hagResponse?.message || 'OTP sent successfully',
      token,
    });
  } catch (error: any) {
    console.error('Error in POST /api/v1/otp/request:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
});

/**
 * POST /api/v1/otp/verify
 * Accepts { phone, otp, token } in body
 * Verifies JWT token (RS512)
 * Calls HAG gRPC service to verify OTP
 * On success: calls HMAIL to send confirmation email
 * Returns { success: boolean }
 * Returns 401 on invalid OTP or token
 */
router.post('/verify', async (req: Request, res: Response) => {
  try {
    const { phone, otp, token } = req.body || {};

    if (!phone || !otp || !token) {
      return res.status(400).json({ error: 'phone, otp, and token are required' });
    }

    // Verify JWT token (RS512)
    let decoded;
    try {
      decoded = verifyNonce(token);
    } catch (jwtError: any) {
      return res.status(401).json({ success: false, error: 'Invalid or expired token' });
    }

    // Validate phone claim in token matches request
    if (decoded.phone && decoded.phone !== phone) {
      return res.status(401).json({ success: false, error: 'Token phone claim mismatch' });
    }

    // Call HAG gRPC service to verify OTP
    const hagClient = getClient('hag');
    const verifyResponse = await hagClient.verifyOtp!({
      phone,
      otp,
      token,
    });

    if (!verifyResponse || !verifyResponse.success) {
      return res.status(401).json({ success: false, error: verifyResponse?.message || 'Invalid OTP' });
    }

    // On success: call HMAIL to send confirmation email if recipient available
    const emailRecipient = decoded.email || req.body.email;
    if (emailRecipient) {
      try {
        const hmailClient = getClient('hmail');
        await hmailClient.sendConfirmationEmail!({
          to: emailRecipient,
          subject: 'TU5G OTP Verification Confirmation',
          body: `Your OTP verification for ${phone} was successful.`,
        });
      } catch (emailErr: any) {
        console.warn('Failed to send confirmation email via HMAIL:', emailErr.message);
      }
    }

    // Notify WebSocket subscribers if broadcast function is attached
    if (typeof (req.app as any).broadcastWs === 'function') {
      (req.app as any).broadcastWs({
        event: 'otp_verified',
        phone,
        success: true,
        timestamp: new Date().toISOString(),
      });
    }

    return res.status(200).json({ success: true });
  } catch (error: any) {
    console.error('Error in POST /api/v1/otp/verify:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
});

export default router;
