package tn.tunicheque.auth_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import tn.tunicheque.auth_service.entity.User;
import tn.tunicheque.auth_service.entity.enums.Role;
import tn.tunicheque.auth_service.entity.enums.UserType;
import tn.tunicheque.auth_service.repository.UserRepository;

@Component
@RequiredArgsConstructor
@Slf4j
public class DataInitializer implements CommandLineRunner {

    private final UserRepository  userRepository;
    private final PasswordEncoder passwordEncoder;

    // ── Mots de passe démo (soutenance — boutons de raccourci UI) ─────────
    // Respectent la politique : Maj + min + chiffres + spécial, 11 caractères
    static final String DEMO_ADMIN_PWD = "CheqOS@2025";
    static final String DEMO_AGENT_PWD = "Agent#Ban47";

    @Override
    public void run(String... args) {

        // ── Admin principal ───────────────────────────────────────────────
        createIfAbsent("admin@tunicheque.tn", "Admin TuniCheque",
                "+21600000000", Role.ADMIN, "CheqOS@2025");

        // ── Agent principal ───────────────────────────────────────────────
        createIfAbsent("agent@tunicheque.tn", "Agent TuniCheque",
                "+21611111111", Role.AGENT, "Agent#Ban47");

        // ── Comptes DÉMO (soutenance) ─────────────────────────────────────
        createIfAbsent("admin@demo.tn", "Admin Démo",
                "+21690000001", Role.ADMIN, DEMO_ADMIN_PWD);

        createIfAbsent("agent@demo.tn", "Agent Démo",
                "+21690000002", Role.AGENT, DEMO_AGENT_PWD);

        // ── Comptes client test (PIN mobile 6 chiffres) ───────────────────
        // Sans RIB → CLIENT → espace bénéficiaire seulement
        createClientIfAbsent("client.sans.rib@test.tn", "Client Sans RIB",
                "+21622222222", Role.CLIENT, null, null, "112233");

        // Avec RIB → CLIENT → espace tireur + bénéficiaire
        createClientIfAbsent("client.avec.rib@test.tn", "Client Avec RIB",
                "+21633333333", Role.CLIENT, "87654321", "11223300000000000021", "112233");
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    private void createIfAbsent(String email, String fullName,
                                 String phone, Role role, String password) {
        if (!userRepository.existsByEmail(email)) {
            userRepository.save(User.builder()
                    .email(email)
                    .passwordHash(passwordEncoder.encode(password))
                    .fullName(fullName)
                    .userType(UserType.INTERNAL)
                    .role(role)
                    .phone(phone)
                    .isActive(true)
                    .isVerified(true)
                    .build());
            log.info("Compte {} créé : {}", role, email);
        }
    }

    private void createClientIfAbsent(String email, String fullName,
                                       String phone, Role role,
                                       String cin, String password) {
        createClientIfAbsent(email, fullName, phone, role, cin, null, password);
    }

    private void createClientIfAbsent(String email, String fullName,
                                       String phone, Role role,
                                       String cin, String rib, String password) {
        if (!userRepository.existsByEmail(email)) {
            userRepository.save(User.builder()
                    .email(email)
                    .passwordHash(passwordEncoder.encode(password))
                    .fullName(fullName)
                    .userType(UserType.CLIENT)
                    .role(role)
                    .phone(phone)
                    .cinNumber(cin)
                    .rib(rib)
                    .isActive(true)
                    .isVerified(true)
                    .build());
            log.info("Compte client {} créé : {}", role, email);
        }
    }
}