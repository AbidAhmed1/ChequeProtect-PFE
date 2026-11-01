export interface KPIStats {
  totalProcessedToday:  number;
  totalPending:         number;
  aiErrorRate:          number;
  activeAgents:         number;
  totalFraudDetected:   number;
  precisionOcrGlobale:  number;
}

export interface AgentActivity {
  agentId: string;
  agentName: string;
  chequesProcessed: number;
  averageTimePerCheque: number; // in seconds
}

export interface RecentActivity {
  id: string;
  agentName: string;
  chequeNumber: string;
  status: string;
  time: string;
}

export interface ChartDataPoint {
  day: string;
  value: number;
}