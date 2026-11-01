package tn.tunicheque.notification_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
@Slf4j
public class EmailService {

    private final JavaMailSender mailSender;

    public void envoyer(String to, String sujet, String contenu) {
        try {
            SimpleMailMessage msg = new SimpleMailMessage();
            msg.setFrom("tunicheque@gmail.com");
            msg.setTo(to);
            msg.setSubject(sujet);
            msg.setText(contenu);
            mailSender.send(msg);
            log.info("Email envoyé à : {}", to);
        } catch (Exception e) {
            log.error("Echec envoi email à {} : {}", to, e.getMessage());
            throw new RuntimeException("Echec envoi email : " + e.getMessage());
        }
    }
}
