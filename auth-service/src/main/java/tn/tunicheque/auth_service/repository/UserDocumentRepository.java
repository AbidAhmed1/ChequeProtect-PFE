package tn.tunicheque.auth_service.repository;
import org.springframework.data.jpa.repository.JpaRepository;
import tn.tunicheque.auth_service.entity.UserDocument;
import java.util.Optional;
import java.util.UUID;
public interface UserDocumentRepository extends JpaRepository<UserDocument, UUID> {
    Optional<UserDocument> findBySessionId(String sessionId);
    void deleteBySessionId(String sessionId);
}