package tn.tunicheque.auth_service.entity;
import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;
import java.util.UUID;
@Entity @Table(name = "user_documents")
@Getter @Setter @Builder @NoArgsConstructor @AllArgsConstructor
public class UserDocument {
    @Id @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;
    @Column(name = "user_id") // UUID de l'utilisateur (ou session KYC)
    private UUID userId;
    @Column(name = "session_id") private String sessionId;
    @Column(name = "cin_recto_path") private String cinRectoPath;
    @Column(name = "cin_verso_path") private String cinVersoPath;
    @Column(name = "selfie_enc_path") private String selfieEncPath; // fichier .enc
    @Column(name = "face_b64", columnDefinition = "TEXT")
    private String faceBase64;
    @Builder.Default
    @Column(name = "face_verified") private boolean faceVerified = false;
    @Builder.Default
    @Column(name = "created_at") private LocalDateTime createdAt = LocalDateTime.now();
}
