package tn.tunicheque.cheque_service.repository;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;
import tn.tunicheque.cheque_service.entity.Cheque;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface ChequeRepository
        extends JpaRepository<Cheque, UUID>, JpaSpecificationExecutor<Cheque> {

    // ── Requêtes existantes ────────────────────────────────────────────────

    List<Cheque> findByBeneficiaireIdOrderByCreatedAtDesc(UUID beneficiaireId);
    List<Cheque> findByTireurIdOrderByCreatedAtDesc(UUID tireurId);
    List<Cheque> findByStatusOrderByCreatedAtDesc(Cheque.ChequeStatus status);
    List<Cheque> findByStatusAndSourceOrderByCreatedAtDesc(Cheque.ChequeStatus status, String source);
    List<Cheque> findByAgentIdOrderByCreatedAtDesc(UUID agentId);

    // ── Requêtes paginées (dashboard mobile) ──────────────────────────────

    Page<Cheque> findByBeneficiaireIdOrderByCreatedAtDesc(UUID beneficiaireId, Pageable pageable);
    Page<Cheque> findByTireurIdOrderByCreatedAtDesc(UUID tireurId, Pageable pageable);
    Page<Cheque> findByBeneficiaireIdAndStatusOrderByCreatedAtDesc(UUID beneficiaireId, Cheque.ChequeStatus status, Pageable pageable);
    Page<Cheque> findByTireurIdAndStatusOrderByCreatedAtDesc(UUID tireurId, Cheque.ChequeStatus status, Pageable pageable);

    // ── Stats mobile (montant total validé par bénéficiaire) ─────────────

    @Query("SELECT COALESCE(SUM(c.montantExtrait), 0) FROM Cheque c " +
           "WHERE c.beneficiaireId = :uid AND c.status = 'VALIDE'")
    BigDecimal sumMontantValideByBeneficiaire(@Param("uid") UUID uid);

    @Query("SELECT COALESCE(SUM(c.montantExtrait), 0) FROM Cheque c " +
           "WHERE c.tireurId = :uid AND c.status IN ('EN_ATTENTE', 'EN_TRAITEMENT')")
    BigDecimal sumMontantEnCoursParTireur(@Param("uid") UUID uid);

    long countByBeneficiaireId(UUID beneficiaireId);
    long countByBeneficiaireIdAndStatus(UUID beneficiaireId, Cheque.ChequeStatus status);
    long countByTireurId(UUID tireurId);
    long countByTireurIdAndStatus(UUID tireurId, Cheque.ChequeStatus status);

    // ── Comptage par statut ────────────────────────────────────────────────

    long countByStatus(Cheque.ChequeStatus status);
    long countByAgentId(UUID agentId);

    // ── Comptage pour taux d'erreur IA ─────────────────────────────────────

    long countByAiScoreGlobalLessThan(BigDecimal threshold);

    // ── Comptage par plage de dates ────────────────────────────────────────

    long countByCreatedAtBetween(LocalDateTime start, LocalDateTime end);

    long countByStatusAndCreatedAtBetween(
            Cheque.ChequeStatus status, LocalDateTime start, LocalDateTime end);

    long countByAgentIdAndCreatedAtBetween(
            UUID agentId, LocalDateTime start, LocalDateTime end);

    long countByAgentIdAndStatusAndCreatedAtBetween(
            UUID agentId, Cheque.ChequeStatus status,
            LocalDateTime start, LocalDateTime end);

    // ── Liaison tireur rétroactive ─────────────────────────────────────────

    List<Cheque> findByRibEmetteurAndTireurIdIsNull(String ribEmetteur);

    // ── Alertes fraude ─────────────────────────────────────────────────────

    List<Cheque> findTop10ByFraudeDetecteeTrueOrderByCreatedAtDesc();

    // ── Agrégats JPQL ──────────────────────────────────────────────────────

    @Query("SELECT AVG(c.aiScoreGlobal) FROM Cheque c WHERE c.aiScoreGlobal IS NOT NULL")
    Optional<Double> findAvgAiScoreGlobal();

    @Query("SELECT AVG(c.aiScoreGlobal) FROM Cheque c " +
           "WHERE c.agentId = :agentId AND c.aiScoreGlobal IS NOT NULL")
    Optional<Double> findAvgAiScoreGlobalByAgentId(@Param("agentId") UUID agentId);

    @Query("SELECT AVG(c.pipelineMs) FROM Cheque c " +
           "WHERE c.agentId = :agentId AND c.pipelineMs IS NOT NULL")
    Optional<Double> findAvgPipelineMsByAgentId(@Param("agentId") UUID agentId);
}