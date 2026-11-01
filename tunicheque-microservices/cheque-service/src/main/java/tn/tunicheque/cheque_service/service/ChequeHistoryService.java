package tn.tunicheque.cheque_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import tn.tunicheque.cheque_service.dto.response.ChequeHistoryItemDTO;
import tn.tunicheque.cheque_service.dto.response.PagedHistoryResponse;
import tn.tunicheque.cheque_service.entity.Cheque;
import tn.tunicheque.cheque_service.repository.ChequeRepository;
import tn.tunicheque.cheque_service.specification.ChequeSpecification;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Slf4j
public class ChequeHistoryService {

    private final ChequeRepository chequeRepository;

    private static final DateTimeFormatter DATE_FMT = DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm");

    // ── Historique Admin (tous les chèques, filtré + paginé) ───────────────

    public PagedHistoryResponse<ChequeHistoryItemDTO> getAdminHistory(
            String numeroCheque, String beneficiaireNom, String ribEmetteur,
            LocalDate dateDebut, LocalDate dateFin, Cheque.ChequeStatus statut,
            int page, int size, String sortBy, Sort.Direction direction) {

        Specification<Cheque> spec = ChequeSpecification.withFilters(
                numeroCheque, beneficiaireNom, ribEmetteur,
                dateDebut, dateFin, statut, null, null);

        Pageable pageable = PageRequest.of(page, size, Sort.by(direction, sortBy));
        return toPagedResponse(chequeRepository.findAll(spec, pageable));
    }

    // ── Historique Agent (filtré par agentId + paginé) ─────────────────────

    public PagedHistoryResponse<ChequeHistoryItemDTO> getAgentHistory(
            UUID agentId,
            String numeroCheque, String beneficiaireNom,
            LocalDate dateDebut, LocalDate dateFin, Cheque.ChequeStatus statut,
            int page, int size, String sortBy, Sort.Direction direction) {

        Specification<Cheque> spec = ChequeSpecification.withFilters(
                numeroCheque, beneficiaireNom, null,
                dateDebut, dateFin, statut, agentId, null);

        Pageable pageable = PageRequest.of(page, size, Sort.by(direction, sortBy));
        return toPagedResponse(chequeRepository.findAll(spec, pageable));
    }

    // ── Export CSV Admin ───────────────────────────────────────────────────

    public byte[] exportAdminCsv(
            String numeroCheque, String beneficiaireNom, String ribEmetteur,
            LocalDate dateDebut, LocalDate dateFin, Cheque.ChequeStatus statut) {

        Specification<Cheque> spec = ChequeSpecification.withFilters(
                numeroCheque, beneficiaireNom, ribEmetteur,
                dateDebut, dateFin, statut, null, null);

        List<Cheque> cheques = chequeRepository.findAll(spec,
                Sort.by(Sort.Direction.DESC, "createdAt"));
        return buildCsvBytes(cheques);
    }

    // ── Export CSV Agent ───────────────────────────────────────────────────

    public byte[] exportAgentCsv(UUID agentId,
                                  LocalDate dateDebut, LocalDate dateFin,
                                  Cheque.ChequeStatus statut) {

        Specification<Cheque> spec = ChequeSpecification.withFilters(
                null, null, null, dateDebut, dateFin, statut, agentId, null);

        List<Cheque> cheques = chequeRepository.findAll(spec,
                Sort.by(Sort.Direction.DESC, "createdAt"));
        return buildCsvBytes(cheques);
    }

    // ── Helpers ────────────────────────────────────────────────────────────

    private PagedHistoryResponse<ChequeHistoryItemDTO> toPagedResponse(Page<Cheque> page) {
        List<ChequeHistoryItemDTO> content = page.getContent().stream()
                .map(this::toDTO)
                .collect(Collectors.toList());

        return PagedHistoryResponse.<ChequeHistoryItemDTO>builder()
                .content(content)
                .totalElements(page.getTotalElements())
                .totalPages(page.getTotalPages())
                .currentPage(page.getNumber())
                .pageSize(page.getSize())
                .hasNext(page.hasNext())
                .hasPrevious(page.hasPrevious())
                .build();
    }

    private ChequeHistoryItemDTO toDTO(Cheque c) {
        double score = c.getAiScoreGlobal() != null
                ? c.getAiScoreGlobal()
                        .multiply(BigDecimal.valueOf(100))
                        .setScale(1, RoundingMode.HALF_UP)
                        .doubleValue()
                : 0.0;

        return ChequeHistoryItemDTO.builder()
                .id(c.getId())
                .numeroCheque(c.getNumeroCheque())
                .dateTraitement(c.getCreatedAt())
                .beneficiaireNom(c.getBeneficiaireNom())
                .montant(c.getMontantExtrait())
                .statut(c.getStatus())
                .scoreOcr(score)
                .agentId(c.getAgentId())
                .pipelineMs(c.getPipelineMs())
                .fraudeDetectee(c.getFraudeDetectee())
                .ribEmetteur(c.getRibEmetteur())
                .decisionFinale(c.getDecisionFinale())
                .build();
    }

    private byte[] buildCsvBytes(List<Cheque> cheques) {
        StringBuilder sb = new StringBuilder(
                "ID,Numéro Chèque,Date Traitement,Bénéficiaire,Montant (TND)," +
                "Statut,Score OCR (%),RIB Émetteur,Agent ID,Durée Pipeline (ms)\n");

        for (Cheque c : cheques) {
            double score = c.getAiScoreGlobal() != null
                    ? c.getAiScoreGlobal()
                            .multiply(BigDecimal.valueOf(100))
                            .setScale(1, RoundingMode.HALF_UP)
                            .doubleValue()
                    : 0.0;

            sb.append(csvField(c.getId()))
              .append(',').append(csvField(c.getNumeroCheque()))
              .append(',').append(csvField(c.getCreatedAt() != null
                      ? c.getCreatedAt().format(DATE_FMT) : ""))
              .append(',').append(csvField(c.getBeneficiaireNom()))
              .append(',').append(c.getMontantExtrait() != null
                      ? c.getMontantExtrait().toPlainString() : "")
              .append(',').append(csvField(c.getStatus()))
              .append(',').append(score)
              .append(',').append(csvField(c.getRibEmetteur()))
              .append(',').append(csvField(c.getAgentId()))
              .append(',').append(c.getPipelineMs() != null ? c.getPipelineMs() : "")
              .append('\n');
        }
        byte[] bom     = { (byte) 0xEF, (byte) 0xBB, (byte) 0xBF };
        byte[] content = sb.toString().getBytes(StandardCharsets.UTF_8);
        byte[] result  = new byte[bom.length + content.length];
        System.arraycopy(bom,     0, result, 0,          bom.length);
        System.arraycopy(content, 0, result, bom.length, content.length);
        return result;
    }

    /** Encapsule une valeur CSV : protège les virgules et guillemets. */
    private static String csvField(Object value) {
        if (value == null) return "";
        String s = value.toString().replace("\"", "\"\"");
        return (s.contains(",") || s.contains("\"") || s.contains("\n"))
                ? '"' + s + '"' : s;
    }
}