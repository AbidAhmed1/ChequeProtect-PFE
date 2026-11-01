package tn.tunicheque.cheque_service.kafka;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.Map;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class ReclamationKafkaProducer {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public void publishReclamationCreated(UUID reclamationId, UUID userId, String objet) {
        try {
            Map<String, String> event = Map.of(
                "reclamationId", reclamationId.toString(),
                "userId",        userId.toString(),
                "objet",         objet != null ? objet : "Réclamation",
                "timestamp",     LocalDateTime.now().toString()
            );
            kafkaTemplate.send("reclamation.created", reclamationId.toString(), event);
            log.info("Kafka → reclamation.created : id={} userId={}", reclamationId, userId);
        } catch (Exception e) {
            log.warn("Kafka non disponible, event réclamation ignoré : {}", e.getMessage());
        }
    }

    public void publishStatutChange(UUID reclamationId, UUID userId, String objet,
                                    String ancienStatut, String nouveauStatut,
                                    String reponseAgent) {
        try {
            java.util.HashMap<String, String> event = new java.util.HashMap<>();
            event.put("reclamationId", reclamationId.toString());
            event.put("userId",        userId.toString());
            event.put("objet",         objet != null ? objet : "Réclamation");
            event.put("ancienStatut",  ancienStatut);
            event.put("nouveauStatut", nouveauStatut);
            event.put("reponseAgent",  reponseAgent != null ? reponseAgent : "");
            event.put("timestamp",     LocalDateTime.now().toString());
            kafkaTemplate.send("reclamation.statut_change", reclamationId.toString(), event);
            log.info("Kafka → reclamation.statut_change : id={} userId={} {} → {}",
                reclamationId, userId, ancienStatut, nouveauStatut);
        } catch (Exception e) {
            log.warn("Kafka non disponible, event statut réclamation ignoré : {}", e.getMessage());
        }
    }
}