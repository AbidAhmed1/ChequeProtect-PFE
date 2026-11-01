package tn.tunicheque.cheque_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import tn.tunicheque.cheque_service.dto.response.*;
import tn.tunicheque.cheque_service.entity.Cheque;
import tn.tunicheque.cheque_service.repository.ChequeRepository;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Slf4j
public class StatsService {

    private final ChequeRepository  chequeRepository;
    private final AuthServiceClient authServiceClient;

    // ── Admin Dashboard ────────────────────────────────────────────────────

    public AdminDashboardDTO getAdminDashboard() {
        long totalTraites = chequeRepository.count();
        long enAttente    = chequeRepository.countByStatus(Cheque.ChequeStatus.EN_ATTENTE)
                          + chequeRepository.countByStatus(Cheque.ChequeStatus.EN_TRAITEMENT);

        // Taux d'erreur IA = % chèques dont le score global est < 0.85
        long lowScoreCount = chequeRepository.countByAiScoreGlobalLessThan(new BigDecimal("0.85"));
        double tauxErreur = totalTraites > 0
                ? round1(lowScoreCount * 100.0 / totalTraites) : 0.0;

        // Précision OCR globale (moyenne des scores * 100)
        double precisionOcr = chequeRepository.findAvgAiScoreGlobal()
                .map(avg -> round1(avg * 100))
                .orElse(0.0);

        // Agents actifs depuis auth-service
        long agentsActifs = authServiceClient.getAgentsActifsCount();

        // Alertes fraude — 10 dernières
        List<FraudeAlertDTO> alertes = chequeRepository
                .findTop10ByFraudeDetecteeTrueOrderByCreatedAtDesc()
                .stream()
                .map(c -> FraudeAlertDTO.builder()
                        .chequeId(c.getId())
                        .numeroCheque(c.getNumeroCheque())
                        .montant(c.getMontantExtrait())
                        .beneficiaireNom(c.getBeneficiaireNom())
                        .detecteAt(c.getCreatedAt())
                        .motif(c.getMotifRejet())
                        .build())
                .collect(Collectors.toList());

        return AdminDashboardDTO.builder()
                .totalTraites(totalTraites)
                .enAttente(enAttente)
                .tauxErreurIA(tauxErreur)
                .agentsActifs(agentsActifs)
                .precisionOcrGlobale(precisionOcr)
                .disponibiliteService(99.9)
                .volumeSeptJours(buildVolumeChart(7))
                .alertesFraude(alertes)
                .build();
    }

    // ── Agent Dashboard ────────────────────────────────────────────────────

    public AgentDashboardDTO getAgentDashboard(UUID agentId) {
        LocalDateTime startOfDay = LocalDate.now().atStartOfDay();
        LocalDateTime endOfDay   = LocalDate.now().atTime(LocalTime.MAX);

        long chequesAujourdhui = chequeRepository
                .countByAgentIdAndCreatedAtBetween(agentId, startOfDay, endOfDay);
        long validesAujourdhui = chequeRepository
                .countByAgentIdAndStatusAndCreatedAtBetween(
                        agentId, Cheque.ChequeStatus.VALIDE, startOfDay, endOfDay);
        long rejetesAujourdhui = chequeRepository
                .countByAgentIdAndStatusAndCreatedAtBetween(
                        agentId, Cheque.ChequeStatus.REJETE, startOfDay, endOfDay);
        long totalTraites = chequeRepository.countByAgentId(agentId);

        double precisionOcr = chequeRepository.findAvgAiScoreGlobalByAgentId(agentId)
                .map(avg -> round1(avg * 100))
                .orElse(0.0);

        double tempsMoyen = chequeRepository.findAvgPipelineMsByAgentId(agentId)
                .map(avg -> BigDecimal.valueOf(avg).setScale(0, RoundingMode.HALF_UP).doubleValue())
                .orElse(0.0);

        return AgentDashboardDTO.builder()
                .chequesAujourdhui(chequesAujourdhui)
                .validesAujourdhui(validesAujourdhui)
                .rejetesAujourdhui(rejetesAujourdhui)
                .totalTraites(totalTraites)
                .precisionOcrMoyenne(precisionOcr)
                .tempsMoyenMs(tempsMoyen)
                .build();
    }

    // ── Volume 7 jours ─────────────────────────────────────────────────────

    private List<VolumePointDTO> buildVolumeChart(int days) {
        List<VolumePointDTO> result = new ArrayList<>();
        for (int i = days - 1; i >= 0; i--) {
            LocalDate     date  = LocalDate.now().minusDays(i);
            LocalDateTime start = date.atStartOfDay();
            LocalDateTime end   = date.atTime(LocalTime.MAX);

            long total   = chequeRepository.countByCreatedAtBetween(start, end);
            long valides = chequeRepository.countByStatusAndCreatedAtBetween(
                    Cheque.ChequeStatus.VALIDE, start, end);
            long rejetes = chequeRepository.countByStatusAndCreatedAtBetween(
                    Cheque.ChequeStatus.REJETE, start, end);

            result.add(VolumePointDTO.builder()
                    .date(date.toString())
                    .total(total)
                    .valides(valides)
                    .rejetes(rejetes)
                    .build());
        }
        return result;
    }

    private double round1(double value) {
        return BigDecimal.valueOf(value).setScale(1, RoundingMode.HALF_UP).doubleValue();
    }
}