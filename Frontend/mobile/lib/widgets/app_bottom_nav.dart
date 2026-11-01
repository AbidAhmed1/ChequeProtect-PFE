import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';

class AppBottomNav extends StatelessWidget {
  final int currentIndex;
  final String homeRoute;
  final bool showScanner;
  final String chequeRoute;
  final VoidCallback? onScannerTap;

  const AppBottomNav({
    super.key,
    required this.currentIndex,
    this.homeRoute = '/home/titulaire',
    this.showScanner = false,
    this.chequeRoute = '/emissions',
    this.onScannerTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.08),
            blurRadius: 16,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _NavItem(
                icon: Icons.home_rounded,
                label: 'Accueil',
                isSelected: currentIndex == 0,
                onTap: () => context.go(homeRoute),
              ),
              _NavItem(
                icon: Icons.payments_rounded,
                label: 'Chèques',
                isSelected: currentIndex == 1,
                onTap: () => context.go(chequeRoute, extra: {'homeRoute': homeRoute, 'showScanner': showScanner}),
              ),
              if (showScanner)
                _NavItem(
                  icon: Icons.photo_camera_rounded,
                  label: 'Scanner',
                  isSelected: currentIndex == 2,
                  onTap: onScannerTap ?? () => context.go('/depot'),
                  isPrimary: true,
                ),
              _NavItem(
                icon: Icons.support_agent_rounded,
                label: 'Support',
                isSelected: showScanner ? currentIndex == 3 : currentIndex == 2,
                onTap: () => context.go('/chatbot', extra: {'homeRoute': homeRoute, 'showScanner': showScanner}),
              ),
              _NavItem(
                icon: Icons.settings_rounded,
                label: 'Paramètres',
                isSelected: showScanner ? currentIndex == 4 : currentIndex == 3,
                onTap: () => context.go('/parametres', extra: {'homeRoute': homeRoute, 'showScanner': showScanner}),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isSelected;
  final VoidCallback onTap;
  final bool isPrimary;

  const _NavItem({
    required this.icon,
    required this.label,
    required this.isSelected,
    required this.onTap,
    this.isPrimary = false,
  });

  @override
  Widget build(BuildContext context) {
    if (isPrimary) {
      return GestureDetector(
        onTap: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [AppColors.primary, AppColors.primaryContainer],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: AppColors.primary.withOpacity(0.4),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Icon(icon, color: Colors.white, size: 24),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w600,
                color: isSelected ? AppColors.primary : AppColors.onSurfaceVariant,
              ),
            ),
          ],
        ),
      );
    }

    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            decoration: BoxDecoration(
              color: isSelected
                  ? AppColors.secondaryContainer
                  : Colors.transparent,
              borderRadius: BorderRadius.circular(100),
            ),
            child: Icon(
              icon,
              color: isSelected ? AppColors.primary : AppColors.onSurfaceVariant,
              size: 22,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 10,
              fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
              color: isSelected ? AppColors.primary : AppColors.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}
