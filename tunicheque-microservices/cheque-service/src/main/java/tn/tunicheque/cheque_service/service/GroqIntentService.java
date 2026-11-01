package tn.tunicheque.cheque_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.List;
import java.util.Map;

/**
 * GroqIntentService — NLU gratuit via Groq API (Llama 3).
 *
 * Rôle unique : classifier l'intention du message client en JSON minimal.
 * Supporte FR / EN / AR / Darija tunisien automatiquement.
 *
 * Fallback : si Groq indisponible → détection par mots-clés Java.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class GroqIntentService {

    private final RestTemplate restTemplate;

    @Value("${groq.api-key}")
    private String groqKey;

    private static final String GROQ_URL = "https://api.groq.com/openai/v1/chat/completions";
    private static final String MODEL    = "llama-3.1-8b-instant";

    // Intents possibles
    public static final String SALUTATION           = "SALUTATION";
    public static final String VOULOIR_RECLAMATION  = "VOULOIR_RECLAMATION";
    public static final String CHEQUE_PERDU         = "CHEQUE_PERDU";
    public static final String MONTANT_INCORRECT    = "MONTANT_INCORRECT";
    public static final String CHEQUE_NON_ENCAISSE  = "CHEQUE_NON_ENCAISSE";
    public static final String DELAI_TROP_LONG      = "DELAI_TROP_LONG";
    public static final String FRAUDE               = "FRAUDE";
    public static final String AUTRE                = "AUTRE";
    public static final String DESCRIPTION_FOURNIE  = "DESCRIPTION_FOURNIE";
    public static final String CONFIRMATION         = "CONFIRMATION";
    public static final String ANNULATION           = "ANNULATION";
    public static final String HORS_SUJET           = "HORS_SUJET";
    public static final String INCONNU              = "INCONNU";

    /**
     * Appelle Groq pour classifier l'intent.
     * Retourne un intent parmi les constantes ci-dessus.
     */
    public IntentResult classify(String userMessage) {
        try {
            String prompt = buildClassificationPrompt(userMessage);

            HttpHeaders headers = new HttpHeaders();
            headers.set("Authorization", "Bearer " + groqKey);
            headers.setContentType(MediaType.APPLICATION_JSON);

            Map<String, Object> body = Map.of(
                "model",       MODEL,
                "max_tokens",  60,
                "temperature", 0,
                "messages",    List.of(Map.of("role", "user", "content", prompt))
            );

            @SuppressWarnings("unchecked")
            Map<String, Object> resp = restTemplate.postForEntity(
                GROQ_URL, new HttpEntity<>(body, headers), Map.class
            ).getBody();

            String raw = extractGroqText(resp);
            IntentResult result = parseIntentJson(raw, userMessage);
            log.info("Groq NLU : message='{}' → intent={} langue={}", userMessage, result.intent(), result.langue());
            return result;

        } catch (Exception e) {
            log.warn("Groq indisponible ({}), fallback keywords", e.getMessage());
            return fallbackKeywords(userMessage);
        }
    }

    // ── Prompt minimal pour Groq ──────────────────────────────────

    private String buildClassificationPrompt(String msg) {
        return """
            You are classifying messages for a Tunisian banking chatbot that handles complaints (réclamations).
            The user may write in French, English, Arabic, or Tunisian Darija (mixed Arabic-French).

            Darija hints: "dha3/ضاع"=lost, "ghalta"=error/wrong, "mte3i"=my, "9alouli"=they told me,
            "frauda/fraude/falsifié/mouch sahih"=fraud/fake, "bati/rzina"=slow, "tsarraf/tsaref"=encash,
            "naam/ayeh/yessir"=yes, "la/non"=no, "mouch/mech/ma...ch"=not/negation.

            Choose EXACTLY ONE intent:
            - SALUTATION: greeting only (bonjour, asslema, hello, salam) with NO complaint
            - VOULOIR_RECLAMATION: wants to complain but no specific category yet
              (examples: "je veux faire une réclamation", "n7eb na3mel réclamation", "kifeh n3adi réclamation",
               "je veux passer une réclamation sur le résultat", "j'ai un problème avec mon chèque")
            - CHEQUE_PERDU: cheque physically lost (dha3, perdu, mfqoud, lost, disparu)
              NOT for fraud — only if the cheque is missing/cannot be found
            - MONTANT_INCORRECT: wrong amount (ghalta fel montant, montant incorrect, مبلغ غلط, somme erreur)
            - CHEQUE_NON_ENCAISSE: cheque not cashed (ma tsarefch, ma tsarrafch, non encaissé, لم يُصرف)
            - DELAI_TROP_LONG: processing too slow (bati, rzina, tardif, lent, délai long)
            - FRAUDE: fraud OR falsification suspected
              (fraude, frauda, falsifié, falsification, احتيال, موش حقيقي, "9alouli rahou fraude",
               "ils disent que c'est falsifié", "mouch sahih", "contrefait")
            - AUTRE: other complaint not fitting above
            - DESCRIPTION_FOURNIE: user describes their problem in detail — a statement (NOT a question)
              (examples: "mon chèque du 01/05 montant 500DT", "ils m'ont dit que j'ai un problème de signature",
               "j'ai déposé le chèque le 3 mai et rien n'a été fait")
            - CONFIRMATION: yes/agreement (oui, naam, ayeh, ok, d'accord, yessir, mleh)
            - ANNULATION: cancel/no (non, la, annuler, cancel, barkha)
            - HORS_SUJET: general app usage questions, NOT a complaint
              (examples: "comment déposer un chèque", "kifeh na3mel test", "c'est quoi TuniCheque",
               "déposer un cheque", "how does this work", "comment ça marche")

            CRITICAL RULES:
            - "déposer un chèque" alone → HORS_SUJET (it's a process question, not a complaint)
            - "falsifié" or "falsification" → always FRAUDE, never CHEQUE_PERDU
            - "je veux faire/passer une réclamation" → VOULOIR_RECLAMATION
            - "kifeh n3adi réclamation" → VOULOIR_RECLAMATION
            - Message with greeting + complaint category → use the category, not SALUTATION
            - DESCRIPTION_FOURNIE only for statements explaining a problem, never questions

            Message: "%s"

            Respond ONLY with valid JSON:
            {"intent":"INTENT_HERE","langue":"fr|en|ar|darija"}
            """.formatted(msg);
    }

    // ── Parsing de la réponse Groq ────────────────────────────────

    @SuppressWarnings("unchecked")
    private String extractGroqText(Map<String, Object> resp) {
        if (resp == null) return "";
        List<Map<String, Object>> choices = (List<Map<String, Object>>) resp.get("choices");
        if (choices == null || choices.isEmpty()) return "";
        Map<String, Object> message = (Map<String, Object>) choices.get(0).get("message");
        if (message == null) return "";
        Object content = message.get("content");
        return content != null ? content.toString().trim() : "";
    }

    private IntentResult parseIntentJson(String raw, String originalMsg) {
        try {
            // Extraire l'intent du JSON retourné par Groq
            String intent = extractJsonField(raw, "intent");
            String langue = extractJsonField(raw, "langue");
            if (intent != null && isValidIntent(intent)) {
                return new IntentResult(intent, langue != null ? langue : "fr");
            }
        } catch (Exception e) {
            log.warn("Parsing JSON Groq échoué pour : {}", raw);
        }
        return fallbackKeywords(originalMsg);
    }

    private String extractJsonField(String json, String field) {
        String key = "\"" + field + "\":\"";
        int start = json.indexOf(key);
        if (start == -1) return null;
        start += key.length();
        int end = json.indexOf("\"", start);
        if (end == -1) return null;
        return json.substring(start, end);
    }

    private boolean isValidIntent(String intent) {
        return List.of(SALUTATION, VOULOIR_RECLAMATION, CHEQUE_PERDU, MONTANT_INCORRECT,
            CHEQUE_NON_ENCAISSE, DELAI_TROP_LONG, FRAUDE, AUTRE, DESCRIPTION_FOURNIE,
            CONFIRMATION, ANNULATION, HORS_SUJET, INCONNU).contains(intent);
    }

    // ── Fallback mots-clés (si Groq indisponible) ─────────────────

    private IntentResult fallbackKeywords(String msg) {
        String m = msg.toLowerCase();

        if (m.matches(".*\\b(bonjour|salut|hello|hi|asslema|ahlan|salam|مرحبا|سلام)\\b.*"))
            return new IntentResult(SALUTATION, "fr");
        if (m.matches(".*\\b(reclamation|réclamation|plainte|problème|problem|شكوى)\\b.*"))
            return new IntentResult(VOULOIR_RECLAMATION, "fr");
        if (m.contains("perdu") || m.contains("ضاع") || m.contains("mfqoud") || m.contains("lost"))
            return new IntentResult(CHEQUE_PERDU, "fr");
        if (m.contains("montant") || m.contains("مبلغ") || m.contains("incorrect") || m.contains("غلط"))
            return new IntentResult(MONTANT_INCORRECT, "fr");
        if (m.contains("encaiss") || m.contains("tsarraf") || m.contains("تصرف"))
            return new IntentResult(CHEQUE_NON_ENCAISSE, "fr");
        if (m.contains("délai") || m.contains("tard") || m.contains("lent") || m.contains("bati"))
            return new IntentResult(DELAI_TROP_LONG, "fr");
        if (m.matches(".*\\b(oui|yes|naam|ayeh|d.accord|ok|ياها)\\b.*"))
            return new IntentResult(CONFIRMATION, "fr");
        if (m.matches(".*\\b(non|no|la|cancel|annul)\\b.*"))
            return new IntentResult(ANNULATION, "fr");
        if (msg.length() > 30)
            return new IntentResult(DESCRIPTION_FOURNIE, "fr");

        return new IntentResult(INCONNU, "fr");
    }

    public record IntentResult(String intent, String langue) {}
}