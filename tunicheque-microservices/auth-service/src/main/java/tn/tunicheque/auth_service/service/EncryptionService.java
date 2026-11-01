package tn.tunicheque.auth_service.service;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import javax.crypto.*;
import javax.crypto.spec.*;
import java.security.SecureRandom;
import java.util.Base64;
@Service @Slf4j
public class EncryptionService {
    // Dans application.yml : kyc.aes-key: (cle 32 chars exactement)
// Ex: kyc.aes-key: TuniCheque2026SecureKeyAES256!!
    @Value("${kyc.aes-key}")
    private String aesKeyString;
    private static final String ALGORITHM = "AES/CBC/PKCS5Padding";
    /**
     * Chiffre les bytes avec AES-256.
     * Format sortie : IV (16 bytes) + donnees_chiffrees
     * Le fichier .enc resultant est illisible sans la cle.
     */
    public byte[] encrypt(byte[] data) throws Exception {
        SecretKeySpec key = new SecretKeySpec(aesKeyString.getBytes(), "AES");
// IV aleatoire (16 bytes) — different a chaque chiffrement
        byte[] iv = new byte[16];
        new SecureRandom().nextBytes(iv);
        IvParameterSpec ivSpec = new IvParameterSpec(iv);
        Cipher cipher = Cipher.getInstance(ALGORITHM);
        cipher.init(Cipher.ENCRYPT_MODE, key, ivSpec);
        byte[] encrypted = cipher.doFinal(data);
// Concatener IV + donnees chiffrees
        byte[] result = new byte[16 + encrypted.length];
        System.arraycopy(iv, 0, result, 0, 16);
        System.arraycopy(encrypted, 0, result, 16, encrypted.length);
        log.info("Chiffrement AES-256 reussi : {} bytes -> {} bytes", data.length, result.length);
        return result;
    }
    /**
     * Dechiffre les bytes (IV recupere depuis les 16 premiers bytes).
     * Utilise pour envoyer le selfie a FastAPI sans sauvegarder
     * une copie dechiffree sur disque.
     */
    public byte[] decrypt(byte[] encryptedData) throws Exception {
        SecretKeySpec key = new SecretKeySpec(aesKeyString.getBytes(), "AES");
// Extraire IV (16 premiers bytes)
        byte[] iv = new byte[16];
        System.arraycopy(encryptedData, 0, iv, 0, 16);
// Donnees chiffrees (le reste)
        byte[] data = new byte[encryptedData.length - 16];
        System.arraycopy(encryptedData, 16, data, 0, data.length);
        Cipher cipher = Cipher.getInstance(ALGORITHM);
        cipher.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(iv));
        return cipher.doFinal(data);
    }
}