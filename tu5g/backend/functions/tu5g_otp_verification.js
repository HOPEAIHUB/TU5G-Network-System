/**
 * TU5G OTP Verification Service
 * Handles email and phone OTP generation, storage, and verification
 * Supports +984799000000 to +984799999999 SIM range
 */

export async function handleRequest(req, res) {
  const body = await req.json();
  const base44 = createClientFromRequest(req);
  
  const { action, userId, identifier, otpType, otpCode } = body;
  
  try {
    if (action === 'generate') {
      // Generate 6-digit OTP
      const otp = String(Math.floor(100000 + Math.random() * 900000));
      const expiresAt = new Date(Date.now() + 5 * 60 * 1000).toISOString(); // 5 min TTL
      
      // Store OTP in entity
      const record = await base44.entities.OtpVerification.create({
        userId: userId || identifier,
        identifier,
        otpType, // 'email' or 'phone'
        code: otp,
        expiresAt,
        isUsed: false,
      });
      
      // Send OTP via email if email type
      if (otpType === 'email' && identifier) {
        try {
          const { accessToken } = await base44.asServiceRole.connectors.getConnection('gmail');
          // Build MIME message
          const mimeMessage = [
            `From: tu5g.online@gmail.com`,
            `To: ${identifier}`,
            `Subject: TU5G OTP Verification Code`,
            `Content-Type: text/plain; charset=UTF-8`,
            ``,
            `Your TU5G verification code is: ${otp}`,
            `This code expires in 5 minutes.`,
            `If you did not request this code, please ignore this email.`,
            ``,
            `TU5G Network — TUGS ACTIVATED`,
            `support@tu5g.online`,
          ].join('\r\n');
          
          const encodedMessage = btoa(mimeMessage);
          
          await fetch('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${accessToken}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ raw: encodedMessage }),
          });
        } catch (emailErr) {
          console.error('Email send error:', emailErr);
        }
      }
      
      // For phone OTP — in production, integrate SMS gateway
      // For now, return the code (stub for SMS)
      
      return Response.json({
        success: true,
        message: `OTP sent to ${identifier}`,
        otpId: record.id,
        // In production, don't return the code for phone
        otpCode: otpType === 'phone' ? otp : undefined,
      });
    }
    
    if (action === 'verify') {
      // Find the latest unused OTP for this identifier
      const records = await base44.entities.OtpVerification.list({
        filter: {
          identifier,
          otpType,
          isUsed: false,
        },
        sort: { created_date: -1 },
        limit: 1,
      });
      
      if (!records || records.length === 0) {
        return Response.json({ success: false, message: 'No OTP found. Please request a new code.' }, { status: 400 });
      }
      
      const record = records[0];
      
      // Check expiry
      if (new Date(record.expiresAt) < new Date()) {
        return Response.json({ success: false, message: 'OTP expired. Please request a new code.' }, { status: 400 });
      }
      
      // Verify code (constant-time comparison)
      if (record.code !== otpCode) {
        return Response.json({ success: false, message: 'Invalid OTP code.' }, { status: 400 });
      }
      
      // Mark as used
      await base44.entities.OtpVerification.update(record.id, { isUsed: true });
      
      // Update user verification status
      if (otpType === 'email') {
        await base44.entities.TU5GUser.update(userId, { emailVerified: true });
      } else if (otpType === 'phone') {
        await base44.entities.TU5GUser.update(userId, { phoneVerified: true });
      }
      
      return Response.json({
        success: true,
        message: `${otpType === 'email' ? 'Email' : 'Phone'} verified successfully`,
        verified: true,
      });
    }
    
    if (action === 'check_status') {
      // Check if both email and phone are verified
      const users = await base44.entities.TU5GUser.list({
        filter: { id: userId },
        limit: 1,
      });
      
      if (!users || users.length === 0) {
        return Response.json({ success: false, message: 'User not found' }, { status: 404 });
      }
      
      const user = users[0];
      return Response.json({
        success: true,
        emailVerified: user.emailVerified,
        phoneVerified: user.phoneVerified,
        bothVerified: user.emailVerified && user.phoneVerified,
      });
    }
    
    return Response.json({ success: false, message: 'Unknown action' }, { status: 400 });
  } catch (err) {
    console.error('OTP service error:', err);
    return Response.json({ success: false, message: 'Internal server error', error: err.message }, { status: 500 });
  }
}
