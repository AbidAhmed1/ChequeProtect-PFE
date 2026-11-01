import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../services/auth_service.dart';

class SpaceSelectorScreen extends StatelessWidget {
  const SpaceSelectorScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final user = AuthService.instance.currentUser;
    final hasRib = user?.rib != null && user!.rib!.isNotEmpty;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) SystemNavigator.pop();
      },
      child: Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [AppColors.primary, AppColors.primaryContainer],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Column(
              children: [
                const SizedBox(height: 48),
                Icon(
                  Icons.account_balance_wallet_rounded,
                  color: Colors.white.withOpacity(0.9),
                  size: 48,
                ).animate().fadeIn(duration: 500.ms).scale(begin: const Offset(0.8, 0.8), duration: 500.ms),
                const SizedBox(height: 16),
                const Text(
                  'Choisissez votre espace',
                  style: TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                    letterSpacing: -0.5,
                  ),
                ).animate().fadeIn(delay: 200.ms, duration: 500.ms),
                const SizedBox(height: 8),
                Text(
                  'Sélectionnez votre profil pour accéder à votre espace personnel.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 14,
                    color: Colors.white.withOpacity(0.75),
                    height: 1.5,
                  ),
                ).animate().fadeIn(delay: 300.ms, duration: 500.ms),
                const SizedBox(height: 48),
                // Tireur card — visible uniquement si le client a un RIB
                if (hasRib)
                  _SpaceCard(
                    icon: Icons.person_rounded,
                    title: 'Espace Tireur',
                    subtitle: 'Gérez vos chèques émis\net votre compte bancaire',
                    gradientColors: const [AppColors.primary, Color(0xFF7B5EA7)],
                    onTap: () => context.go('/home/titulaire'),
                  ).animate().fadeIn(delay: 400.ms, duration: 500.ms).slideX(
                      begin: -0.1, end: 0, delay: 400.ms, duration: 500.ms),
                if (hasRib) const SizedBox(height: 16),
                // Bénéficiaire card
                _SpaceCard(
                  icon: Icons.account_balance_rounded,
                  title: 'Espace Bénéficiaire',
                  subtitle: 'Déposez les chèques\nque vous avez reçus',
                  gradientColors: const [AppColors.secondary, Color(0xFF8B7FA8)],
                  onTap: () => context.go('/home/beneficiaire'),
                ).animate().fadeIn(delay: hasRib ? 500.ms : 400.ms, duration: 500.ms).slideX(
                    begin: 0.1, end: 0, delay: hasRib ? 500.ms : 400.ms, duration: 500.ms),
                const Spacer(),
                TextButton(
                  onPressed: () => context.go('/welcome'),
                  child: Text(
                    'Se déconnecter',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.65),
                      fontSize: 14,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
              ],
            ),
          ),
        ),
      ),
    ),
    );
  }
}

class _SpaceCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final List<Color> gradientColors;
  final VoidCallback onTap;

  const _SpaceCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.gradientColors,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.12),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.white.withOpacity(0.2)),
        ),
        child: Row(
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: gradientColors,
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(16),
                boxShadow: [
                  BoxShadow(
                    color: gradientColors.first.withOpacity(0.4),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Icon(icon, color: Colors.white, size: 28),
            ),
            const SizedBox(width: 20),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.white.withOpacity(0.7),
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              Icons.chevron_right_rounded,
              color: Colors.white.withOpacity(0.6),
              size: 28,
            ),
          ],
        ),
      ),
    );
  }
}
