package tn.tunicheque.auth_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import tn.tunicheque.auth_service.entity.enums.Role;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

/**
 * Envoie l'email de bienvenue avec les identifiants lors de la création
 * d'un compte ADMIN ou AGENT par l'administrateur.
 *
 * Le mot de passe est transmis en clair une seule fois ; il n'est jamais
 * stocké en clair en base (BCrypt uniquement).
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class WelcomeEmailService {

    private final JavaMailSender mailSender;

    @Value("${spring.mail.username}")
    private String fromAddress;

    @Value("${app.frontend-url:http://localhost:4200}")
    private String frontendUrl;

    /**
     * @return true si l'email a été envoyé avec succès
     */
    public boolean sendPasswordChangedEmail(String toEmail, String fullName, String newPassword) {
        try {
            MimeMessage mime = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom(fromAddress, "ChèqueProtect — Plateforme Bancaire");
            helper.setTo(toEmail);
            helper.setSubject("ChèqueProtect — Votre mot de passe a été réinitialisé");
            helper.setText(buildPasswordChangedHtml(fullName, toEmail, newPassword), true);

            mailSender.send(mime);
            log.info("Email réinitialisation MDP envoyé → {}", toEmail);
            return true;
        } catch (Exception e) {
            log.error("Échec envoi email réinitialisation MDP vers {} : {}", toEmail, e.getMessage());
            return false;
        }
    }

    public boolean sendWelcomeEmail(String toEmail, String fullName,
                                     Role role, String plainPassword) {
        try {
            MimeMessage mime = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom(fromAddress, "ChèqueProtect — Plateforme Bancaire");
            helper.setTo(toEmail);
            helper.setSubject("Votre compte ChèqueProtect a été créé — " + roleLabel(role));
            helper.setText(buildHtml(fullName, toEmail, role, plainPassword), true);

            mailSender.send(mime);
            log.info("Email de bienvenue envoyé → {}", toEmail);
            return true;

        } catch (Exception e) {
            log.error("Échec envoi email de bienvenue vers {} : {}", toEmail, e.getMessage());
            return false;
        }
    }

    // ── Template HTML ──────────────────────────────────────────────────────

    private String buildHtml(String fullName, String email,
                              Role role, String password) {
        return """
            <!DOCTYPE html>
            <html lang="fr">
            <head>
              <meta charset="UTF-8"/>
              <style>
                body  { font-family: 'Segoe UI', Arial, sans-serif; background:#f4f6f9; margin:0; padding:0; }
                .wrap { max-width:600px; margin:40px auto; background:#fff;
                        border-radius:12px; overflow:hidden;
                        box-shadow:0 4px 20px rgba(0,0,0,.08); }
                .hdr  { background:linear-gradient(135deg,#1a56db,#1e40af);
                        padding:36px 40px; text-align:center; }
                .hdr h1 { color:#fff; margin:0; font-size:26px; letter-spacing:.5px; }
                .hdr p  { color:#bfdbfe; margin:8px 0 0; font-size:14px; }
                .body { padding:40px; }
                .greet { font-size:18px; color:#1e293b; margin-bottom:16px; }
                .badge { display:inline-block; background:#eff6ff; color:#1a56db;
                         border:1px solid #bfdbfe; border-radius:20px;
                         padding:4px 14px; font-size:13px; font-weight:600;
                         margin-bottom:24px; }
                .creds { background:#f8fafc; border:1px solid #e2e8f0;
                         border-radius:10px; padding:24px; margin:24px 0; }
                .creds-row { display:flex; justify-content:space-between;
                             align-items:center; padding:10px 0;
                             border-bottom:1px solid #e2e8f0; }
                .creds-row:last-child { border-bottom:none; }
                .creds-lbl { color:#64748b; font-size:13px; font-weight:500; }
                .creds-val { font-weight:700; color:#0f172a; font-size:15px;
                             font-family:monospace; letter-spacing:.5px; }
                .warn { background:#fef9c3; border:1px solid #fde047;
                        border-radius:8px; padding:14px 18px; margin:20px 0;
                        font-size:13px; color:#713f12; }
                .warn strong { display:block; margin-bottom:4px; }
                .btn  { display:block; width:fit-content; margin:28px auto 0;
                        background:#1a56db; color:#fff; text-decoration:none;
                        padding:14px 36px; border-radius:8px; font-size:15px;
                        font-weight:600; }
                .ftr  { text-align:center; padding:24px; background:#f8fafc;
                        color:#94a3b8; font-size:12px; }
              </style>
            </head>
            <body>
              <div class="wrap">
                <div class="hdr">
                  <h1>🛡️ ChèqueProtect</h1>
                  <p>Plateforme sécurisée de traitement des chèques bancaires</p>
                </div>
                <div class="body">
                  <p class="greet">Bonjour <strong>%s</strong>,</p>
                  <span class="badge">Rôle : %s</span>
                  <p style="color:#475569;font-size:15px;line-height:1.6;">
                    Votre compte sur la plateforme <strong>ChèqueProtect</strong> a été créé
                    par l'administrateur système. Vous trouverez ci-dessous vos identifiants
                    de connexion.
                  </p>

                  <div class="creds">
                    <div class="creds-row">
                      <span class="creds-lbl">Adresse e-mail</span>
                      <span class="creds-val">%s</span>
                    </div>
                    <div class="creds-row">
                      <span class="creds-lbl">Mot de passe</span>
                      <span class="creds-val">%s</span>
                    </div>
                  </div>

                  <div class="warn">
                    <strong>⚠️ Identifiants STRICTEMENT CONFIDENTIELS</strong>
                    Ces informations d'accès sont personnelles et ne doivent être
                    communiquées à personne. Votre mot de passe est <strong>fixe et
                    non modifiable</strong>. En cas de problème, contactez votre
                    administrateur système.
                  </div>

                  <a href="%s" class="btn">Accéder à ChèqueProtect →</a>
                </div>
                <div class="ftr">
                  © 2026 ChèqueProtect — Plateforme confidentielle à usage professionnel
                </div>
              </div>
            </body>
            </html>
            """.formatted(fullName, roleLabel(role), email, password, frontendUrl);
    }

    private String buildPasswordChangedHtml(String fullName, String email, String newPassword) {
        return """
            <!DOCTYPE html>
            <html lang="fr">
            <head>
              <meta charset="UTF-8"/>
              <style>
                body  { font-family: 'Segoe UI', Arial, sans-serif; background:#f4f6f9; margin:0; padding:0; }
                .wrap { max-width:600px; margin:40px auto; background:#fff;
                        border-radius:12px; overflow:hidden;
                        box-shadow:0 4px 20px rgba(0,0,0,.08); }
                .hdr  { background:linear-gradient(135deg,#1a56db,#1e40af);
                        padding:36px 40px; text-align:center; }
                .hdr h1 { color:#fff; margin:0; font-size:26px; }
                .hdr p  { color:#bfdbfe; margin:8px 0 0; font-size:14px; }
                .body { padding:40px; }
                .creds { background:#f8fafc; border:1px solid #e2e8f0;
                         border-radius:10px; padding:24px; margin:24px 0; }
                .creds-row { display:flex; justify-content:space-between;
                             align-items:center; padding:10px 0;
                             border-bottom:1px solid #e2e8f0; }
                .creds-row:last-child { border-bottom:none; }
                .creds-lbl { color:#64748b; font-size:13px; font-weight:500; }
                .creds-val { font-weight:700; color:#0f172a; font-size:15px;
                             font-family:monospace; }
                .warn { background:#fef9c3; border:1px solid #fde047;
                        border-radius:8px; padding:14px 18px; margin:20px 0;
                        font-size:13px; color:#713f12; }
                .btn  { display:block; width:fit-content; margin:28px auto 0;
                        background:#1a56db; color:#fff; text-decoration:none;
                        padding:14px 36px; border-radius:8px; font-size:15px; font-weight:600; }
                .ftr  { text-align:center; padding:24px; background:#f8fafc;
                        color:#94a3b8; font-size:12px; }
              </style>
            </head>
            <body>
              <div class="wrap">
                <div class="hdr">
                  <h1>🛡️ ChèqueProtect</h1>
                  <p>Réinitialisation de mot de passe</p>
                </div>
                <div class="body">
                  <p style="font-size:18px;color:#1e293b;margin-bottom:16px;">Bonjour <strong>%s</strong>,</p>
                  <p style="color:#475569;font-size:15px;line-height:1.6;">
                    L'administrateur système a réinitialisé votre mot de passe sur la plateforme <strong>ChèqueProtect</strong>.
                    Voici vos nouveaux identifiants :
                  </p>
                  <div class="creds">
                    <div class="creds-row">
                      <span class="creds-lbl">Adresse e-mail</span>
                      <span class="creds-val">%s</span>
                    </div>
                    <div class="creds-row">
                      <span class="creds-lbl">Nouveau mot de passe</span>
                      <span class="creds-val">%s</span>
                    </div>
                  </div>
                  <div class="warn">
                    <strong>⚠️ Sécurité</strong><br/>
                    Ces identifiants sont strictement confidentiels. Ne les communiquez à personne.
                  </div>
                  <a href="%s" class="btn">Accéder à ChèqueProtect →</a>
                </div>
                <div class="ftr">© 2026 ChèqueProtect — Plateforme confidentielle à usage professionnel</div>
              </div>
            </body>
            </html>
            """.formatted(fullName, email, newPassword, frontendUrl);
    }

    private static String roleLabel(Role role) {
        return switch (role) {
            case ADMIN -> "Administrateur";
            case AGENT -> "Agent bancaire";
            default    -> role.name();
        };
    }
}