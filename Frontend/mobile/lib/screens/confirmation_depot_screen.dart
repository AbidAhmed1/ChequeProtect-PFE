import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../widgets/primary_button.dart';

class ConfirmationDepotScreen extends StatelessWidget {
  final String? numeroCheque;
  final String? montant;
  final String? statut;

  const ConfirmationDepotScreen({
    super.key,
    this.numeroCheque,
    this.montant,
    this.statut,
  });

  static const _months = [
    'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
  ];

  String get _dateDepot {
    final d = DateTime.now();
    return '${d.day.toString().padLeft(2, '0')} ${_months[d.month - 1]} ${d.year}';
  }

  String get _statutLabel => statut ?? 'En traitement';

  Color get _statutBg {
    final s = _statutLabel.toLowerCase();
    if (s.contains('validé')) return const Color(0xFFD1FAE5);
    if (s.contains('rejeté') || s.contains('fraude')) return const Color(0xFFFEE2E2);
    return const Color(0xFFFEF3C7);
  }

  Color get _statutColor {
    final s = _statutLabel.toLowerCase();
    if (s.contains('validé')) return const Color(0xFF059669);
    if (s.contains('rejeté') || s.contains('fraude')) return const Color(0xFFDC2626);
    return const Color(0xFFD97706);
  }

  @override
  Widget build(BuildContext context) {
    final refLabel = numeroCheque != null && numeroCheque != '—'
        ? '#${numeroCheque}'
        : '—';
    final montantLabel = montant ?? '—';

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.go('/home/beneficiaire');
      },
      child: Scaffold(
        backgroundColor: AppColors.background,
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 96,
                  height: 96,
                  decoration: BoxDecoration(
                    color: const Color(0xFFD1FAE5),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.check_circle_rounded,
                    color: Color(0xFF059669),
                    size: 56,
                  ),
                )
                    .animate()
                    .scale(
                        begin: const Offset(0, 0),
                        end: const Offset(1, 1),
                        duration: 600.ms,
                        curve: Curves.elasticOut)
                    .fadeIn(duration: 300.ms),
                const SizedBox(height: 24),
                const Text(
                  'Dépôt confirmé !',
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                    color: AppColors.onSurface,
                    letterSpacing: -0.5,
                  ),
                ).animate().fadeIn(delay: 300.ms, duration: 500.ms),
                const SizedBox(height: 8),
                Text(
                  'Votre chèque a été déposé avec succès\net sera traité dans les 48h ouvrables.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 15,
                    color: AppColors.onSurfaceVariant,
                    height: 1.5,
                  ),
                ).animate().fadeIn(delay: 400.ms, duration: 500.ms),
                const SizedBox(height: 36),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: AppColors.outlineVariant),
                  ),
                  child: Column(
                    children: [
                      _DetailRow(
                        label: 'Numéro de chèque',
                        value: refLabel,
                      ),
                      const Divider(height: 20),
                      _DetailRow(
                        label: 'Date de dépôt',
                        value: _dateDepot,
                      ),
                      const Divider(height: 20),
                      _DetailRow(
                        label: 'Statut',
                        value: _statutLabel,
                        valueWidget: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 4),
                          decoration: BoxDecoration(
                            color: _statutBg,
                            borderRadius: BorderRadius.circular(100),
                          ),
                          child: Text(
                            _statutLabel,
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: _statutColor,
                            ),
                          ),
                        ),
                      ),
                      const Divider(height: 20),
                      _DetailRow(
                        label: 'Montant',
                        value: montantLabel,
                      ),
                    ],
                  ),
                ).animate().fadeIn(delay: 500.ms, duration: 500.ms).slideY(
                    begin: 0.2, end: 0, delay: 500.ms, duration: 500.ms),
                const SizedBox(height: 36),
                PrimaryButton(
                  label: 'Retour à l\'accueil',
                  onPressed: () => context.go('/home/beneficiaire'),
                ).animate().fadeIn(delay: 700.ms, duration: 500.ms),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  final String label;
  final String value;
  final TextStyle? valueStyle;
  final Widget? valueWidget;

  const _DetailRow({
    required this.label,
    required this.value,
    this.valueStyle,
    this.valueWidget,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 13,
            color: AppColors.onSurfaceVariant,
          ),
        ),
        valueWidget ??
            Text(
              value,
              style: valueStyle ??
                  const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: AppColors.onSurface,
                  ),
            ),
      ],
    );
  }
}
