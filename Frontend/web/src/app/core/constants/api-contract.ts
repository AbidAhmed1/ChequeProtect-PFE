// ================================================================
// ChèqueProtect — API CONTRACT v1.0
// Source de vérité partagée entre Frontend et Backend
// ================================================================

// ── Configuration ─────────────────────────────────────────────────────────────

export const API_CONFIG = {
  BASE_URL: 'http://localhost:8080',

  TOKEN_KEY: 'tunicheque_token',
  USER_KEY:  'tunicheque_user',

  /** false = appels HTTP réels vers le backend */
  USE_MOCK: false,

  DEMO: {
    ADMIN: { email: 'admin@tunicheque.tn', password: 'CheqOS@2025', role: 'ADMIN' as const },
    AGENT: { email: 'agent@tunicheque.tn', password: 'Agent#Ban47', role: 'AGENT' as const },
  },
} as const;

// ── Endpoints ─────────────────────────────────────────────────────────────────

export const API = {

  AUTH: {
    LOGIN:             '/api/auth/login',
    FORGOT_PASSWORD:   '/api/auth/forgot-password',
    ME:                '/api/auth/me',
    ME_PASSWORD:       '/api/auth/me/password',
    ME_PIN:            '/api/auth/me/pin',

    USERS:             '/api/auth/users',
    USERS_STATS:       '/api/auth/users/stats',
    AGENTS:            '/api/auth/users/agents',
    USER_BY_ID:        (id: string) => `/api/auth/users/${id}`,
    USER_BLOQUER:      (id: string) => `/api/auth/users/${id}/bloquer`,
    USER_DEBLOQUER:    (id: string) => `/api/auth/users/${id}/debloquer`,
    USER_REACTIVATE:   (id: string) => `/api/auth/users/${id}/reactivate`,
    USER_EMAIL:        (id: string) => `/api/auth/users/${id}/email`,
  },

  CHEQUES: {
    UPLOAD:            '/api/cheques/upload',
    BY_ID:             (id: string) => `/api/cheques/${id}`,
    AI_RESULTS:        (id: string) => `/api/cheques/${id}/ai-results`,
    MES_CHEQUES:       '/api/cheques/mes-cheques',
    EN_ATTENTE:        '/api/cheques/en-attente',
    ALL:               '/api/cheques/all',
    VALIDER:           (id: string) => `/api/cheques/${id}/valider`,
    REPROCESS:         (id: string) => `/api/cheques/${id}/reprocess`,
    IMAGE_RECTO:       (id: string) => `/api/cheques/${id}/image/recto`,
    IMAGE_VERSO:       (id: string) => `/api/cheques/${id}/image/verso`,

    ADMIN_DASHBOARD:   '/api/cheques/stats/admin/dashboard',
    ADMIN_HISTORY:     '/api/cheques/stats/admin/history',
    ADMIN_EXPORT:      '/api/cheques/stats/admin/history/export',
    AGENT_DASHBOARD:   '/api/cheques/stats/agent/dashboard',
    AGENT_HISTORY:     '/api/cheques/stats/agent/history',
    AGENT_EXPORT:      '/api/cheques/stats/agent/history/export',
  },

  RECLAMATIONS: {
    ALL:               '/api/reclamations',
    TRANSMIT:          (id: string) => `/api/reclamations/${id}/transmit`,
    UPDATE_STATUT:     (id: string) => `/api/reclamations/${id}/statut`,
  },

  NOTIFICATIONS: {
    BY_USER:           (userId: string) => `/api/notifications/user/${userId}`,
    UNREAD:            (userId: string) => `/api/notifications/user/${userId}/unread`,
    UNREAD_COUNT:      (userId: string) => `/api/notifications/user/${userId}/unread-count`,
    MARK_READ:         (id: string) => `/api/notifications/${id}/read`,
    READ_ALL:          (userId: string) => `/api/notifications/user/${userId}/read-all`,
  },

} as const;

// ── Types communs ─────────────────────────────────────────────────────────────

export type UserRole     = 'ADMIN' | 'AGENT';
export type UserType     = 'INTERNAL' | 'CLIENT';
export type ChequeStatus = 'EN_ATTENTE' | 'EN_TRAITEMENT' | 'VALIDE' | 'REJETE' | 'FRAUDE_DETECTEE';
export type AiPhase      = 'identification' | 'compliance' | 'ocr' | 'signature';

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface LoginWebRequest {
  email:    string;
  password: string;
}

/** Réponse brute du backend au login */
export interface BackendAuthResponse {
  token:     string;
  tokenType: 'Bearer';
  role:      UserRole;
  userType:  UserType;
  expiresIn: number;
}

/** Utilisateur renvoyé par GET /api/auth/me (Jackson sérialise boolean isX → x) */
export interface UserDTO {
  id:                     string;
  fullName:               string;
  email:                  string | null;
  phone:                  string | null;
  role:                   UserRole;
  userType:               UserType;
  active:                 boolean;   // Jackson: isActive → active
  verified:               boolean;  // Jackson: isVerified → verified
  resetPasswordRequested: boolean;
  createdAt:              string;
  updatedAt:              string;
}

export interface UserStatsDTO {
  totalUsers:    number;
  totalAgents:   number;
  agentsActifs:  number;
  agentsBloques: number;
  totalAdmins:   number;
}

/** Corps de POST /api/auth/users */
export interface CreateUserRequest {
  fullName:  string;
  email:     string;
  phone?:    string;
  role:      'ADMIN' | 'AGENT';
  password?: string;  // si fourni → utilisé tel quel ; sinon → auto-généré par le backend
}

export interface CreateUserResponse {
  user:              UserDTO;
  temporaryPassword: string;
  emailStatus:       'SENT' | 'FAILED';
  message:           string;
}

export interface UpdateUserRequest {
  fullName?:    string;
  email?:       string;
  phone?:       string;
  role?:        UserRole;
  isActive?:    boolean;
  newPassword?: string;
}

export interface ProfileUpdateRequest {
  fullName?: string;
  email?:    string;
  phone?:    string;
}

// ── Chèques ───────────────────────────────────────────────────────────────────

/** Chèque tel que renvoyé par le backend après upload ou validation */
export interface BackendChequeDTO {
  id:              string;
  numeroCheque:    string | null;
  imageRectoUrl:   string;
  imageVersoUrl:   string | null;
  montantExtrait:  number | null;
  montantLettres:  string | null;
  beneficiaireNom: string | null;
  dateEmission:    string | null;
  ribEmetteur:     string | null;
  qrData:          string | null;
  status:          ChequeStatus;
  decisionFinale:  string | null;
  aiScoreGlobal:   number | null;
  fraudeDetectee:  boolean;
  motifRejet:      string | null;
  pipelineMs:      number | null;
  agentId:         string | null;
  beneficiaireId:  string | null;
  titulaireId:     string | null;
  emetteurNom:     string | null;
  source:          'MOBILE' | 'WEB';
  createdAt:       string;
  validatedAt:     string | null;
}

export interface AiResult {
  id:         string;
  chequeId:   string;
  phase:      AiPhase;
  score:      number;
  passed:     boolean;
  decision:   string | null;
  durationMs: number | null;
  createdAt:  string;
}

/** Décision de validation envoyée au backend */
export interface ValiderChequeRequest {
  decision:          'VALIDE' | 'REJETE';
  motif?:            string;
  cinBeneficiaire?:  string;
  ribBeneficiaire?:  string;
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export interface AdminDashboardDTO {
  totalTraites:         number;
  enAttente:            number;
  tauxErreurIA:         number;
  agentsActifs:         number;
  precisionOcrGlobale:  number;
  disponibiliteService: number;
  volumeSeptJours:      VolumePointDTO[];
  alertesFraude:        FraudeAlertDTO[];
}

export interface AgentDashboardDTO {
  chequesAujourdhui:   number;
  validesAujourdhui:   number;
  rejetesAujourdhui:   number;
  totalTraites:        number;
  precisionOcrMoyenne: number;
  tempsMoyenMs:        number;
}

export interface VolumePointDTO {
  date:    string;
  total:   number;
  valides: number;
  rejetes: number;
}

export interface FraudeAlertDTO {
  chequeId:        string;
  numeroCheque:    string | null;
  montant:         number | null;
  beneficiaireNom: string | null;
  detecteAt:       string;
  motif:           string | null;
}

// ── Réclamations ─────────────────────────────────────────────────────────────

export interface ReclamationDTO {
  id:                    string;
  userId:                string;
  chequeId:              string | null;
  objet:                 string | null;
  description:           string | null;
  statut:                'OUVERTE' | 'EN_COURS' | 'TRANSMISE' | 'RESOLUE' | 'FERMEE';
  reponseAgent:          string | null;
  createdAt:             string;
  updatedAt:             string | null;
  clientName:            string | null;
  clientIdentifier:      string | null;
  clientIdentifierType:  string | null;
}

// ── Historique ────────────────────────────────────────────────────────────────

export interface ChequeHistoryItemDTO {
  id:              string;
  numeroCheque:    string | null;
  dateTraitement:  string;
  beneficiaireNom: string | null;
  montant:         number | null;
  statut:          ChequeStatus;
  scoreOcr:        number;
  agentId:         string | null;
  pipelineMs:      number | null;
  fraudeDetectee:  boolean;
  ribEmetteur:     string | null;
  decisionFinale:  string | null;
}

export interface PagedHistoryResponse<T> {
  content:       T[];
  totalElements: number;
  totalPages:    number;
  currentPage:   number;
  pageSize:      number;
  hasNext:       boolean;
  hasPrevious:   boolean;
}

export interface HistoryFilter {
  numeroCheque?:    string;
  beneficiaireNom?: string;
  ribEmetteur?:     string;
  dateDebut?:       string;
  dateFin?:         string;
  statut?:          ChequeStatus | '';
  page?:            number;
  size?:            number;
  sortBy?:          string;
  direction?:       'ASC' | 'DESC';
}
