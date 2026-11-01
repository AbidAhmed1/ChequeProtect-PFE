package tn.tunicheque.notification_service.kafka;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;
import tn.tunicheque.notification_service.service.NotificationService;

/**
 * NotificationKafkaConsumer — consomme les 3 topics cheque-service.
 *
 * Topics :
 *   cheque.uploaded    → dépôt reçu
 *   pipeline.completed → résultat IA (Bénéficiaire + Agent + Tireur)
 *   cheque.validated   → décision agent (Bénéficiaire + Tireur)
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class NotificationKafkaConsumer {

    private final NotificationService notificationService;

    @KafkaListener(
        topics = "cheque.uploaded",
        groupId = "notification-group",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void onChequeUploaded(
            @Payload ChequeEvent event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {
        log.info("Kafka reçu [{}] chequeId={}", topic, event.getChequeId());
        event.setTopic(topic);
        try {
            notificationService.notifierDepotRecu(event);
        } catch (Exception e) {
            log.error("Erreur traitement [cheque.uploaded] : {}", e.getMessage());
            // Ne pas relancer → Kafka ne retente pas (évite la boucle infinie)
        }
    }

    @KafkaListener(
        topics = "pipeline.completed",
        groupId = "notification-group",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void onPipelineCompleted(
            @Payload ChequeEvent event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {
        log.info("Kafka reçu [{}] chequeId={} decision={}",
            topic, event.getChequeId(), event.getDecisionFinale());
        event.setTopic(topic);
        try {
            notificationService.notifierResultatIA(event);
        } catch (Exception e) {
            log.error("Erreur traitement [pipeline.completed] : {}", e.getMessage());
        }
    }

    @KafkaListener(
        topics = "cheque.validated",
        groupId = "notification-group",
        containerFactory = "kafkaListenerContainerFactory"
    )
    public void onChequeValidated(
            @Payload ChequeEvent event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {
        log.info("Kafka reçu [{}] chequeId={} decision={}",
            topic, event.getChequeId(), event.getDecisionFinale());
        event.setTopic(topic);
        try {
            notificationService.notifierDecisionAgent(event);
        } catch (Exception e) {
            log.error("Erreur traitement [cheque.validated] : {}", e.getMessage());
        }
    }

    @KafkaListener(
        topics = "reclamation.created",
        groupId = "notification-group",
        containerFactory = "mapKafkaListenerContainerFactory"
    )
    public void onReclamationCreated(
            @Payload java.util.Map<String, Object> event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {
        String reclamationId = (String) event.get("reclamationId");
        String userId        = (String) event.get("userId");
        log.info("Kafka reçu [{}] reclamationId={} userId={}", topic, reclamationId, userId);
        try {
            notificationService.notifierReclamationCreee(event);
        } catch (Exception e) {
            log.error("Erreur traitement [reclamation.created] : {}", e.getMessage());
        }
    }

    @KafkaListener(
        topics = "reclamation.statut_change",
        groupId = "notification-group",
        containerFactory = "mapKafkaListenerContainerFactory"
    )
    public void onReclamationStatutChange(
            @Payload java.util.Map<String, Object> event,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {
        String reclamationId = (String) event.get("reclamationId");
        String userId        = (String) event.get("userId");
        String nouveauStatut = (String) event.get("nouveauStatut");
        log.info("Kafka reçu [{}] reclamationId={} userId={} statut={}",
            topic, reclamationId, userId, nouveauStatut);
        try {
            notificationService.notifierStatutReclamation(event);
        } catch (Exception e) {
            log.error("Erreur traitement [reclamation.statut_change] : {}", e.getMessage());
        }
    }
}
