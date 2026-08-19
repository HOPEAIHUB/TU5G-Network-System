import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

/**
 * TUGS OTP Bridge — Proxies OTP requests to the TUGS Gateway System
 * 
 * This function bridges the HMTML frontend to the TUGS gateway at tugs.tu5g.online
 * It handles both direct TUGS API calls and fallback to Base44 entity storage
 * 
 * IMPORTANT: This endpoint is called by ANONYMOUS public visitors on tugs.tu5g.online
 * (no Base44 login). All entity reads/writes MUST use base44.asServiceRole — the
 * plain base44.entities client requires an authenticated session and throws
 * "This app is private, You do not have access to this app" for anonymous callers.
 * 
 * Endpoints:
 * - action: "request" → POST to TUGS /api/v1/otp/request
 * - action: "verify" → POST to TUGS /api/v1/otp/verify
 * - action: "status" → Check TUGS gateway health
 */

Deno.serve(async (req) => {
  const base44 = createClientFromRequest(req);
  const db = base44.asServiceRole; // service-role client — works for anonymous public callers

  try {
    const body = await req.json();
    const { action, phone, email, otp, token } = body;

    const TUGS_URL = Deno.env.get("TUGS_GATEWAY_URL") || "https://tugs.tu5g.online/api/v1";

    if (action === "request") {
      try {
        const tugsResponse = await fetch(`${TUGS_URL}/otp/request`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone, email: email || undefined }),
          signal: AbortSignal.timeout(5000),
        });

        if (tugsResponse.ok) {
          const tugsData = await tugsResponse.json();

          await db.entities.OtpVerification.create({
            data: {
              identifier: phone || email,
              otpType: phone ? "phone" : "email",
              code: "tugs_managed",
              isUsed: false,
              userId: phone || email || "tugs-gateway",
              expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
            },
          });

          return Response.json({
            success: true,
            message: "OTP sent via TUGS gateway",
            token: tugsData.token,
            gateway: "tugs",
          });
        } else if (tugsResponse.status === 429) {
          return Response.json({
            success: false,
            message: "Rate limit exceeded. Maximum 5 OTP requests per hour.",
          }, { status: 429 });
        } else {
          return await fallbackOtp(db, phone, email);
        }
      } catch (err) {
        return await fallbackOtp(db, phone, email);
      }
    }

    if (action === "verify") {
      try {
        const tugsResponse = await fetch(`${TUGS_URL}/otp/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone, otp, token }),
          signal: AbortSignal.timeout(5000),
        });

        if (tugsResponse.ok) {
          const tugsData = await tugsResponse.json();

          if (tugsData.success) {
            const records = await db.entities.OtpVerification.list({
              filter: { identifier: phone || email },
            });
            if (records.length > 0) {
              await db.entities.OtpVerification.update(
                records[records.length - 1].id,
                { data: { isUsed: true } }
              );
            }

            return Response.json({
              success: true,
              message: "OTP verified via TUGS gateway",
              gateway: "tugs",
            });
          } else {
            return Response.json({
              success: false,
              message: "Invalid OTP or token",
            }, { status: 401 });
          }
        } else {
          return await fallbackVerify(db, phone, email, otp);
        }
      } catch (err) {
        return await fallbackVerify(db, phone, email, otp);
      }
    }

    if (action === "status") {
      try {
        const healthResponse = await fetch(`${TUGS_URL.replace("/api/v1", "")}/health`, {
          signal: AbortSignal.timeout(5000),
        });
        const healthy = healthResponse.ok;
        return Response.json({
          success: true,
          tugs_gateway: healthy ? "online" : "degraded",
          url: TUGS_URL,
        });
      } catch {
        return Response.json({
          success: true,
          tugs_gateway: "offline",
          message: "TUGS gateway not reachable — using Base44 fallback",
        });
      }
    }

    return Response.json({
      success: false,
      message: "Unknown action. Use: request, verify, or status",
    }, { status: 400 });

  } catch (error) {
    return Response.json({
      success: false,
      message: "TUGS OTP Bridge error: " + error.message,
    }, { status: 500 });
  }
});

async function fallbackOtp(db, phone, email) {
  const identifier = phone || email;
  const code = String(Math.floor(100000 + Math.random() * 900000));
  const expiresAt = new Date(Date.now() + 5 * 60 * 1000).toISOString();

  await db.entities.OtpVerification.create({
    data: {
      identifier,
      otpType: phone ? "phone" : "email",
      code,
      isUsed: false,
      userId: identifier,
      expiresAt,
    },
  });

  const token = btoa(JSON.stringify({
    phone: identifier,
    jti: crypto.randomUUID(),
    iat: Date.now(),
    exp: Date.now() + 5 * 60 * 1000,
  }));

  return Response.json({
    success: true,
    message: "OTP generated (Base44 fallback — TUGS gateway offline)",
    token,
    code,
    gateway: "base44-fallback",
  });
}

async function fallbackVerify(db, phone, email, otp) {
  const identifier = phone || email;
  const records = await db.entities.OtpVerification.list({
    filter: { identifier, isUsed: false },
  });

  if (records.length === 0) {
    return Response.json({
      success: false,
      message: "No active OTP found for this identifier",
    }, { status: 401 });
  }

  const latest = records[records.length - 1];
  const now = new Date();
  const expires = new Date(latest.data.expiresAt);

  if (now > expires) {
    return Response.json({
      success: false,
      message: "OTP has expired. Please request a new one.",
    }, { status: 401 });
  }

  if (latest.data.code !== otp) {
    return Response.json({
      success: false,
      message: "Invalid OTP code",
    }, { status: 401 });
  }

  await db.entities.OtpVerification.update(latest.id, {
    data: { isUsed: true },
  });

  return Response.json({
    success: true,
    message: "OTP verified (Base44 fallback)",
    gateway: "base44-fallback",
  });
}
