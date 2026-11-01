package tn.tunicheque.cheque_service.dto.response;

import lombok.Builder;
import lombok.Data;

import java.util.List;

@Data
@Builder
public class AdminDashboardDTO {
    private long   totalTraites;
    private long   enAttente;
    private double tauxErreurIA;
    private long   agentsActifs;
    private double precisionOcrGlobale;
    private double disponibiliteService;
    private List<VolumePointDTO>  volumeSeptJours;
    private List<FraudeAlertDTO>  alertesFraude;
}