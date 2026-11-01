package tn.tunicheque.auth_service.service;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import java.io.IOException;
import java.nio.file.*;
import java.util.UUID;
@Service @Slf4j
public class FileStorageService {
    // Dans application.yml : kyc.upload-dir: uploads/kyc
    @Value("${kyc.upload-dir:uploads/kyc}")
    private String uploadDir;
    // Appele au demarrage du service
    public void init() throws IOException {
        Path dir = Paths.get(uploadDir);
        if (!Files.exists(dir)) {
            Files.createDirectories(dir);
            log.info("Dossier KYC cree : {}", dir.toAbsolutePath());
        }
    }
    /**
     * Sauvegarde un fichier et retourne son chemin relatif.
     * Ex: 'uploads/kyc/cin_recto_550e8400-uuid.jpg'
     */
    public String save(byte[] data, String prefix, String extension) throws IOException {
        init();
        String filename = prefix + '_' + UUID.randomUUID() + '.' + extension;
        Path target = Paths.get(uploadDir, filename);
        Files.write(target, data, StandardOpenOption.CREATE_NEW);
        log.info("Fichier sauvegarde : {} ({} bytes)", filename, data.length);
        return target.toString(); // chemin stocke en base
    }
    /** Lire un fichier depuis son chemin. */
    public byte[] read(String path) throws IOException {
        return Files.readAllBytes(Paths.get(path));
    }
    /** Supprimer un fichier (apres creation compte reussie). */
    public void delete(String path) {
        try { Files.deleteIfExists(Paths.get(path)); }
        catch (IOException e) { log.warn("Impossible de supprimer : {}", path); }
    }
}