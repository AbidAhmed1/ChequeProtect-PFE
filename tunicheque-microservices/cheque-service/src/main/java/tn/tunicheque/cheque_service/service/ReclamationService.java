package tn.tunicheque.cheque_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import tn.tunicheque.cheque_service.dto.request.ChatMessage;
import tn.tunicheque.cheque_service.dto.request.CreateReclamationRequest;
import tn.tunicheque.cheque_service.dto.response.ChatResponse;
import tn.tunicheque.cheque_service.dto.response.ReclamationAdminDTO;
import tn.tunicheque.cheque_service.entity.Reclamation;
import tn.tunicheque.cheque_service.kafka.ReclamationKafkaProducer;
import tn.tunicheque.cheque_service.repository.ReclamationRepository;
import tn.tunicheque.cheque_service.service.AuthServiceClient.ClientInfo;
import tn.tunicheque.cheque_service.service.GroqIntentService.IntentResult;
import tn.tunicheque.cheque_service.service.ChatbotEngine.BotResponse;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * ReclamationService — orchestre NLU (Groq) + ChatbotEngine structuré.
 *
 * Flux chat :
 *   1. Groq classifie l'intent (pour détecter salutation / annulation)
 *   2. ChatbotEngine guide l'utilisateur : numéro chèque → référence → description
 *   3. Quand intent = RECLAMATION_READY → frontend affiche le bouton Soumettre
 *   4. Clic Soumettre → POST /api/reclamations → createReclamation()
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class ReclamationService {

    private final ReclamationRepository    reclamationRepo;
    private final ReclamationKafkaProducer kafkaProducer;
    private final NotificationHttpClient   notificationClient;
    private final GroqIntentService        groqIntentService;
    private final ChatbotEngine            chatbotEngine;
    private final AuthServiceClient        authServiceClient;

    // ══ Chat : Groq NLU → ChatbotEngine structuré ════════════════

    public ChatResponse chat(String userId, ChatMessage msg) {
        IntentResult nlu = groqIntentService.classify(msg.getMessage());
        BotResponse bot  = chatbotEngine.process(userId, nlu.intent(), nlu.langue(), msg.getMessage());

        log.info("Chat userId={} intent={} langue={} chatIntent={}",
            userId, nlu.intent(), nlu.langue(), bot.intent());

        return new ChatResponse(bot.reply(), bot.intent());
    }

    // ══ Création réclamation via bouton Soumettre ══════════════════

    public Reclamation createReclamation(String userId, CreateReclamationRequest req) {
        // Les données viennent de la session chatbot (toujours en état CONFIRMING côté frontend)
        String chequeNum   = chatbotEngine.getChequeNumber(userId);
        String reference   = chatbotEngine.getReference(userId);
        String problemDesc = chatbotEngine.getProblemDescription(userId);

        // Fallback sur le contenu de la requête si la session a expiré
        if (chequeNum == null && req.getDescription() != null) {
            chequeNum   = req.getChequeId();
            problemDesc = req.getDescription();
        }

        return createReclamationFromData(userId, chequeNum, reference, problemDesc);
    }

    // ── Méthode interne ────────────────────────────────────────────

    private Reclamation createReclamationFromData(String userId,
                                                   String chequeNum,
                                                   String reference,
                                                   String problemDesc) {
        StringBuilder desc = new StringBuilder();
        if (chequeNum != null && !chequeNum.isBlank())
            desc.append("Numéro de chèque : ").append(chequeNum).append("\n");
        if (reference != null && !reference.isBlank())
            desc.append("Référence traitement : ").append(reference).append("\n");
        if (problemDesc != null && !problemDesc.isBlank())
            desc.append("Problème : ").append(problemDesc);

        String finalDesc   = desc.toString().trim();
        String finalCheque = reference != null && !reference.isBlank() ? reference : chequeNum;

        Reclamation recl = Reclamation.builder()
            .userId(UUID.fromString(userId))
            .chequeId(finalCheque)
            .objet("Problème de résultat de traitement")
            .description(finalDesc.isEmpty() ? "—" : finalDesc)
            .statut("OUVERTE")
            .build();

        recl = reclamationRepo.save(recl);
        kafkaProducer.publishReclamationCreated(
            recl.getId(), UUID.fromString(userId), "Problème de résultat de traitement");

        // Notification HTTP directe → in-app mobile immédiate
        notificationClient.send(
            userId, null, "BENEFICIAIRE",
            "ChèqueProtect — Réclamation enregistrée",
            "Réclamation bien reçue et résolue.",
            "reclamation.created");

        chatbotEngine.resetSession(userId);
        log.info("Réclamation créée : id={} userId={} cheque={}", recl.getId(), userId, finalCheque);
        return recl;
    }

    // ══ Admin : liste enrichie avec infos client ══════════════════

    public List<ReclamationAdminDTO> findAll() {
        return reclamationRepo.findAllByOrderByCreatedAtDesc().stream()
            .map(r -> {
                ClientInfo info = r.getUserId() != null
                    ? authServiceClient.getClientInfo(r.getUserId())
                    : new ClientInfo("—", "—", "—");
                return ReclamationAdminDTO.from(r, info.fullName(), info.identifier(), info.identifierType());
            })
            .toList();
    }

    // ══ Admin : transmettre au service client ═════════════════════

    public void transmit(UUID id) {
        updateStatut(id, "TRANSMISE", null);
    }

    // ══ Admin : mettre à jour le statut + notifier le client ══════

    public Reclamation updateStatut(UUID id, String nouveauStatut, String reponseAgent) {
        Reclamation r = reclamationRepo.findById(id)
            .orElseThrow(() -> new RuntimeException("Réclamation introuvable : " + id));

        String ancienStatut = r.getStatut();
        r.setStatut(nouveauStatut);
        r.setUpdatedAt(LocalDateTime.now());
        if (reponseAgent != null && !reponseAgent.isBlank()) {
            r.setReponseAgent(reponseAgent);
        }
        reclamationRepo.save(r);

        kafkaProducer.publishStatutChange(
            r.getId(), r.getUserId(), r.getObjet(),
            ancienStatut, nouveauStatut, r.getReponseAgent());

        // Notification HTTP directe → in-app mobile (ne dépend pas de Kafka)
        if (r.getUserId() != null) {
            String sujet   = statutToSujet(nouveauStatut);
            String contenu = statutToContenu(nouveauStatut, r.getReponseAgent());
            notificationClient.send(
                r.getUserId().toString(), null, "BENEFICIAIRE",
                sujet, contenu, "reclamation.statut_change");
        }

        log.info("Réclamation statut changé : id={} {} → {}", id, ancienStatut, nouveauStatut);
        return r;
    }

    private String statutToSujet(String statut) {
        return switch (statut) {
            case "EN_COURS"  -> "ChèqueProtect — Réclamation en cours de traitement";
            case "TRANSMISE" -> "ChèqueProtect — Réclamation prise en charge";
            case "RESOLUE"   -> "ChèqueProtect — Réclamation résolue";
            case "FERMEE"    -> "ChèqueProtect — Réclamation clôturée";
            default          -> "ChèqueProtect — Mise à jour de votre réclamation";
        };
    }

    private String statutToContenu(String statut, String reponseAgent) {
        String base = switch (statut) {
            case "EN_COURS"  -> "Votre réclamation est en cours de traitement par notre équipe.";
            case "TRANSMISE" -> "Réclamation bien reçue et résolue.";
            case "RESOLUE"   -> "Votre réclamation a été résolue.";
            case "FERMEE"    -> "Votre réclamation a été clôturée.";
            default          -> "Votre réclamation a été mise à jour.";
        };
        if (reponseAgent != null && !reponseAgent.isBlank())
            base += " Réponse : " + reponseAgent;
        return base;
    }
}
