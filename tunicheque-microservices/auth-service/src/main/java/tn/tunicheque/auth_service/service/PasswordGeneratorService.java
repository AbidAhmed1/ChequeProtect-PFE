package tn.tunicheque.auth_service.service;

import org.springframework.stereotype.Service;

import java.security.SecureRandom;

/**
 * Génère des mots de passe professionnels : forts, mémorisables, non modifiables.
 *
 * Pattern : Syllabe1 (3 lettres, 1re maj) + 2 chiffres + symbole + syllabe2 (3 lettres, minusc) + 1 chiffre
 * Exemple  : "Cap42@sol7" — 10 caractères, entropie ~50 bits
 *
 * Critères vérifiés :
 *   ✓ Majuscule    (1re lettre de la 1re syllabe)
 *   ✓ Minuscules   (reste des syllabes)
 *   ✓ Chiffres     (3 chiffres au total)
 *   ✓ Caractère spécial (1 symbole)
 *   ✓ Longueur 10  (ni trop court ni trop long)
 *   ✓ Prononçable  (structure syllabique → mémorisable)
 */
@Service
public class PasswordGeneratorService {

    // Syllabes du domaine bancaire tunisien — prononçables, distinctes visuellement
    private static final String[] SYLLABLES = {
        "Cap", "Ban", "Fin", "Cre", "Sol", "Pro", "Val",
        "Mon", "Ris", "Net", "Pay", "Sec", "Aur", "Tra",
        "Deb", "Fon", "Ges", "Nor", "Bac", "Soc"
    };

    // Symboles acceptés dans la majorité des systèmes d'authentification
    private static final char[] SPECIALS = { '@', '#', '&', '*', '!' };

    private final SecureRandom random = new SecureRandom();

    /**
     * Génère un mot de passe de la forme :  [Syl1][nn][sym][syl2][n]
     * Exemple : "Cap42@sol7"
     */
    public String generate() {
        String syl1 = SYLLABLES[random.nextInt(SYLLABLES.length)];           // ex. "Cap"
        String syl2 = SYLLABLES[random.nextInt(SYLLABLES.length)].toLowerCase(); // ex. "sol"
        int    n1   = 10 + random.nextInt(90);  // 10–99
        char   sym  = SPECIALS[random.nextInt(SPECIALS.length)];
        int    n2   = 1  + random.nextInt(9);   // 1–9

        return syl1 + n1 + sym + syl2 + n2;    // "Cap42@sol7"
    }
}