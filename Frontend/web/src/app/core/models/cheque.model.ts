export type ChequeStatus = 'PENDING' | 'VALIDATED' | 'REJECTED';

export interface QrInfo {
  raw:           string;
  type:          string;
  numeroCheque:  string;
  rib:           string;
  beneficiaire:  string;
  montant:       number;
  date:          string;       // YYMMDD
  serie:         string;
  actif:         boolean;
}

export interface OCRField<T> {
  value: T;
  confidence: number;
  isManuallyVerified?: boolean;
}

export type AiPhase = 'identification' | 'compliance' | 'ocr' | 'signature';

export interface AiPhaseResult {
  phase:      AiPhase;
  score:      number;
  passed:     boolean;
  decision:   string | null;
  durationMs: number | null;
}

export interface Cheque {
  id: string;
  imagePath: string;
  uploadDate: string;
  status: ChequeStatus;
  source?: 'MOBILE' | 'WEB';
  hasVerso?: boolean;

  // OCR Extracted Fields
  chequeNumber: OCRField<string>;
  amountNumeric: OCRField<number>;
  amountText: OCRField<string>;
  emitterName: OCRField<string>;
  beneficiaryName: OCRField<string>;
  date: OCRField<string>;
  bank: OCRField<string>;
  rib: OCRField<string>;
  signatureValid: OCRField<boolean>;

  // Overall confidence
  overallConfidence: number;

  // QR code data (raw URL from pecc.tn)
  qrData?: string | null;

  // AI phase results (loaded after upload)
  aiPhases?: AiPhaseResult[];
}
