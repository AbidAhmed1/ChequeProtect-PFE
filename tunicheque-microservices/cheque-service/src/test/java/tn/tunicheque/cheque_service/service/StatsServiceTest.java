package tn.tunicheque.cheque_service.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tn.tunicheque.cheque_service.dto.response.AdminDashboardDTO;
import tn.tunicheque.cheque_service.entity.Cheque;
import tn.tunicheque.cheque_service.repository.ChequeRepository;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class StatsServiceTest {

    @Mock ChequeRepository  chequeRepository;
    @Mock AuthServiceClient authServiceClient;

    @InjectMocks StatsService statsService;

    @Test
    void getAdminDashboard_calcule_tauxErreur_proportionnel() {
        when(chequeRepository.count()).thenReturn(10L);
        when(chequeRepository.countByStatus(any())).thenReturn(1L);
        when(chequeRepository.countByAiScoreGlobalLessThan(new BigDecimal("0.85"))).thenReturn(3L);
        when(chequeRepository.findAvgAiScoreGlobal()).thenReturn(Optional.of(0.89));
        when(authServiceClient.getAgentsActifsCount()).thenReturn(5L);
        when(chequeRepository.findTop10ByFraudeDetecteeTrueOrderByCreatedAtDesc()).thenReturn(List.of());

        AdminDashboardDTO dto = statsService.getAdminDashboard();

        assertThat(dto.getTauxErreurIA()).isEqualTo(30.0);
        assertThat(dto.getPrecisionOcrGlobale()).isEqualTo(89.0);
        assertThat(dto.getAgentsActifs()).isEqualTo(5L);
        assertThat(dto.getDisponibiliteService()).isEqualTo(99.9);
        assertThat(dto.getAlertesFraude()).isEmpty();
    }

    @Test
    void getAdminDashboard_retourne_zeros_quandAucunCheque() {
        when(chequeRepository.count()).thenReturn(0L);
        when(chequeRepository.countByStatus(any())).thenReturn(0L);
        when(chequeRepository.countByAiScoreGlobalLessThan(any())).thenReturn(0L);
        when(chequeRepository.findAvgAiScoreGlobal()).thenReturn(Optional.empty());
        when(authServiceClient.getAgentsActifsCount()).thenReturn(0L);
        when(chequeRepository.findTop10ByFraudeDetecteeTrueOrderByCreatedAtDesc()).thenReturn(List.of());

        AdminDashboardDTO result = statsService.getAdminDashboard();

        assertThat(result.getTauxErreurIA()).isEqualTo(0.0);
        assertThat(result.getPrecisionOcrGlobale()).isEqualTo(0.0);
        assertThat(result.getTotalTraites()).isEqualTo(0L);
    }
}
