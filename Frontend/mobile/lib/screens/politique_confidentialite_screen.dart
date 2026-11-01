import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';

class PolitiqueConfidentialiteScreen extends StatelessWidget {
  const PolitiqueConfidentialiteScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.pop();
      },
      child: Scaffold(
      backgroundColor: AppColors.surfaceContainerLow,
      appBar: AppBar(
        title: const Text('Politique de confidentialité'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded),
          onPressed: () => context.pop(),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.secondaryContainer,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Icon(Icons.privacy_tip_rounded, color: AppColors.primary, size: 24),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'ChèqueProtect s\'engage à protéger vos données personnelles conformément à la loi organique tunisienne n°2004-63 relative à la protection des données à caractère personnel.',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: AppColors.primary,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            _Section(
              title: '1. Responsable du traitement',
              body:
                  'ChèqueProtect, société à responsabilité limitée immatriculée au Registre National des Entreprises (RNE) de Tunis sous le numéro B 12345678, est le responsable du traitement de vos données personnelles.',
            ),
            _Section(
              title: '2. Données collectées',
              body:
                  'Nous collectons les données suivantes lors de votre utilisation de l\'application :\n\n• Identité : nom, prénom, numéro de CIN.\n• Coordonnées : adresse e-mail (optionnelle), numéro de téléphone.\n• Données bancaires : RIB (chiffré).\n• Images de chèques transmises lors des dépôts.\n• Données de connexion : adresse IP, horodatage, type d\'appareil.\n• Données de navigation dans l\'application.',
            ),
            _Section(
              title: '3. Finalités du traitement',
              body:
                  'Vos données sont utilisées pour :\n\n• Créer et gérer votre compte utilisateur.\n• Traiter vos dépôts de chèques.\n• Sécuriser l\'accès à votre espace (authentification par code PIN).\n• Vous envoyer des notifications liées à vos opérations.\n• Améliorer nos services et prévenir la fraude.\n• Respecter nos obligations légales et réglementaires.',
            ),
            _Section(
              title: '4. Base légale',
              body:
                  'Les traitements reposent sur :\n\n• L\'exécution du contrat de service.\n• Le respect des obligations légales issues de la loi tunisienne n°2004-63.\n• Notre intérêt légitime à sécuriser notre plateforme et prévenir la fraude.',
            ),
            _Section(
              title: '5. Durée de conservation',
              body:
                  'Vos données sont conservées pendant la durée de votre relation contractuelle avec ChèqueProtect, augmentée des délais légaux de prescription applicables (5 ans pour les données bancaires). Les images de chèques sont supprimées 13 mois après leur traitement.',
            ),
            _Section(
              title: '6. Destinataires des données',
              body:
                  'Vos données peuvent être transmises à :\n\n• Nos prestataires techniques (hébergement, traitement OCR) dans le cadre de contrats garantissant leur confidentialité.\n• Les établissements bancaires tunisiens concernés par vos opérations.\n• Les autorités légales et réglementaires tunisiennes sur demande.',
            ),
            _Section(
              title: '7. Vos droits',
              body:
                  'Conformément à la loi n°2004-63, vous disposez des droits suivants :\n\n• Droit d\'accès à vos données.\n• Droit de rectification.\n• Droit à l\'effacement.\n• Droit d\'opposition au traitement.\n\nPour exercer ces droits, contactez-nous à : dpo@chequepro.tn',
            ),
            _Section(
              title: '8. Sécurité',
              body:
                  'ChèqueProtect met en œuvre des mesures techniques et organisationnelles appropriées pour protéger vos données : chiffrement TLS en transit, chiffrement AES-256 au repos, authentification forte par code PIN, journalisation des accès et audits réguliers.',
            ),
            _Section(
              title: '9. Identifiants techniques',
              body:
                  'L\'application mobile n\'utilise pas de cookies. Des identifiants techniques anonymisés peuvent être utilisés à des fins de stabilité et d\'amélioration de l\'application, sans permettre votre identification personnelle.',
            ),
            _Section(
              title: '10. Contact & réclamations',
              body:
                  'Pour toute question relative à vos données personnelles, contactez-nous via le Support de l\'application ou par e-mail à : privacy@chequepro.tn\n\nVous pouvez également introduire une réclamation auprès de l\'INPDP — Instance Nationale de Protection des Données Personnelles (www.inpdp.nat.tn).',
            ),
            const SizedBox(height: 8),
            Text(
              'Dernière mise à jour : 7 mai 2026',
              style: TextStyle(
                fontSize: 12,
                color: AppColors.onSurfaceVariant,
                fontStyle: FontStyle.italic,
              ),
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    ),
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final String body;

  const _Section({required this.title, required this.body});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: AppColors.onSurface,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              body,
              style: TextStyle(fontSize: 14, height: 1.6, color: AppColors.onSurface),
            ),
          ),
        ],
      ),
    );
  }
}