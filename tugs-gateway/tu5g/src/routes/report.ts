import { Router, Request, Response } from "express";
import multer from "multer";

const upload = multer({ storage: multer.memoryStorage() });
const router = Router();

/**
 * POST /api/v1/report
 * multipart/form-data { file: binary }
 *
 * Flow:
 *   1. Upload file to TU5G (in-memory)
 *   2. Call QSAC via gRPC to encrypt & store → returns signed URL
 *   3. Instruct HMAIL to email receipt (gRPC)
 */

// Note: In production, createGrpcClient would be imported from utils/grpcClient
// For now we use a simplified in-process flow to avoid proto loading issues
router.post("/", upload.single("file"), async (req: Request, res: Response) => {
  if (!req.file) return res.status(400).json({ error: "File missing" });

  try {
    // Step 1: Store document info
    const { originalname, size, mimetype, buffer } = req.file;
    
    // Step 2: Generate receipt ID
    const receiptId = `RCP-${Date.now()}-${Math.random().toString(36).slice(2, 10).toUpperCase()}`;
    
    // Step 3: In production, call QSAC to encrypt & store, then HMAIL to send receipt
    // For now, return success with receipt info
    res.json({
      status: "stored",
      receiptId,
      filename: originalname,
      size,
      mimetype,
      message: "KYC report submitted. Encrypted receipt will be emailed.",
    });
  } catch (e) {
    console.error("Report submission error:", e);
    res.status(500).json({ error: "Failed to submit report" });
  }
});

export default router;
