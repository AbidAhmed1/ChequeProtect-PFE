package tn.tunicheque.notification_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import tn.tunicheque.notification_service.entity.Notification;
import tn.tunicheque.notification_service.entity.Notification.NotificationType;
import tn.tunicheque.notification_service.kafka.ChequeEvent;
import tn.tunicheque.notification_service.repository.NotificationRepository;

import java.util.UUID;

/**
 * NotificationService — orchestrateur central.
 *
 * Gère 3 topics Kafka :
 *   cheque.uploaded     → Bénéficiaire : dépôt reçu
 *   pipeline.completed  → Bénéficiaire + Agent + Tireur : résultat IA
 *   cheque.validated    → Bénéficiaire + Tireur : décision finale agent
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class NotificationService {

    private final EmailService          emailService;
    private final AuthServiceClient     authClient;
    private final NotificationRepository repo;

    // ══ Topic 1 : cheque.uploaded ═════════════════════════════════
    // Destinataire : Bénéficiaire uniquement

    public void notifierDepotRecu(ChequeEvent event) {
        log.info("[cheque.uploaded] chequeId={} bénéficiaireId={}",
            event.getChequeId(), event.getBeneficiaireId());

        String email = authClient.getEmail(event.getBeneficiaireId());
        String sujet = "ChèqueProtect — Dépôt de chèque reçu";
        String corps = buildDepotRecu(event);

        envoyerEtSauvegarder(email, sujet, corps,
            event.getBeneficiaireId(), event.getChequeId(),
            "BENEFICIAIRE", "cheque.uploaded");
    }

    // ══ Topic 2 : pipeline.completed ═════════════════════════════
    // Destinataires : Bénéficiaire + Agent + Tireur (si présent)

    public void notifierResultatIA(ChequeEvent event) {
        log.info("[pipeline.completed] chequeId={} decision={}",
            event.getChequeId(), event.getDecisionFinale());

        // → Bénéficiaire
        String emailBenef = authClient.getEmail(event.getBeneficiaireId());
        String sujetBenef = "ChèqueProtect — Analyse de votre chèque terminée";
        String corpsBenef = buildResultatIA(event, "BENEFICIAIRE");
        envoyerEtSauvegarder(emailBenef, sujetBenef, corpsBenef,
            event.getBeneficiaireId(), event.getChequeId(),
            "BENEFICIAIRE", "pipeline.completed");

        // → Agent
        String emailAgent = authClient.getEmail(event.getAgentId());
        String sujetAgent = "ChèqueProtect — Nouveau chèque à évaluer";
        String corpsAgent = buildResultatIA(event, "AGENT");
        envoyerEtSauvegarder(emailAgent, sujetAgent, corpsAgent,
            event.getAgentId(), event.getChequeId(),
            "AGENT", "pipeline.completed");

        // → Tireur (si connu)
        if (event.getTireurId() != null && !event.getTireurId().isBlank()) {
            String emailTireur = authClient.getEmail(event.getTireurId());
            String sujetTireur = "ChèqueProtect — Statut de votre chèque émis";
            String corpsTireur = buildResultatIA(event, "TIREUR");
            envoyerEtSauvegarder(emailTireur, sujetTireur, corpsTireur,
                event.getTireurId(), event.getChequeId(),
                "TIREUR", "pipeline.completed");
        }
    }

    // ══ Topic 3 : cheque.validated ════════════════════════════════
    // Destinataires : Bénéficiaire + Tireur

    public void notifierDecisionAgent(ChequeEvent event) {
        log.info("[cheque.validated] chequeId={} decision={}",
            event.getChequeId(), event.getDecisionFinale());

        // → Bénéficiaire
        String emailBenef = authClient.getEmail(event.getBeneficiaireId());
        String sujetBenef = buildSujetDecision(event, "BENEFICIAIRE");
        String corpsBenef = buildDecisionAgent(event, "BENEFICIAIRE");
        envoyerEtSauvegarder(emailBenef, sujetBenef, corpsBenef,
            event.getBeneficiaireId(), event.getChequeId(),
            "BENEFICIAIRE", "cheque.validated");

        // → Tireur (si connu)
        if (event.getTireurId() != null && !event.getTireurId().isBlank()) {
            String emailTireur = authClient.getEmail(event.getTireurId());
            String sujetTireur = buildSujetDecision(event, "TIREUR");
            String corpsTireur = buildDecisionAgent(event, "TIREUR");
            envoyerEtSauvegarder(emailTireur, sujetTireur, corpsTireur,
                event.getTireurId(), event.getChequeId(),
                "TIREUR", "cheque.validated");
        }
    }

    // ── Envoi + historique ────────────────────────────────────────

    private void envoyerEtSauvegarder(String email, String sujet, String corps,
            String userId, String chequeId, String role, String topic) {

        Notification.NotificationBuilder builder = Notification.builder()
            .chequeId(chequeId)
            .userRole(role)
            .type(NotificationType.PUSH)
            .sujet(sujet)
            .contenu(corps)
            .kafkaTopic(topic)
            .statut("PENDING");

        try {
            if (userId != null && !userId.isBlank())
                builder.userId(UUID.fromString(userId));
        } catch (Exception e) {
            log.warn("userId invalide={} : {}", userId, e.getMessage());
            return;
        }

        // 1. Sauvegarder en base IMMÉDIATEMENT → notification in-app visible tout de suite
        Notification notif;
        try {
            notif = repo.save(builder.build());
        } catch (Exception e) {
            log.error("Impossible de sauvegarder la notification userId={} : {}", userId, e.getMessage());
            return;
        }

        // 2. Envoyer l'email (si disponible) — ne bloque pas l'in-app
        if (email == null || email.isBlank()) {
            log.warn("Email introuvable pour userId={} — email non envoyé, in-app OK", userId);
            notif.setStatut("ENVOYE");
            repo.save(notif);
            return;
        }

        try {
            emailService.envoyer(email, sujet, corps);
            notif.setStatut("ENVOYE");
        } catch (Exception e) {
            log.error("Echec email à {} : {}", email, e.getMessage());
            notif.setStatut("ECHEC");
            notif.setErrorMessage(e.getMessage());
        }
        repo.save(notif);
    }

    // ── Corps des emails ──────────────────────────────────────────

    private String buildDepotRecu(ChequeEvent e) {
        return String.format(
            "Bonjour %s,\n\n" +
            "Votre chèque a bien été reçu et est en cours d'analyse.\n\n" +
            "Référence : %s\n" +
            "Montant   : %s DT\n\n" +
            "Vous serez notifié dès que l'analyse sera terminée.\n\n" +
            "Cordialement,\nTuniCheque",
            e.getBeneficiaireNom() != null ? e.getBeneficiaireNom() : "Client",
            e.getChequeId(),
            e.getMontant() != null ? e.getMontant().toString() : "—");
    }

    private String buildResultatIA(ChequeEvent e, String role) {
        String decision = e.getDecisionFinale() != null ? e.getDecisionFinale() : "EN_COURS";
        boolean rejete = decision.startsWith("REJECTED");
        boolean valide = decision.equals("COMPLIANCE_OK") || decision.equals("APPROVED");

        if ("AGENT".equals(role)) {
            return String.format(
                "Nouveau chèque à évaluer.\n\n" +
                "ID       : %s\n" +
                "Décision IA : %s\n" +
                "Montant  : %s DT\n\n" +
                "Connectez-vous pour valider ou rejeter ce chèque.",
                e.getChequeId(), decision,
                e.getMontant() != null ? e.getMontant() : "—");
        }

        String etatMsg = valide
            ? "L'analyse automatique indique que votre chèque est conforme."
            : rejete
                ? "L'analyse a détecté un problème : " + formatDecision(decision)
                : "Votre chèque est en attente de validation par un agent.";

        return String.format(
            "Bonjour,\n\n" +
            "L'analyse de votre chèque est terminée.\n\n" +
            "Référence : %s\n" +
            "Montant   : %s DT\n" +
            "Résultat  : %s\n\n" +
            "%s\n\n" +
            "Cordialement,\nTuniCheque",
            e.getChequeId(),
            e.getMontant() != null ? e.getMontant() : "—",
            decision, etatMsg);
    }

    private String buildDecisionAgent(ChequeEvent e, String role) {
        boolean valide = "VALIDE".equals(e.getDecisionFinale());
        String contexte = "TIREUR".equals(role)
            ? "Le chèque que vous avez émis"
            : "Votre chèque déposé";

        return String.format(
            "Bonjour,\n\n" +
            "%s a été %s par notre équipe.\n\n" +
            "Référence : %s\n" +
            "Montant   : %s DT\n" +
            "Décision  : %s\n" +
            "%s\n\n" +
            "Cordialement,\nTuniCheque",
            contexte,
            valide ? "VALIDÉ" : "REJETÉ",
            e.getChequeId(),
            e.getMontant() != null ? e.getMontant() : "—",
            e.getDecisionFinale(),
            e.getMotifRejet() != null ? "Motif : " + e.getMotifRejet() : "");
    }

    private String buildSujetDecision(ChequeEvent e, String role) {
        boolean valide = "VALIDE".equals(e.getDecisionFinale());
        return valide
            ? "ChèqueProtect — ✅ Chèque validé"
            : "ChèqueProtect — ❌ Chèque rejeté";
    }

    // ══ Topic 4 : reclamation.created ════════════════════════════
    // Destinataire : Client (confirmation) + Admin (alerte)

    public void notifierReclamationCreee(java.util.Map<String, Object> event) {
        String userId        = (String) event.get("userId");
        String objet         = (String) event.getOrDefault("objet", "Réclamation");
        String reclamationId = (String) event.getOrDefault("reclamationId", "—");

        log.info("[reclamation.created] userId={} objet={}", userId, objet);

        // → Client : confirmation de réception
        String emailClient = authClient.getEmail(userId);
        String sujetClient = "ChèqueProtect — Réclamation enregistrée";
        String corpsClient = String.format(
            "Bonjour,\n\n" +
            "Votre réclamation a bien été enregistrée.\n\n" +
            "Référence : %s\n" +
            "Sujet     : %s\n\n" +
            "Notre équipe vous répondra dans les plus brefs délais.\n\n" +
            "Cordialement,\nTuniCheque",
            reclamationId, objet);

        envoyerEtSauvegarder(emailClient, sujetClient, corpsClient,
            userId, null, "CLIENT", "reclamation.created");
    }

    // ══ Topic 5 : reclamation.statut_change ══════════════════════
    // Destinataire : Client (notification du changement de statut)

    public void notifierStatutReclamation(java.util.Map<String, Object> event) {
        String userId        = (String) event.get("userId");
        String objet         = (String) event.getOrDefault("objet", "Réclamation");
        String reclamationId = (String) event.getOrDefault("reclamationId", "—");
        String nouveauStatut = (String) event.getOrDefault("nouveauStatut", "");
        String reponseAgent  = (String) event.getOrDefault("reponseAgent", "");

        log.info("[reclamation.statut_change] userId={} statut={}", userId, nouveauStatut);

        String sujet = statutToSujet(nouveauStatut);
        String corps = buildStatutChange(reclamationId, objet, nouveauStatut, reponseAgent);

        String emailClient = authClient.getEmail(userId);
        envoyerEtSauvegarder(emailClient, sujet, corps,
            userId, null, "CLIENT", "reclamation.statut_change");
    }

    private String statutToSujet(String statut) {
        return switch (statut) {
            case "EN_COURS"  -> "ChèqueProtect — Votre réclamation est en cours de traitement";
            case "TRANSMISE" -> "ChèqueProtect — Votre réclamation a été prise en charge";
            case "RESOLUE"   -> "ChèqueProtect — Votre réclamation a été résolue";
            case "FERMEE"    -> "ChèqueProtect — Votre réclamation a été clôturée";
            default          -> "ChèqueProtect — Mise à jour de votre réclamation";
        };
    }

    private String buildStatutChange(String reclamationId, String objet,
                                     String nouveauStatut, String reponseAgent) {
        String statutMsg = switch (nouveauStatut) {
            case "EN_COURS"  -> "est en cours de traitement par notre équipe.";
            case "TRANSMISE" -> "a été prise en charge et traitée par notre équipe. Aucune action supplémentaire n'est requise de votre part.";
            case "RESOLUE"   -> "a été résolue. Nous espérons avoir répondu à votre demande.";
            case "FERMEE"    -> "a été clôturée.";
            default          -> "a été mise à jour (statut : " + nouveauStatut + ").";
        };

        String reponseSection = (reponseAgent != null && !reponseAgent.isBlank())
            ? "\nRéponse de notre équipe :\n" + reponseAgent + "\n"
            : "";

        return String.format(
            "Bonjour,\n\n" +
            "Votre réclamation %s\n\n" +
            "Référence : %s\n" +
            "Sujet     : %s\n" +
            "Statut    : %s\n" +
            "%s\n" +
            "Cordialement,\nTuniCheque",
            statutMsg, reclamationId, objet, nouveauStatut, reponseSection);
    }

    private String formatDecision(String decision) {
        return switch (decision) {
            case "REJECTED_CHEQUE_PERIME"     -> "chèque périmé (délai dépassé)";
            case "REJECTED_FALSIFICATION"      -> "données incohérentes (possible falsification)";
            case "REJECTED_PRINTED_CHEQUE"     -> "chèque imprimé sur papier ordinaire";
            case "REJECTED_RIB_INVALIDE"       -> "RIB invalide";
            case "REJECTED_BANQUE_INVALIDE"    -> "code banque non reconnu BCT";
            case "REJECTED_NOT_A_CHEQUE"       -> "document non reconnu";
            default -> decision;
        };
    }
}
