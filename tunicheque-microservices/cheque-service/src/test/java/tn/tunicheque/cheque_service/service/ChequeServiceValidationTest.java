package tn.tunicheque.cheque_service.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.client.RestTemplate;
import tn.tunicheque.cheque_service.entity.Cheque;
import tn.tunicheque.cheque_service.repository.AiResultRepository;
import tn.tunicheque.cheque_service.repository.ChequeRepository;

import java.math.BigDecimal;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ChequeServiceValidationTest {

    @Mock ChequeRepository       chequeRepository;
    @Mock AiResultRepository     aiResultRepository;
    @Mock NotificationHttpClient notificationClient;
    @Mock AuthServiceClient      authServiceClient;
    @Mock RestTemplate           restTemplate;

    @InjectMocks ChequeService chequeService;

    private static final UUID CHEQUE_ID = UUID.fromString("cccccccc-0000-0000-0000-000000000001");
    private static final UUID AGENT_ID  = UUID.fromString("aaaaaaaa-0000-0000-0000-000000000002");

    private Cheque chequEnAttente;

    @BeforeEach
    void setUp() {
        chequEnAttente = Cheque.builder()
                .id(CHEQUE_ID)
                .beneficiaireId(UUID.fromString("bbbbbbbb-0000-0000-0000-000000000003"))
                .beneficiaireNom("Salma Kammoun")
                .aiScoreGlobal(new BigDecimal("0.92"))
                .numeroCheque("TN-2026-00042")
                .status(Cheque.ChequeStatus.EN_ATTENTE)
                .build();

        when(chequeRepository.findById(CHEQUE_ID)).thenReturn(Optional.of(chequEnAttente));
        when(chequeRepository.save(any(Cheque.class))).thenAnswer(inv -> inv.getArgument(0));
    }

    @Test
    void validerCheque_decisionVALIDE_metsAJourStatutEtNotifie() {
        Cheque result = chequeService.validerCheque(
                CHEQUE_ID, AGENT_ID, "VALIDE", null, null, null);

        assertThat(result.getStatus()).isEqualTo(Cheque.ChequeStatus.VALIDE);
        assertThat(result.getDecisionFinale()).isEqualTo("VALIDE");
        assertThat(result.getAgentId()).isEqualTo(AGENT_ID);
        assertThat(result.getValidatedAt()).isNotNull();

        ArgumentCaptor<String> topicCaptor = ArgumentCaptor.forClass(String.class);
        verify(notificationClient, atLeastOnce()).send(
                anyString(), eq(CHEQUE_ID.toString()),
                anyString(), anyString(), anyString(),
                topicCaptor.capture());
        assertThat(topicCaptor.getAllValues()).contains("cheque.validated");
    }

    @Test
    void validerCheque_decisionREJETE_enregistreMotif() {
        Cheque
                result = chequeService.validerCheque(
                CHEQUE_ID, AGENT_ID, "REJETE", "Signature non conforme", null, null);

        assertThat(result.getStatus()).isEqualTo(Cheque.ChequeStatus.REJETE);
        assertThat(result.getMotifRejet()).isEqualTo("Signature non conforme");
        verify(chequeRepository, times(1)).save(any(Cheque.class));
    }
}
