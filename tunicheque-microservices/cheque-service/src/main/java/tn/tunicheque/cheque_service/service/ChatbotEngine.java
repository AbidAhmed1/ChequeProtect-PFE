package tn.tunicheque.cheque_service.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * ChatbotEngine — Machine d'états pour la collecte d'une réclamation.
 *
 * Flux :
 *   GREETING → ASKING_CHEQUE_NUMBER → ASKING_REFERENCE → ASKING_PROBLEM → CONFIRMING → DONE
 *
 * L'utilisateur décrit son problème de résultat, le bot collecte
 * le numéro de chèque et la référence du traitement, puis demande
 * une description avant de présenter un récapitulatif + bouton Soumettre.
 */
@Service
@Slf4j
public class ChatbotEngine {

    private final Map<String, ConversationState> sessions             = new ConcurrentHashMap<>();
    private final Map<String, String>            chequeNumbers        = new ConcurrentHashMap<>();
    private final Map<String, String>            references           = new ConcurrentHashMap<>();
    private final Map<String, String>            problemDescriptions  = new ConcurrentHashMap<>();

    // ── API publique ──────────────────────────────────────────────

    public BotResponse process(String userId, String intent, String langue, String originalMessage) {
        ConversationState state = sessions.getOrDefault(userId, ConversationState.GREETING);
        BotResponse response = route(intent, langue, state, userId, originalMessage);
        log.info("Chatbot : userId={} state={} intent={} → nextState={}",
            userId, state, intent, sessions.getOrDefault(userId, ConversationState.GREETING));
        return response;
    }

    public void resetSession(String userId)            { clearSession(userId); }

    public boolean isInState(String userId, ConversationState expected) {
        return expected == sessions.getOrDefault(userId, ConversationState.GREETING);
    }

    public String getChequeNumber(String userId)       { return chequeNumbers.get(userId); }
    public String getReference(String userId)          { return references.get(userId); }
    public String getProblemDescription(String userId) { return problemDescriptions.get(userId); }

    // ── Machine d'états ───────────────────────────────────────────

    private BotResponse route(String intent, String langue, ConversationState state,
                               String userId, String originalMessage) {

        // Annulation à tout moment
        if (GroqIntentService.ANNULATION.equals(intent)) {
            clearSession(userId);
            return respond(langue, CANCEL_MSG);
        }

        return switch (state) {
            case GREETING             -> handleGreeting(intent, langue, userId);
            case ASKING_CHEQUE_NUMBER -> handleChequeNumber(langue, userId, originalMessage);
            case ASKING_REFERENCE     -> handleReference(langue, userId, originalMessage);
            case ASKING_PROBLEM       -> handleProblem(langue, userId, originalMessage);
            case CONFIRMING           -> handleConfirming(langue, userId);
            case DONE -> {
                clearSession(userId);
                yield handleGreeting(intent, langue, userId);
            }
        };
    }

    private BotResponse handleGreeting(String intent, String langue, String userId) {
        // Salutation pure ou message incompréhensible → message de bienvenue
        if (GroqIntentService.SALUTATION.equals(intent) || GroqIntentService.INCONNU.equals(intent)) {
            sessions.put(userId, ConversationState.GREETING);
            return respond(langue, WELCOME_MSG);
        }
        // N'importe quel autre message (plainte, description, catégorie) → collecter le numéro de chèque
        sessions.put(userId, ConversationState.ASKING_CHEQUE_NUMBER);
        return respond(langue, ASK_CHEQUE_NUMBER_MSG);
    }

    private BotResponse handleChequeNumber(String langue, String userId, String originalMessage) {
        String num = originalMessage != null ? originalMessage.trim().replaceAll("\\s", "") : "";
        if (num.isEmpty()) return respond(langue, ASK_CHEQUE_NUMBER_MSG);
        if (!num.matches("\\d{7}")) return respond(langue, INVALID_CHEQUE_NUMBER_MSG);
        chequeNumbers.put(userId, num);
        sessions.put(userId, ConversationState.ASKING_REFERENCE);
        return respond(langue, ASK_REFERENCE_MSG);
    }

    private BotResponse handleReference(String langue, String userId, String originalMessage) {
        String ref = originalMessage != null ? originalMessage.trim() : "";
        if (ref.isEmpty()) return respond(langue, ASK_REFERENCE_MSG);
        references.put(userId, ref);
        sessions.put(userId, ConversationState.ASKING_PROBLEM);
        return respond(langue, ASK_PROBLEM_MSG);
    }

    private BotResponse handleProblem(String langue, String userId, String originalMessage) {
        String desc = originalMessage != null ? originalMessage.trim() : "";
        if (desc.length() < 5) return respond(langue, ASK_PROBLEM_MSG);
        problemDescriptions.put(userId, desc);
        sessions.put(userId, ConversationState.CONFIRMING);
        return new BotResponse(buildConfirmMsg(userId, langue), "RECLAMATION_READY", null);
    }

    private BotResponse handleConfirming(String langue, String userId) {
        // Session toujours active — la réclamation est déjà soumise automatiquement par le mobile
        // Si l'utilisateur tape quand même un message, on relance une nouvelle réclamation
        clearSession(userId);
        return handleGreeting("GREETING", langue, userId);
    }

    // ── Helpers ───────────────────────────────────────────────────

    private void clearSession(String userId) {
        sessions.remove(userId);
        chequeNumbers.remove(userId);
        references.remove(userId);
        problemDescriptions.remove(userId);
    }

    private String buildConfirmMsg(String userId, String langue) {
        String num = chequeNumbers.getOrDefault(userId, "—");
        String ref = references.getOrDefault(userId, "—");
        Map<String, String> msgs = Map.of(
            "fr",     "✅ Réclamation enregistrée avec succès.\n\n"
                    + "• Chèque n° : **" + num + "**\n"
                    + "• Référence traitement : **" + ref + "**\n\n"
                    + "Notre équipe vous contactera dans les plus brefs délais.",
            "en",     "✅ Complaint registered successfully.\n\n"
                    + "• Cheque n°: **" + num + "**\n"
                    + "• Treatment reference: **" + ref + "**\n\n"
                    + "Our team will contact you shortly.",
            "ar",     "✅ تم تسجيل شكواك بنجاح.\n\n"
                    + "• رقم الشيك: **" + num + "**\n"
                    + "• مرجع المعالجة: **" + ref + "**\n\n"
                    + "سيتواصل معك فريقنا في أقرب وقت.",
            "darija", "✅ Réclamation msajla b najah.\n\n"
                    + "• Numéro chèque: **" + num + "**\n"
                    + "• Référence: **" + ref + "**\n\n"
                    + "L'équipe mte3na tkalemk f akrab wakt momken."
        );
        return getMsg(langue, msgs);
    }

    private BotResponse respond(String langue, Map<String, String> messages) {
        return new BotResponse(getMsg(langue, messages), "GATHERING_INFO", null);
    }

    private String getMsg(String langue, Map<String, String> messages) {
        String l = langue != null ? langue : "fr";
        return messages.getOrDefault(l, messages.get("fr"));
    }

    // ── États ─────────────────────────────────────────────────────

    public enum ConversationState {
        GREETING, ASKING_CHEQUE_NUMBER, ASKING_REFERENCE, ASKING_PROBLEM, CONFIRMING, DONE
    }

    public record BotResponse(String reply, String intent, String selectedCategory) {}

    // ── Templates multilingues ────────────────────────────────────

    private static final Map<String, String> WELCOME_MSG = Map.of(
        "fr",     "Bonjour ! 👋 Je suis l'assistant TuniCheque.\n\n"
                + "Vous avez un problème avec le résultat du traitement d'un chèque ?\n"
                + "Décrivez-le et je vous aide à soumettre une réclamation.",
        "en",     "Hello! 👋 I'm the TuniCheque assistant.\n\n"
                + "Do you have an issue with a cheque processing result?\n"
                + "Describe it and I'll help you file a complaint.",
        "ar",     "مرحباً! 👋 أنا مساعد TuniCheque.\n\n"
                + "هل لديك مشكلة في نتيجة معالجة شيكك؟\n"
                + "صفها وسأساعدك في تقديم شكوى.",
        "darija", "Asslema! 👋 Ana l'assistant mta3 TuniCheque.\n\n"
                + "3andek mochkla m3a résultat mta3 chèque mte3ek?\n"
                + "Ahkili w na3awnek tsajjel réclamation."
    );

    private static final Map<String, String> ASK_CHEQUE_NUMBER_MSG = Map.of(
        "fr",     "Pour enregistrer votre réclamation, j'ai besoin de quelques informations.\n\n"
                + "Quel est le **numéro de votre chèque** ?",
        "en",     "To file your complaint, I need some information.\n\n"
                + "What is your **cheque number**?",
        "ar",     "لتسجيل شكواك، أحتاج بعض المعلومات.\n\n"
                + "ما هو **رقم شيكك**؟",
        "darija", "Bech nsajjel réclamation mte3ek, 7ajti ba3d el ma3loumet.\n\n"
                + "Chnou **numéro chèque** mte3ek?"
    );

    private static final Map<String, String> INVALID_CHEQUE_NUMBER_MSG = Map.of(
        "fr",     "❌ Le numéro de chèque doit contenir exactement **7 chiffres**.\n\n"
                + "Veuillez saisir uniquement des chiffres (ex : 1234567).",
        "en",     "❌ The cheque number must contain exactly **7 digits**.\n\n"
                + "Please enter digits only (e.g. 1234567).",
        "ar",     "❌ يجب أن يحتوي رقم الشيك على **7 أرقام** فقط.\n\n"
                + "يرجى إدخال أرقام فقط (مثال: 1234567).",
        "darija", "❌ Numéro chèque lazem ykoun **7 chiffres** bes.\n\n"
                + "Dkhel chiffres bes (ex: 1234567)."
    );

    private static final Map<String, String> ASK_REFERENCE_MSG = Map.of(
        "fr",     "Merci. Quelle est la **référence du traitement** ?\n"
                + "_(vous la trouvez dans votre historique de dépôts)_",
        "en",     "Thank you. What is the **treatment reference**?\n"
                + "_(you can find it in your deposit history)_",
        "ar",     "شكراً. ما هو **مرجع المعالجة**؟\n"
                + "_(يمكنك إيجاده في سجل إيداعاتك)_",
        "darija", "Merci. Chnou **référence mta3 traitement**?\n"
                + "_(Tlagehha f historique mta3 dépôts)_"
    );

    private static final Map<String, String> ASK_PROBLEM_MSG = Map.of(
        "fr",     "Décrivez brièvement le problème constaté :\n"
                + "_(ex : résultat « Fraude détectée » incorrect, signature non reconnue, montant erroné...)_",
        "en",     "Briefly describe the problem:\n"
                + "_(e.g. incorrect 'Fraud detected' result, unrecognized signature, wrong amount...)_",
        "ar",     "صف باختصار المشكلة التي لاحظتها:\n"
                + "_(مثال: نتيجة احتيال غير صحيحة، توقيع غير معترف به، مبلغ خاطئ...)_",
        "darija", "Ahkili fel qsir el mochkla li lqit:\n"
                + "_(ex: résultat 'Fraude' ghalet, imzé ma ta3refch, montant ghalet...)_"
    );

    private static final Map<String, String> THANKYOU_MSG = Map.of(
        "fr",     "✅ Votre réclamation a été enregistrée avec succès.\n"
                + "Notre équipe vous contactera dans les plus brefs délais.",
        "en",     "✅ Your complaint has been successfully registered.\n"
                + "Our team will contact you shortly.",
        "ar",     "✅ تم تسجيل شكواك بنجاح.\n"
                + "سيتواصل معك فريقنا في أقرب وقت.",
        "darija", "✅ Réclamation mte3ek msajla b najah.\n"
                + "L'équipe mte3na tkalemk f akrab wakt momken."
    );

    private static final Map<String, String> REMIND_SUBMIT_MSG = Map.of(
        "fr",     "⬆️ Cliquez sur le bouton **Soumettre** ci-dessus pour enregistrer votre réclamation.",
        "en",     "⬆️ Please click the **Submit** button above to register your complaint.",
        "ar",     "⬆️ الرجاء النقر على زر **إرسال** أعلاه لتسجيل شكواك.",
        "darija", "⬆️ Enzel 3la bouton **Soumettre** l fo9 bech tsajjel réclamation mte3ek."
    );

    private static final Map<String, String> CANCEL_MSG = Map.of(
        "fr",     "D'accord, réclamation annulée. N'hésitez pas à revenir si vous avez besoin d'aide.",
        "en",     "Alright, cancelled. Feel free to come back if you need help.",
        "ar",     "حسناً، تم الإلغاء. لا تتردد في العودة إذا احتجت مساعدة.",
        "darija", "Ok, annulé. Marahbe bik, nestanewk!"
    );
}