import jwt, { JwtPayload, SignOptions, VerifyOptions } from 'jsonwebtoken';
import { randomUUID } from 'crypto';

export interface OtpJwtPayload extends JwtPayload {
  jti: string;
  phone: string;
  email?: string;
  iat?: number;
  exp?: number;
}

export interface NoncePayload {
  phone: string;
  email?: string;
  [key: string]: any;
}

/**
 * Signs a JWT nonce with RS512 algorithm using JWT_PRIVATE_KEY.
 * Payload includes jti (unique UUID), phone number, iat, and 5-minute exp.
 */
export function signNonce(payload: NoncePayload): string {
  const privateKey = process.env.JWT_PRIVATE_KEY;
  if (!privateKey) {
    throw new Error('JWT_PRIVATE_KEY environment variable is not configured');
  }

  const formattedKey = privateKey.replace(/\\n/g, '\n');
  const jti = payload.jti || randomUUID();

  const options: SignOptions = {
    algorithm: 'RS512',
    expiresIn: '5m',
  };

  return jwt.sign(
    {
      ...payload,
      phone: payload.phone,
      jti,
    },
    formattedKey,
    options
  );
}

/**
 * Verifies a JWT nonce using RS512 algorithm with JWT_PUBLIC_KEY.
 * Returns the decoded JwtPayload on success or throws an Error.
 */
export function verifyNonce(token: string): OtpJwtPayload {
  const publicKey = process.env.JWT_PUBLIC_KEY;
  if (!publicKey) {
    throw new Error('JWT_PUBLIC_KEY environment variable is not configured');
  }

  const formattedKey = publicKey.replace(/\\n/g, '\n');

  const options: VerifyOptions = {
    algorithms: ['RS512'],
  };

  const decoded = jwt.verify(token, formattedKey, options);

  if (typeof decoded === 'string' || !decoded) {
    throw new Error('Invalid token payload');
  }

  return decoded as OtpJwtPayload;
}
