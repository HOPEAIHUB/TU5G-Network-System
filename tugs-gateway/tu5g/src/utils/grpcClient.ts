import * as grpc from "@grpc/grpc-js";
import * as protoLoader from "@grpc/proto-loader";
import path from "path";
import { credentials } from "@grpc/grpc-js";
import dotenv from "dotenv";

dotenv.config();

const PROTO_PATH = path.join(__dirname, "../../proto/tugs.proto");

const packageDef = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});
const proto = grpc.loadPackageDefinition(packageDef) as any;
const TugsService = proto.tugs.Tugs;

export function createGrpcClient(service: "hag" | "hmail" | "qsac") {
  const address =
    process.env[`${service.toUpperCase()}_GRPC_ADDR`] ?? `${service}:50051`;

  const root = process.env.GRPC_ROOT_CA
    ? Buffer.from(process.env.GRPC_ROOT_CA, "base64")
    : undefined;
  const key = process.env.GRPC_CLIENT_KEY
    ? Buffer.from(process.env.GRPC_CLIENT_KEY, "base64")
    : undefined;
  const cert = process.env.GRPC_CLIENT_CERT
    ? Buffer.from(process.env.GRPC_CLIENT_CERT, "base64")
    : undefined;

  const creds = root && key && cert
    ? credentials.createSsl(root, key, cert)
    : credentials.createInsecure();

  return new TugsService(address, creds);
}
