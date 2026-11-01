package tn.tunicheque.auth_service.entity;

import jakarta.persistence.*;
import lombok.*;


import java.time.LocalDateTime;
import java.util.UUID;

/**
 * BankAccount — compte bancaire BCT.
 * Table : bank_accounts dans database_auth.
 *
 * Le RIB (20 chiffres) lie le client à son numéro de téléphone.
 * Utilisé pour l'inscription mobile via RIB.
 */
@Entity
@Table(name = "bank_accounts")
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BankAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(unique = true, nullable = false, length = 20)
    private String rib;             // 20 chiffres complets

    @Column(name = "code_banque", length = 2)
    private String codeBanque;      // rib[0:2]

    @Column(name = "code_agence", length = 3)
    private String codeAgence;      // rib[2:5]

    @Column(name = "num_compte", length = 13)
    private String numCompte;       // rib[5:18]

    @Column(name = "cle_rib", length = 2)
    private String cleRib;          // rib[18:20]

    @Column(nullable = false, length = 20)
    private String telephone;       // numéro lié au compte (reçoit l'OTP)

    @Column(name = "nom_client", length = 200)
    private String nomClient;

    @Column(name = "prenom", length = 100)
    private String prenom;

    @Builder.Default
    private boolean active = true;

    @Column(name = "created_at")
    @Builder.Default
    private LocalDateTime createdAt = LocalDateTime.now();
}
