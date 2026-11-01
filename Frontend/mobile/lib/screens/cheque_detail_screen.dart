import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../models/cheque.dart';

class ChequeDetailScreen extends StatelessWidget {
  final Cheque cheque;
  final String homeRoute;

  const ChequeDetailScreen({
    super.key,
    required this.cheque,
    this.homeRoute = '/home/titulaire',
  });

  Color get _statusColor {
    switch (cheque.status) {
      case ChequeStatus.valide:         return const Color(0xFF059669);
      case ChequeStatus.rejete:         return AppColors.error;
      case ChequeStatus.fraudeDetectee: return AppColors.error;
      case ChequeStatus.enTraitement:   return const Color(0xFF6366F1);
      default:                          return const Color(0xFFD97706);
    }
  }

  Color get _statusBg {
    switch (cheque.status) {
      case ChequeStatus.valide:         return const Color(0xFFD1FAE5);
      case ChequeStatus.rejete:         return AppColors.errorContainer;
      case ChequeStatus.fraudeDetectee: return AppColors.errorContainer;
      case ChequeStatus.enTraitement:   return const Color(0xFFEDE9FE);
      default:                          return const Color(0xFFFEF3C7);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bool isEnTraitement = cheque.status == ChequeStatus.enTraitement;
    final String ref = cheque.id.length >= 8
        ? cheque.id.substring(0, 8).toUpperCase()
        : cheque.id.toUpperCase();

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.go(homeRoute);
      },
      child: Scaffold(
        backgroundColor: AppColors.surfaceContainerLow,
        appBar: AppBar(
          title: Text('Chèque $ref'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded),
            onPressed: () => context.go(homeRoute),
          ),
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [

              // ── Statut principal ────────────────────────────────────────
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.04),
                      blurRadius: 8, offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                      decoration: BoxDecoration(
                        color: _statusBg,
                        borderRadius: BorderRadius.circular(100),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (isEnTraitement) ...[
                            SizedBox(
                              width: 14, height: 14,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: _statusColor,
                              ),
                            ),
                            const SizedBox(width: 8),
                          ],
                          Text(
                            cheque.status.label,
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: _statusColor,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (isEnTraitement) ...[
                      const SizedBox(height: 12),
                      Text(
                        'Analyse IA en cours...',
                        style: TextStyle(
                          fontSize: 13,
                          color: AppColors.onSurfaceVariant,
                        ),
                      ),
                    ],
                    const SizedBox(height: 12),
                    Text(
                      cheque.montantFormate,
                      style: const TextStyle(
                        fontSize: 32,
                        fontWeight: FontWeight.w900,
                        color: AppColors.primary,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Réf. $ref',
                      style: TextStyle(
                        fontSize: 13,
                        color: AppColors.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 16),

              // ── Informations du chèque ──────────────────────────────────
              Container(
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.04),
                      blurRadius: 8, offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                      child: Text(
                        'Informations',
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: AppColors.onSurface,
                        ),
                      ),
                    ),
                    const Divider(height: 1),
                    _infoRow('Bénéficiaire',
                        cheque.beneficiaireNom ?? '—'),
                    _infoRow('Numéro chèque',
                        cheque.numeroCheque ?? '—'),
                    _infoRow('Montant (lettres)',
                        cheque.montantLettres ?? '—'),
                    if (cheque.ribEmetteur != null)
                      _infoRow('RIB émetteur', cheque.ribEmetteur!),
                    _infoRow('Date de dépôt',
                        cheque.createdAt.length >= 10
                            ? cheque.createdAt.substring(0, 10)
                            : cheque.createdAt),
                    if (cheque.validatedAt != null)
                      _infoRow('Date de validation',
                          cheque.validatedAt!.length >= 10
                              ? cheque.validatedAt!.substring(0, 10)
                              : cheque.validatedAt!),
                    if (cheque.motifRejet != null)
                      _infoRow('Motif de rejet', cheque.motifRejet!,
                          valueColor: AppColors.error),
                  ],
                ),
              ),

              const SizedBox(height: 16),

              // ── Score IA ────────────────────────────────────────────────
              if (cheque.aiScoreGlobal != null)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(16),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.04),
                        blurRadius: 8, offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Score IA',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: AppColors.onSurface,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(100),
                              child: LinearProgressIndicator(
                                value: cheque.aiScoreGlobal!,
                                minHeight: 10,
                                backgroundColor: AppColors.surfaceContainerLow,
                                color: cheque.aiScoreGlobal! >= 0.85
                                    ? const Color(0xFF059669)
                                    : cheque.aiScoreGlobal! >= 0.6
                                        ? const Color(0xFFD97706)
                                        : AppColors.error,
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Text(
                            '${(cheque.aiScoreGlobal! * 100).toStringAsFixed(0)}%',
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w800,
                              color: AppColors.primary,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),

            ],
          ),
        ),
      ),
    );
  }

  Widget _infoRow(String label, String value, {Color? valueColor}) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 140,
            child: Text(
              label,
              style: TextStyle(
                fontSize: 13,
                color: AppColors.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: valueColor ?? AppColors.onSurface,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
