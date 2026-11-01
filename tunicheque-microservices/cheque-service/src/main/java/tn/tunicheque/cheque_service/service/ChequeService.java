package tn.tunicheque.cheque_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;
import tn.tunicheque.cheque_service.entity.AiResult;
import tn.tunicheque.cheque_service.entity.Cheque;
import tn.tunicheque.cheque_service.repository.AiResultRepository;
import tn.tunicheque.cheque_service.repository.ChequeRepository;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import tn.tunicheque.cheque_service.dto.response.MobileStatsDTO;

@Service
@RequiredArgsConstructor
@Slf4j
public class ChequeService {

    private final ChequeRepository       chequeRepository;
    private final AiResultRepository     aiResultRepository;
    private final NotificationHttpClient notificationClient;
    private final AuthServiceClient      authServiceClient;
    private final RestTemplate           restTemplate;

    @Value("${ai.service.url}")
    private String aiServiceUrl;

    @Value("${storage.upload-dir}")
    private String uploadDir;

    // ─── Upload + Pipeline IA ──────────────────────────────────────────────

    public Cheque uploadAndProcess(MultipartFile recto,
                                   MultipartFile verso,
                                   UUID beneficiaireId,
                                   String source) throws IOException {

        // 1. Lire les bytes avant de sauvegarder (nécessaire avant l'async)
        final byte[] rectoBytes   = recto.getBytes();
        final String rectoName    = recto.getOriginalFilename();
        final byte[] versoBytes   = (verso != null && !verso.isEmpty()) ? verso.getBytes()            : null;
        final String versoName    = (verso != null && !verso.isEmpty()) ? verso.getOriginalFilename() : null;

        // 2. Sauvegarder les images
        String rectoUrl = saveFileBytes(rectoBytes, rectoName, "recto");
        String versoUrl = versoBytes != null ? saveFileBytes(versoBytes, versoName, "verso") : null;

        // 3. Créer le chèque en base
        boolean isWeb = "WEB".equalsIgnoreCase(source);
        Cheque cheque = Cheque.builder()
                .imageRectoUrl(rectoUrl)
                .imageVersoUrl(versoUrl)
                .beneficiaireId(beneficiaireId)
                .source(source != null ? source : "MOBILE")
                .status(isWeb ? Cheque.ChequeStatus.EN_TRAITEMENT : Cheque.ChequeStatus.EN_ATTENTE)
                .build();
        cheque = chequeRepository.save(cheque);
        log.info("Chèque reçu ({}) : {}", cheque.getStatus(), cheque.getId());

        if (isWeb) {
            // 4a. WEB : pipeline IA déclenché immédiatement en arrière-plan
            final UUID finalId = cheque.getId();
            java.util.concurrent.CompletableFuture.runAsync(() -> {
                try {
                    Cheque fresh = chequeRepository.findById(finalId).orElseThrow();
                    callAiPipelineWithBytes(fresh, rectoBytes, rectoName, versoBytes, versoName);
                    log.info("Pipeline WEB terminé — chèque {}", finalId);
                } catch (Exception e) {
                    log.error("Pipeline WEB échoué — chèque {} : {}", finalId, e.getMessage());
                    chequeRepository.findById(finalId).ifPresent(c -> {
                        c.setStatus(Cheque.ChequeStatus.EN_ATTENTE);
                        chequeRepository.save(c);
                    });
                }
            });
        } else {
            // 4b. MOBILE : notifier le bénéficiaire, pipeline déclenché par l'agent
            notificationClient.send(
                beneficiaireId != null ? beneficiaireId.toString() : null,
                cheque.getId().toString(), "BENEFICIAIRE",
                "ChèqueProtect — Chèque déposé avec succès",
                "Votre chèque a été reçu et sera traité par un agent. Référence : " + cheque.getId(),
                "cheque.uploaded");
        }

        return cheque;
    }

    // ─── Appel FastAPI : POST /api/ai/pipeline ─────────────────────────────
    //
    // Fields: recto (file), verso (file), cheque_id (string), source (string)

    private Cheque callAiPipeline(Cheque cheque,
                                  MultipartFile recto,
                                  MultipartFile verso) throws IOException {
        byte[] versoBytes = verso != null && !verso.isEmpty() ? verso.getBytes() : null;
        String versoName  = verso != null && !verso.isEmpty() ? verso.getOriginalFilename() : null;
        return callAiPipelineWithBytes(cheque, recto.getBytes(), recto.getOriginalFilename(), versoBytes, versoName);
    }

    @SuppressWarnings("unchecked")
    private Cheque callAiPipelineWithBytes(Cheque cheque,
                                           byte[] rectoBytes, String rectoFilename,
                                           byte[] versoBytes, String versoFilename) {
        log.info("→ Pipeline IA : {}/api/ai/pipeline [cheque={}]",
                aiServiceUrl, cheque.getId());
        long start = System.currentTimeMillis();

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();

        final String rName = rectoFilename != null ? rectoFilename : "recto.jpg";
        body.add("recto", new ByteArrayResource(rectoBytes) {
            @Override public String getFilename() { return rName; }
        });

        if (versoBytes != null) {
            final String vName = versoFilename != null ? versoFilename : "verso.jpg";
            body.add("verso", new ByteArrayResource(versoBytes) {
                @Override public String getFilename() { return vName; }
            });
        }

        body.add("cheque_id", cheque.getId().toString());
        body.add("source",    "mobile");

        HttpEntity<MultiValueMap<String, Object>> request = new HttpEntity<>(body, headers);

        ResponseEntity<Map> response = restTemplate.exchange(
                aiServiceUrl + "/api/ai/pipeline",
                HttpMethod.POST, request, Map.class);

        Map<String, Object> result = response.getBody();
        if (result == null) throw new RuntimeException("Réponse vide du Pipeline IA");

        long duration = System.currentTimeMillis() - start;
        log.info("← Pipeline IA terminé en {}ms — décision : {}",
                duration, result.get("final_decision"));

        return parseAndSaveResult(cheque, result, (int) duration);
    }

    // ─── Parser la réponse FastAPI ─────────────────────────────────────────
    //
    // {
    //   "cheque_id": "...",
    //   "final_decision": "PENDING_REVIEW_QR",
    //   "total_time_ms": 17394,
    //   "phases": {
    //     "identification": { "score": 0.53, "passed": true, "duration_ms": 2856, "details": {...} },
    //     "compliance":     { "score": 0,    "passed": true,  "details": { "qr_data": null, ... } },
    //     "ocr":            { "score": 0,    "passed": false, "details": { "extracted": {
    //                             "montant_chiffres": null,
    //                             "montant_lettres": null,
    //                             "beneficiaire": null } } },
    //     "signature":      { "score": 0.5,  "passed": true,  "details": { "decision": "REVIEW" } }
    //   }
    // }

    @SuppressWarnings("unchecked")
    private Cheque parseAndSaveResult(Cheque cheque,
                                      Map<String, Object> result,
                                      int durationMs) {

        String finalDecision = (String) result.getOrDefault("final_decision", "EN_ATTENTE");
        cheque.setDecisionFinale(finalDecision);
        cheque.setPipelineMs(durationMs);

        Map<String, Object> phases = (Map<String, Object>) result.get("phases");

        // ── Score global (moyenne phases) ──────────────────────────────────
        if (phases != null) {
            double sum = 0; int n = 0;
            for (Object v : phases.values()) {
                Map<String, Object> p = (Map<String, Object>) v;
                if (p != null && p.get("score") instanceof Number) {
                    sum += ((Number) p.get("score")).doubleValue(); n++;
                }
            }
            if (n > 0) cheque.setAiScoreGlobal(
                    BigDecimal.valueOf(sum / n).setScale(4, RoundingMode.HALF_UP));
        }

        // ── Données OCR ────────────────────────────────────────────────────
        if (phases != null) {
            Map<String, Object> ocr = (Map<String, Object>) phases.get("ocr");
            if (ocr != null) {
                Map<String, Object> details   = (Map<String, Object>) ocr.get("details");
                Map<String, Object> extracted = details != null
                        ? (Map<String, Object>) details.get("extracted") : null;
                if (extracted != null) {
                    Object m = extracted.get("montant_chiffres");
                    if (m instanceof Number)
                        cheque.setMontantExtrait(BigDecimal.valueOf(((Number) m).doubleValue()));
                    cheque.setMontantLettres((String) extracted.get("montant_lettres"));
                    cheque.setBeneficiaireNom((String) extracted.get("beneficiaire"));
                    // Tireur = titulaire du compte (nom sous le cadre "Titulaire du compte")
                    String tireur = (String) extracted.get("tireur");
                    if (tireur == null) tireur = (String) extracted.get("titulaire");
                    if (tireur != null && !tireur.isBlank())
                        cheque.setEmetteurNom(tireur);
                }
            }

            // ── QR data (compliance) ────────────────────────────────────────
            // qr_data est un OBJET (Map) pas une String :
            // { "raw": "pecc.tn/...", "beneficiaire": "GUIZANI RYM", "montant": 1500, ... }
            Map<String, Object> comp = (Map<String, Object>) phases.get("compliance");
            if (comp != null) {
                Map<String, Object> compDet = (Map<String, Object>) comp.get("details");
                if (compDet != null) {
                    Object qrDataObj = compDet.get("qr_data");
                    if (qrDataObj instanceof Map) {
                        Map<String, Object> qrMap = (Map<String, Object>) qrDataObj;
                        // Sauvegarder le QR brut
                        cheque.setQrData((String) qrMap.get("raw"));
                        // QR p[5] = titulaire du compte (émetteur/tireur), pas le bénéficiaire manuscrit
                        // Le bénéficiaire vient uniquement de Phase 3 OCR manuscrite
                        String qrTitulaire = (String) qrMap.get("beneficiaire");
                        if (qrTitulaire != null && !qrTitulaire.isBlank())
                            cheque.setEmetteurNom(qrTitulaire);
                        // N° chèque depuis QR
                        String numCheque = (String) qrMap.get("numero_cheque");
                        if (numCheque != null)
                            cheque.setNumeroCheque(numCheque);
                        // RIB emetteur depuis QR → sauvegarder + résoudre tireur_id
                        String rib = (String) qrMap.get("rib");
                        if (rib != null) {
                            cheque.setRibEmetteur(rib);
                            authServiceClient.findUserIdByRib(rib)
                                .ifPresent(cheque::setTireurId);
                        }
                    }
                }
            }
        }

        // ── Status selon final_decision ────────────────────────────────────
        // Décisions possibles : VALIDE, APPROVED, REJETE, REJECTED_*, FRAUDE, PENDING_*
        if (finalDecision.startsWith("VALIDE") || "APPROVED".equals(finalDecision)) {
            cheque.setStatus(Cheque.ChequeStatus.VALIDE);
        } else if (finalDecision.startsWith("REJETE") || finalDecision.startsWith("REJECTED")) {
            cheque.setStatus(Cheque.ChequeStatus.REJETE);
        } else if (finalDecision.contains("FRAUDE") || "FRAUD".equals(finalDecision)) {
            cheque.setStatus(Cheque.ChequeStatus.FRAUDE_DETECTEE);
            cheque.setFraudeDetectee(true);
        } else {
            // PENDING_REVIEW, PENDING_REVIEW_QR… → agent doit décider
            cheque.setStatus(Cheque.ChequeStatus.EN_ATTENTE);
        }

        cheque = chequeRepository.save(cheque);

        // ── Sauvegarder résultats par phase ────────────────────────────────
        if (phases != null) savePhaseResults(cheque.getId(), phases);

        // ── Notification pipeline via HTTP ────────────────────────────────
        notificationClient.send(
            cheque.getBeneficiaireId() != null ? cheque.getBeneficiaireId().toString() : null,
            cheque.getId().toString(), "BENEFICIAIRE",
            "TuniCheque — Analyse de votre chèque terminée",
            "Résultat : " + finalDecision + ". Référence : " + cheque.getId(),
            "pipeline.completed");

        return cheque;
    }

    @SuppressWarnings("unchecked")
    private void savePhaseResults(UUID chequeId, Map<String, Object> phases) {
        Map<String, AiResult.Phase> mapping = Map.of(
                "identification", AiResult.Phase.identification,
                "compliance",     AiResult.Phase.compliance,
                "ocr",            AiResult.Phase.ocr,
                "signature",      AiResult.Phase.signature
        );

        for (var entry : mapping.entrySet()) {
            Map<String, Object> p = (Map<String, Object>) phases.get(entry.getKey());
            if (p == null) continue;

            AiResult ar = AiResult.builder()
                    .chequeId(chequeId)
                    .phase(entry.getValue())
                    .passed(Boolean.TRUE.equals(p.get("passed")))
                    .build();

            if (p.get("score") instanceof Number)
                ar.setScore(BigDecimal.valueOf(((Number) p.get("score")).doubleValue()));
            if (p.get("duration_ms") instanceof Number)
                ar.setDurationMs(((Number) p.get("duration_ms")).intValue());

            Map<String, Object> det = (Map<String, Object>) p.get("details");
            if (det != null) ar.setDecision((String) det.get("decision"));

            try {
                aiResultRepository.save(ar);
            } catch (Exception e) {
                log.warn("Phase {} déjà en base pour ce chèque", entry.getKey());
            }
        }
    }

    // ─── Sauvegarde image ──────────────────────────────────────────────────

    private String saveFile(MultipartFile file, String suffix) throws IOException {
        return saveFileBytes(file.getBytes(), file.getOriginalFilename(), suffix);
    }

    private String saveFileBytes(byte[] bytes, String originalName, String suffix) throws IOException {
        Path dir = Paths.get(uploadDir);
        if (!Files.exists(dir)) Files.createDirectories(dir);
        String name = UUID.randomUUID() + "_" + suffix + "_" + (originalName != null ? originalName : "file.jpg");
        Files.write(dir.resolve(name), bytes);
        return dir.resolve(name).toString();
    }

    // ─── Retraitement asynchrone d'un chèque mobile ───────────────────────
    //
    // Retourne IMMÉDIATEMENT avec status EN_TRAITEMENT.
    // Le pipeline IA tourne en arrière-plan dans un thread séparé.
    // Le frontend doit poller GET /{id} jusqu'à ce que le status change.

    public Cheque startReprocess(UUID chequeId) throws IOException {
        Cheque cheque = getChequeById(chequeId);

        String rectoPath = cheque.getImageRectoUrl();
        if (rectoPath == null || rectoPath.isBlank()) {
            throw new RuntimeException("Aucune image recto disponible pour ce chèque.");
        }

        // Lire les images avant de lancer le thread
        final byte[] rectoBytes   = Files.readAllBytes(Paths.get(rectoPath));
        final String rectoFilename = Paths.get(rectoPath).getFileName().toString();
        byte[] vBytes = null;
        String vName  = null;
        if (cheque.getImageVersoUrl() != null && !cheque.getImageVersoUrl().isBlank()) {
            try {
                vBytes = Files.readAllBytes(Paths.get(cheque.getImageVersoUrl()));
                vName  = Paths.get(cheque.getImageVersoUrl()).getFileName().toString();
            } catch (Exception e) {
                log.warn("Verso introuvable, ignoré.");
            }
        }
        final byte[] versoBytes   = vBytes;
        final String versoFilename = vName;

        // Supprimer anciens résultats, marquer EN_TRAITEMENT
        aiResultRepository.deleteByChequeId(chequeId);
        cheque.setStatus(Cheque.ChequeStatus.EN_TRAITEMENT);
        cheque.setDecisionFinale(null);
        cheque.setAiScoreGlobal(null);
        cheque = chequeRepository.save(cheque);

        log.info("Retraitement ASYNC lancé — chèque {}", chequeId);

        // Lancer pipeline en arrière-plan
        final UUID finalId = chequeId;
        java.util.concurrent.CompletableFuture.runAsync(() -> {
            try {
                Cheque fresh = chequeRepository.findById(finalId).orElseThrow();
                callAiPipelineWithBytes(fresh, rectoBytes, rectoFilename, versoBytes, versoFilename);
                log.info("Retraitement ASYNC terminé — chèque {}", finalId);
            } catch (Exception e) {
                log.error("Retraitement ASYNC échoué — chèque {} : {}", finalId, e.getMessage());
                chequeRepository.findById(finalId).ifPresent(c -> {
                    c.setStatus(Cheque.ChequeStatus.EN_ATTENTE);
                    chequeRepository.save(c);
                });
            }
        });

        return cheque;
    }

    // ─── Consultation ──────────────────────────────────────────────────────

    public Cheque         getChequeById(UUID id)               { return chequeRepository.findById(id).orElseThrow(() -> new RuntimeException("Chèque non trouvé : " + id)); }
    public List<Cheque>   getAllCheques()                       { return chequeRepository.findAll(); }
    public List<Cheque>   getChequesEnAttente()                { return chequeRepository.findByStatusAndSourceOrderByCreatedAtDesc(Cheque.ChequeStatus.EN_ATTENTE, "MOBILE"); }
    public List<Cheque>   getChequesByBeneficiaire(UUID id)    { return chequeRepository.findByBeneficiaireIdOrderByCreatedAtDesc(id); }
    public List<Cheque>   getChequesByTireur(UUID id)          { return chequeRepository.findByTireurIdOrderByCreatedAtDesc(id); }
    public List<AiResult> getAiResults(UUID chequeId)          { return aiResultRepository.findByChequeIdOrderByCreatedAtAsc(chequeId); }

    // ─── Consultation paginée (mobile) ────────────────────────────────────

    public Page<Cheque> getChequesMobile(UUID userId, String espace,
                                         Cheque.ChequeStatus statut,
                                         int page, int size) {
        PageRequest pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        boolean isTireur = "tireur".equalsIgnoreCase(espace);

        if (statut != null) {
            return isTireur
                    ? chequeRepository.findByTireurIdAndStatusOrderByCreatedAtDesc(userId, statut, pageable)
                    : chequeRepository.findByBeneficiaireIdAndStatusOrderByCreatedAtDesc(userId, statut, pageable);
        }
        return isTireur
                ? chequeRepository.findByTireurIdOrderByCreatedAtDesc(userId, pageable)
                : chequeRepository.findByBeneficiaireIdOrderByCreatedAtDesc(userId, pageable);
    }

    // ─── Stats dashboard mobile ────────────────────────────────────────────

    public MobileStatsDTO getMobileStats(UUID userId, String espace) {
        boolean isTireur = "tireur".equalsIgnoreCase(espace);

        if (isTireur) {
            return MobileStatsDTO.builder()
                    .totalEmissions(chequeRepository.countByTireurId(userId))
                    .emissionsEnAttente(chequeRepository.countByTireurIdAndStatus(userId, Cheque.ChequeStatus.EN_ATTENTE))
                    .emissionsValidees(chequeRepository.countByTireurIdAndStatus(userId, Cheque.ChequeStatus.VALIDE))
                    .montantEnCours(chequeRepository.sumMontantEnCoursParTireur(userId))
                    .build();
        }

        return MobileStatsDTO.builder()
                .totalCheques(chequeRepository.countByBeneficiaireId(userId))
                .enTraitement(chequeRepository.countByBeneficiaireIdAndStatus(userId, Cheque.ChequeStatus.EN_TRAITEMENT))
                .valides(chequeRepository.countByBeneficiaireIdAndStatus(userId, Cheque.ChequeStatus.VALIDE))
                .rejetes(chequeRepository.countByBeneficiaireIdAndStatus(userId, Cheque.ChequeStatus.REJETE))
                .enAttente(chequeRepository.countByBeneficiaireIdAndStatus(userId, Cheque.ChequeStatus.EN_ATTENTE))
                .montantValide(chequeRepository.sumMontantValideByBeneficiaire(userId))
                .build();
    }

    // ─── Liaison tireur rétroactive ───────────────────────────────────────
    // Appelé quand un tireur crée son compte après que ses chèques ont été traités.
    // Lie tous les chèques orphelins (rib_emetteur = rib, tireur_id = null)
    // et envoie les notifications manquées pour les chèques déjà décidés.

    public void linkTireur(String rib, UUID userId) {
        List<Cheque> orphelins = chequeRepository
                .findByRibEmetteurAndTireurIdIsNull(rib);

        if (orphelins.isEmpty()) {
            log.info("linkTireur : aucun chèque orphelin pour rib={}", rib);
            return;
        }

        log.info("linkTireur : {} chèque(s) à lier — rib={} userId={}", orphelins.size(), rib, userId);

        for (Cheque cheque : orphelins) {
            cheque.setTireurId(userId);
            chequeRepository.save(cheque);

            String statut = cheque.getStatus() != null ? cheque.getStatus().name() : "";
            boolean isValide = "VALIDE".equals(statut);
            boolean isRejete = "REJETE".equals(statut) || "FRAUDE_DETECTEE".equals(statut);

            if (isValide || isRejete) {
                String refSuffix   = ". Référence : " + cheque.getId();
                String motifSuffix = cheque.getMotifRejet() != null ? ". Motif : " + cheque.getMotifRejet() : "";
                notificationClient.send(
                    userId.toString(),
                    cheque.getId().toString(), "TIREUR",
                    isValide ? "Un de vos chèques a été validé ✅"
                             : "Un de vos chèques a été rejeté ❌",
                    isValide ? "Le chèque que vous avez émis a été validé" + refSuffix
                             : "Le chèque que vous avez émis a été rejeté" + refSuffix + motifSuffix,
                    "cheque.validated");
                log.info("linkTireur : notification envoyée pour chequeId={} statut={}", cheque.getId(), statut);
            }
        }
    }

    // ─── Validation agent ─────────────────────────────────────────────────

    public Cheque validerCheque(UUID chequeId, UUID agentId, String decision,
                                String motif, String cinBeneficiaire, String ribBeneficiaire) {
        Cheque cheque = getChequeById(chequeId);
        cheque.setAgentId(agentId);
        cheque.setDecisionFinale(decision);
        cheque.setValidatedAt(LocalDateTime.now());
        cheque.setStatus("VALIDE".equals(decision)
                ? Cheque.ChequeStatus.VALIDE : Cheque.ChequeStatus.REJETE);
        if (motif != null) cheque.setMotifRejet(motif);
        cheque = chequeRepository.save(cheque);

        boolean isValide    = "VALIDE".equals(decision);
        String  refSuffix   = ". Référence : " + chequeId;
        String  motifSuffix = motif != null ? ". Motif : " + motif : "";

        // Résoudre l'ID bénéficiaire : depuis la base, via CIN (individu) ou via RIB (société)
        UUID resolvedBeneficiaireId = cheque.getBeneficiaireId();
        if (resolvedBeneficiaireId == null && cinBeneficiaire != null && !cinBeneficiaire.isBlank()) {
            resolvedBeneficiaireId = authServiceClient.findUserIdByCin(cinBeneficiaire).orElse(null);
        }
        if (resolvedBeneficiaireId == null && ribBeneficiaire != null && !ribBeneficiaire.isBlank()) {
            resolvedBeneficiaireId = authServiceClient.findUserIdByRib(ribBeneficiaire).orElse(null);
        }

        // Résoudre le tireur_id par rib_emetteur (extrait du QR ou déjà en base)
        String ribEmetteur = cheque.getRibEmetteur();
        UUID tireurIdResolu = cheque.getTireurId();

        if (tireurIdResolu == null && ribEmetteur != null && !ribEmetteur.isBlank()) {
            tireurIdResolu = authServiceClient.findUserIdByRib(ribEmetteur).orElse(null);
        }

        // Persister les IDs résolus en une seule passe
        boolean needsSave = false;
        if (resolvedBeneficiaireId != null && cheque.getBeneficiaireId() == null) {
            cheque.setBeneficiaireId(resolvedBeneficiaireId);
            needsSave = true;
        }
        if (tireurIdResolu != null && cheque.getTireurId() == null) {
            cheque.setTireurId(tireurIdResolu);
            needsSave = true;
        }
        if (needsSave) cheque = chequeRepository.save(cheque);

        // Notification → bénéficiaire
        if (resolvedBeneficiaireId != null) {
            notificationClient.send(
                resolvedBeneficiaireId.toString(),
                chequeId.toString(), "BENEFICIAIRE",
                isValide ? "Votre chèque a été validé ✅"
                         : "Votre chèque a été rejeté ❌",
                isValide ? "Votre chèque a été accepté et est en cours de traitement" + refSuffix
                         : "Votre chèque a été rejeté" + refSuffix + motifSuffix,
                "cheque.validated");
        }

        // Notification → tireur
        if (tireurIdResolu != null) {
            notificationClient.send(
                tireurIdResolu.toString(),
                chequeId.toString(), "TIREUR",
                isValide ? "Un de vos chèques a été validé ✅"
                         : "Un de vos chèques a été rejeté ❌",
                isValide ? "Le chèque que vous avez émis a été validé" + refSuffix
                         : "Le chèque que vous avez émis a été rejeté" + refSuffix + motifSuffix,
                "cheque.validated");
        }

        return cheque;
    }
}