package tn.tunicheque.cheque_service.dto.response;

import tn.tunicheque.cheque_service.entity.Reclamation;

import java.time.LocalDateTime;
import java.util.UUID;

public record ReclamationAdminDTO(
    UUID          id,
    UUID          userId,
    String        chequeId,
    String        objet,
    String        description,
    String        statut,
    String        reponseAgent,
    LocalDateTime createdAt,
    LocalDateTime updatedAt,
    String        clientName,
    String        clientIdentifier,
    String        clientIdentifierType
) {
    public static ReclamationAdminDTO from(Reclamation r,
                                           String clientName,
                                           String identifier,
                                           String identifierType) {
        return new ReclamationAdminDTO(
            r.getId(), r.getUserId(), r.getChequeId(),
            r.getObjet(), r.getDescription(), r.getStatut(),
            r.getReponseAgent(), r.getCreatedAt(), r.getUpdatedAt(),
            clientName, identifier, identifierType
        );
    }
}