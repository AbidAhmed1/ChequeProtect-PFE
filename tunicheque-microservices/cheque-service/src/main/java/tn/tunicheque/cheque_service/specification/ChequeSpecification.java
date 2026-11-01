package tn.tunicheque.cheque_service.specification;

import jakarta.persistence.criteria.Predicate;
import org.springframework.data.jpa.domain.Specification;
import tn.tunicheque.cheque_service.entity.Cheque;

import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class ChequeSpecification {

    private ChequeSpecification() {}

    public static Specification<Cheque> withFilters(
            String numeroCheque,
            String beneficiaireNom,
            String ribEmetteur,
            LocalDate dateDebut,
            LocalDate dateFin,
            Cheque.ChequeStatus statut,
            UUID agentId,
            Boolean fraudeDetectee) {

        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (numeroCheque != null && !numeroCheque.isBlank()) {
                predicates.add(cb.like(
                        cb.lower(root.get("numeroCheque")),
                        "%" + numeroCheque.trim().toLowerCase() + "%"));
            }
            if (beneficiaireNom != null && !beneficiaireNom.isBlank()) {
                predicates.add(cb.like(
                        cb.lower(root.get("beneficiaireNom")),
                        "%" + beneficiaireNom.trim().toLowerCase() + "%"));
            }
            if (ribEmetteur != null && !ribEmetteur.isBlank()) {
                predicates.add(cb.like(root.get("ribEmetteur"),
                        "%" + ribEmetteur.trim() + "%"));
            }
            if (dateDebut != null) {
                predicates.add(cb.greaterThanOrEqualTo(
                        root.get("createdAt"), dateDebut.atStartOfDay()));
            }
            if (dateFin != null) {
                predicates.add(cb.lessThanOrEqualTo(
                        root.get("createdAt"), dateFin.atTime(LocalTime.MAX)));
            }
            if (statut != null) {
                predicates.add(cb.equal(root.get("status"), statut));
            }
            if (agentId != null) {
                predicates.add(cb.equal(root.get("agentId"), agentId));
            }
            if (fraudeDetectee != null) {
                predicates.add(cb.equal(root.get("fraudeDetectee"), fraudeDetectee));
            }

            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }
}