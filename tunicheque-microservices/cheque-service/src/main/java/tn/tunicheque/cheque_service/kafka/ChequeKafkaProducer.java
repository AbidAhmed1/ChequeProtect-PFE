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
public class ChequeKafkaProducer {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public void publishChequeUploaded(UUID chequeId, UUID beneficiaireId) {
        try {
            Map<String, String> event = Map.of(
                    "chequeId",       chequeId.toString(),
                    "beneficiaireId", beneficiaireId != null ? beneficiaireId.toString() : "",
                    "status",         "UPLOADED",
                    "timestamp",      LocalDateTime.now().toString()
            );
            kafkaTemplate.send("cheque.uploaded", chequeId.toString(), event);
            log.info("Kafka → cheque.uploaded : {}", chequeId);
        } catch (Exception e) {
            log.warn("Kafka non disponible, event ignoré : {}", e.getMessage());
        }
    }

    public void publishPipelineCompleted(UUID chequeId, String decision, UUID beneficiaireId) {
        try {
            Map<String, String> event = Map.of(
                    "chequeId",       chequeId.toString(),
                    "decision",       decision,
                    "beneficiaireId", beneficiaireId != null ? beneficiaireId.toString() : "",
                    "timestamp",      LocalDateTime.now().toString()
            );
            kafkaTemplate.send("pipeline.completed", chequeId.toString(), event);
            log.info("Kafka → pipeline.completed : {} → {}", chequeId, decision);
        } catch (Exception e) {
            log.warn("Kafka non disponible, event ignoré : {}", e.getMessage());
        }
    }

    public void publishChequeValidated(UUID chequeId, String decision,
                                       UUID beneficiaireId, UUID tireurId) {
        try {
            Map<String, String> event = Map.of(
                    "chequeId",       chequeId.toString(),
                    "decision",       decision,
                    "beneficiaireId", beneficiaireId != null ? beneficiaireId.toString() : "",
                    "tireurId",       tireurId       != null ? tireurId.toString()       : "",
                    "timestamp",      LocalDateTime.now().toString()
            );
            kafkaTemplate.send("cheque.validated", chequeId.toString(), event);
            log.info("Kafka → cheque.validated : {} → {}", chequeId, decision);
        } catch (Exception e) {
            log.warn("Kafka non disponible, event ignoré : {}", e.getMessage());
        }
    }
}