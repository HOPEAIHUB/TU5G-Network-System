import jwt from "jsonwebtoken";
import dotenv from "dotenv";

dotenv.config();

const PRIVATE_KEY = process.env.JWT_PRIVATE_KEY
  ? Buffer.from(process.env.JWT_PRIVATE_KEY, "base64")
  : undefined;

const PUBLIC_KEY = process.env.JWT_PUBLIC_KEY
  ? Buffer.from(process.env.JWT_PUBLIC_KEY, "base64")
  : undefined;

export async function generateJwt(
  payload: object,
  expiresIn = "5m"
): Promise<string> {
  if (!PRIVATE_KEY) throw new Error("JWT_PRIVATE_KEY not configured");
  return jwt.sign(payload, PRIVATE_KEY, {
    algorithm: "RS512",
    expiresIn,
    jwtid: crypto.randomUUID(),
  });
}

export async function verifyJwt(token: string): Promise<any> {
  if (!PUBLIC_KEY) throw new Error("JWT_PUBLIC_KEY not configured");
  return jwt.verify(token, PUBLIC_KEY, { algorithms: ["RS512"] });
}
