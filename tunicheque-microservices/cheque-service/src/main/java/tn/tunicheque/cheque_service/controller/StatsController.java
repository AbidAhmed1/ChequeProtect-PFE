package tn.tunicheque.cheque_service.controller;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Sort;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import tn.tunicheque.cheque_service.dto.response.*;
import tn.tunicheque.cheque_service.entity.Cheque;
import tn.tunicheque.cheque_service.service.ChequeHistoryService;
import tn.tunicheque.cheque_service.service.StatsService;

import java.time.LocalDate;
import java.util.UUID;

/**
 * StatsController — Tableaux de bord et historiques pour l'Admin et l'Agent.
 *
 * Tous les endpoints s'appuient sur les headers X-User-Id et X-User-Role
 * injectés par l'API Gateway après validation du JWT.
 *
 * Admin  : /api/cheques/stats/admin/**
 * Agent  : /api/cheques/stats/agent/**
 */
@RestController
@RequestMapping("/api/cheques/stats")
@RequiredArgsConstructor
@Slf4j
public class StatsController {

    private final StatsService         statsService;
    private final ChequeHistoryService historyService;

    // ── Helpers d'accès ────────────────────────────────────────────────────

    private static boolean isAdmin(String role) {
        return role != null && role.contains("ADMIN");
    }

    private static boolean isAgentOrAdmin(String role) {
        return role != null && (role.contains("AGENT") || role.contains("ADMIN"));
    }

    private static <T> ResponseEntity<T> forbidden() {
        return ResponseEntity.status(403).build();
    }

    // ════════════════════════════════════════════════════════════════════════
    //  ADMIN ─ Dashboard
    // ════════════════════════════════════════════════════════════════════════

    /**
     * KPIs globaux : total chèques, en attente, taux erreur IA,
     * agents actifs, précision OCR, volume 7 jours, alertes fraude.
     */
    @GetMapping("/admin/dashboard")
    public ResponseEntity<AdminDashboardDTO> getAdminDashboard(
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role) {

        if (!isAdmin(role)) return forbidden();
        log.debug("Admin dashboard demandé");
        return ResponseEntity.ok(statsService.getAdminDashboard());
    }

    // ════════════════════════════════════════════════════════════════════════
    //  ADMIN ─ Historique des traitements
    // ════════════════════════════════════════════════════════════════════════

    /**
     * Historique paginé avec filtres avancés (numéro, bénéficiaire, RIB,
     * plage de dates, statut) et tri configurable.
     */
    @GetMapping("/admin/history")
    public ResponseEntity<PagedHistoryResponse<ChequeHistoryItemDTO>> getAdminHistory(
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role,
            @RequestParam(required = false) String numeroCheque,
            @RequestParam(required = false) String beneficiaireNom,
            @RequestParam(required = false) String ribEmetteur,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateDebut,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateFin,
            @RequestParam(required = false)    Cheque.ChequeStatus statut,
            @RequestParam(defaultValue = "0")  int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(defaultValue = "createdAt") String sortBy,
            @RequestParam(defaultValue = "DESC")      String direction) {

        if (!isAdmin(role)) return forbidden();

        Sort.Direction dir = Sort.Direction.fromOptionalString(direction)
                .orElse(Sort.Direction.DESC);

        return ResponseEntity.ok(historyService.getAdminHistory(
                numeroCheque, beneficiaireNom, ribEmetteur,
                dateDebut, dateFin, statut,
                page, size, sortBy, dir));
    }

    /**
     * Export CSV de l'historique admin avec les mêmes filtres que la liste.
     */
    @GetMapping("/admin/history/export")
    public ResponseEntity<byte[]> exportAdminHistory(
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role,
            @RequestParam(required = false) String numeroCheque,
            @RequestParam(required = false) String beneficiaireNom,
            @RequestParam(required = false) String ribEmetteur,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateDebut,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateFin,
            @RequestParam(required = false) Cheque.ChequeStatus statut) {

        if (!isAdmin(role)) return forbidden();

        byte[] csv = historyService.exportAdminCsv(
                numeroCheque, beneficiaireNom, ribEmetteur,
                dateDebut, dateFin, statut);

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"historique_cheques.csv\"")
                .contentType(MediaType.parseMediaType("text/csv; charset=UTF-8"))
                .body(csv);
    }

    // ════════════════════════════════════════════════════════════════════════
    //  AGENT ─ Dashboard
    // ════════════════════════════════════════════════════════════════════════

    /**
     * KPIs journaliers de l'agent connecté : chèques du jour, validés,
     * rejetés, précision OCR moyenne, temps moyen de traitement.
     */
    @GetMapping("/agent/dashboard")
    public ResponseEntity<AgentDashboardDTO> getAgentDashboard(
            @RequestHeader("X-User-Id")                             String agentId,
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role) {

        if (!isAgentOrAdmin(role)) return forbidden();
        return ResponseEntity.ok(
                statsService.getAgentDashboard(UUID.fromString(agentId)));
    }

    // ════════════════════════════════════════════════════════════════════════
    //  AGENT ─ Historique personnel
    // ════════════════════════════════════════════════════════════════════════

    /**
     * Historique paginé des traitements effectués par l'agent connecté,
     * avec filtres sur numéro, bénéficiaire, dates et statut.
     */
    @GetMapping("/agent/history")
    public ResponseEntity<PagedHistoryResponse<ChequeHistoryItemDTO>> getAgentHistory(
            @RequestHeader("X-User-Id")                             String agentId,
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role,
            @RequestParam(required = false) String numeroCheque,
            @RequestParam(required = false) String beneficiaireNom,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateDebut,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateFin,
            @RequestParam(required = false)    Cheque.ChequeStatus statut,
            @RequestParam(defaultValue = "0")  int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(defaultValue = "createdAt") String sortBy,
            @RequestParam(defaultValue = "DESC")      String direction) {

        if (!isAgentOrAdmin(role)) return forbidden();

        Sort.Direction dir = Sort.Direction.fromOptionalString(direction)
                .orElse(Sort.Direction.DESC);

        return ResponseEntity.ok(historyService.getAgentHistory(
                UUID.fromString(agentId),
                numeroCheque, beneficiaireNom,
                dateDebut, dateFin, statut,
                page, size, sortBy, dir));
    }

    /**
     * Export CSV des traitements personnels de l'agent connecté.
     */
    @GetMapping("/agent/history/export")
    public ResponseEntity<byte[]> exportAgentHistory(
            @RequestHeader("X-User-Id")                             String agentId,
            @RequestHeader(value = "X-User-Role", defaultValue = "") String role,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateDebut,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate dateFin,
            @RequestParam(required = false) Cheque.ChequeStatus statut) {

        if (!isAgentOrAdmin(role)) return forbidden();

        byte[] csv = historyService.exportAgentCsv(
                UUID.fromString(agentId), dateDebut, dateFin, statut);

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"mes_traitements.csv\"")
                .contentType(MediaType.parseMediaType("text/csv; charset=UTF-8"))
                .body(csv);
    }
}