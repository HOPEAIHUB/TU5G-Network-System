import { Router, Request, Response } from 'express';
import multer from 'multer';
import { getClient } from '../utils/grpcClient';

const router = Router();

// Configure Multer memory storage for incoming document uploads
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 25 * 1024 * 1024 }, // 25MB file size limit
});

/**
 * POST /api/v1/report — Submit KYC report
 * Accepts multipart/form-data with file upload
 * Calls QSAC gRPC to encrypt and store the document
 * Calls HMAIL to email a signed receipt (PDF/XML)
 * Returns { status, receiptId }
 */
router.post('/', upload.any(), async (req: Request, res: Response) => {
  try {
    const files = req.files as Express.Multer.File[] | undefined;
    const file = files && files.length > 0 ? files[0] : (req as any).file;

    if (!file) {
      return res.status(400).json({ error: 'No KYC document file uploaded' });
    }

    const email = req.body.email || 'kyc-reports@tu5g.online';
    const filename = file.originalname || 'kyc_report.pdf';
    const content = file.buffer;
    const mimeType = file.mimetype || 'application/octet-stream';

    // 1. Call QSAC gRPC service to encrypt and store document
    const qsacClient = getClient('qsac');
    const qsacResponse = await qsacClient.encryptAndStore!({
      filename,
      content,
      mimeType,
    });

    const receiptId =
      qsacResponse?.receiptId ||
      qsacResponse?.receipt_id ||
      `rcpt_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const status = qsacResponse?.status || 'ENCRYPTED_AND_STORED';

    // 2. Call HMAIL gRPC service to email a signed receipt (PDF/XML)
    const hmailClient = getClient('hmail');
    await hmailClient.sendReceipt!({
      email,
      receiptId,
      document: content,
      filename: `receipt_${receiptId}.pdf`,
    });

    // Notify WebSocket subscribers if broadcast function is attached
    if (typeof (req.app as any).broadcastWs === 'function') {
      (req.app as any).broadcastWs({
        event: 'kyc_report_submitted',
        receiptId,
        status,
        timestamp: new Date().toISOString(),
      });
    }

    // Return { status, receiptId }
    return res.status(200).json({
      status,
      receiptId,
    });
  } catch (error: any) {
    console.error('Error in POST /api/v1/report:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
});

export default router;
