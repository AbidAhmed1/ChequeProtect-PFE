import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';

class ConditionsUtilisationScreen extends StatelessWidget {
  const ConditionsUtilisationScreen({super.key});

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
        title: const Text('Conditions d\'utilisation'),
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
            _Section(
              title: '1. Objet',
              body:
                  'Les présentes Conditions Générales d\'Utilisation (CGU) régissent l\'accès et l\'utilisation de l\'application mobile ChèqueProtect, éditée par ChèqueProtect. En accédant à l\'application, vous acceptez sans réserve les présentes CGU.',
            ),
            _Section(
              title: '2. Accès au service',
              body:
                  'L\'accès à ChèqueProtect est réservé aux personnes physiques majeures disposant d\'un compte bancaire valide. L\'inscription nécessite la fourniture d\'un RIB et la validation de votre identité via un code OTP. Vous êtes responsable de la confidentialité de vos identifiants.',
            ),
            _Section(
              title: '3. Utilisation du service',
              body:
                  'ChèqueProtect vous permet de déposer des chèques en les photographiant via votre smartphone. Vous vous engagez à :\n\n• Fournir des images lisibles et non altérées.\n• Ne pas déposer un chèque déjà encaissé ou annulé.\n• Conserver le chèque physique jusqu\'à confirmation du traitement.\n• Ne pas utiliser le service à des fins frauduleuses.',
            ),
            _Section(
              title: '4. Responsabilités',
              body:
                  'ChèqueProtect met en œuvre tous les moyens raisonnables pour assurer la disponibilité et la sécurité du service. Toutefois, nous ne saurions être tenus responsables de toute interruption, perte de données ou préjudice indirect résultant de l\'utilisation de l\'application.',
            ),
            _Section(
              title: '5. Propriété intellectuelle',
              body:
                  'L\'ensemble des contenus présents dans l\'application (textes, icônes, logos, interface) sont la propriété exclusive de ChèqueProtect et sont protégés par le droit de la propriété intellectuelle. Toute reproduction, même partielle, est interdite sans autorisation écrite préalable.',
            ),
            _Section(
              title: '6. Modification des CGU',
              body:
                  'ChèqueProtect se réserve le droit de modifier les présentes CGU à tout moment. Vous serez notifié de tout changement substantiel. La poursuite de l\'utilisation du service après modification vaut acceptation des nouvelles conditions.',
            ),
            _Section(
              title: '7. Résiliation',
              body:
                  'Vous pouvez clôturer votre compte à tout moment depuis la section Profil. ChèqueProtect peut suspendre ou résilier votre accès en cas de violation des présentes CGU, sans préavis ni indemnité.',
            ),
            _Section(
              title: '8. Loi applicable',
              body:
                  'Les présentes CGU sont régies par le droit français. Tout litige relatif à leur interprétation ou exécution sera soumis aux tribunaux compétents de Paris.',
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
              style: TextStyle(
                fontSize: 14,
                height: 1.6,
                color: AppColors.onSurface,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
