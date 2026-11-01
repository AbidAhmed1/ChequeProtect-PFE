import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../widgets/app_bottom_nav.dart';
import '../widgets/primary_button.dart';
import '../services/cheque_service.dart';
import '../services/auth_service.dart';
import '../models/cheque.dart';

class AccueilBeneficiaireScreen extends StatefulWidget {
  const AccueilBeneficiaireScreen({super.key});

  @override
  State<AccueilBeneficiaireScreen> createState() => _AccueilBeneficiaireScreenState();
}

class _AccueilBeneficiaireScreenState extends State<AccueilBeneficiaireScreen> {
  List<Cheque> _recentCheques = [];
  MobileDashboardStats _stats = MobileDashboardStats.empty();
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    try {
      final results = await Future.wait([
        ChequeService.instance.getMesCheques(size: 5, espace: 'beneficiaire'),
        ChequeService.instance.getDashboardStats(espace: 'beneficiaire'),
      ]);
      if (mounted) {
        setState(() {
          _recentCheques = (results[0] as PagedCheques).content;
          _stats = results[1] as MobileDashboardStats;
          _isLoading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  String get _userName {
    final user = AuthService.instance.currentUser;
    if (user == null) return 'Bonjour';
    return user.fullName.trim().split(' ')
        .map((w) => w.isEmpty ? '' : '${w[0].toUpperCase()}${w.substring(1).toLowerCase()}')
        .join(' ');
  }

  String get _userInitials {
    final user = AuthService.instance.currentUser;
    if (user == null) return '?';
    final parts = user.fullName.split(' ');
    if (parts.length >= 2) return '${parts[0][0]}${parts[1][0]}'.toUpperCase();
    return user.fullName.isNotEmpty ? user.fullName[0].toUpperCase() : '?';
  }

  String _formatMontant(double v) =>
      '${v.toStringAsFixed(3)} DT';

  @override
  Widget build(BuildContext context) {
    final recentDeposits = _isLoading
        ? <Map<String, String>>[]
        : _recentCheques.map((c) => {
              'label': 'Réf. ${c.id.substring(0, 8).toUpperCase()}',
              'date': c.createdAt.length >= 16
                  ? '${c.createdAt.substring(0, 10)}  ${c.createdAt.substring(11, 16)}'
                  : c.createdAt.substring(0, 10),
              'amount': c.montantFormate,
              'status': c.status.label,
            }).toList();

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) () async {
          final exit = await showDialog<bool>(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Text('Quitter l\'application ?'),
              content: const Text('Voulez-vous vraiment quitter ChèqueProtect ?'),
              actions: [
                TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Annuler')),
                TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Quitter', style: TextStyle(color: Colors.red))),
              ],
            ),
          );
          if (exit == true) SystemNavigator.pop();
        }();
      },
      child: Scaffold(
      backgroundColor: AppColors.surfaceContainerLow,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            pinned: true,
            backgroundColor: Colors.white,
            elevation: 0,
            automaticallyImplyLeading: false,
            toolbarHeight: 70,
            flexibleSpace: SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                child: Row(
                  children: [
                    GestureDetector(
                      onTap: () => context.push('/profil'),
                      child: Container(
                        width: 42,
                        height: 42,
                        decoration: const BoxDecoration(
                          gradient: LinearGradient(
                            colors: [AppColors.secondary, AppColors.primary],
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          ),
                          shape: BoxShape.circle,
                        ),
                        child: Center(
                          child: Text(
                            _userInitials,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            'Bonjour, $_userName',
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              color: AppColors.onSurface,
                            ),
                          ),
                          Text(
                            'Espace Bénéficiaire',
                            style: TextStyle(
                              fontSize: 12,
                              color: AppColors.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Tooltip(
                      message: 'Changer d\'espace',
                      child: IconButton(
                        icon: const Icon(Icons.swap_horiz_rounded),
                        color: AppColors.onSurfaceVariant,
                        onPressed: () => context.go('/select-space'),
                      ),
                    ),
                    Stack(
                      children: [
                        IconButton(
                          icon: const Icon(Icons.notifications_rounded),
                          color: AppColors.onSurface,
                          onPressed: () => context.push('/notifications'),
                        ),
                        Positioned(
                          top: 8,
                          right: 8,
                          child: Container(
                            width: 10,
                            height: 10,
                            decoration: const BoxDecoration(
                              color: AppColors.error,
                              shape: BoxShape.circle,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Summary card
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [AppColors.secondary, Color(0xFF8B7FA8)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      borderRadius: BorderRadius.circular(24),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.secondary.withOpacity(0.35),
                          blurRadius: 20,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Chèques reçus',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.75),
                            fontSize: 13,
                            letterSpacing: 0.5,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          _isLoading ? '—' : _formatMontant(_stats.montantValide),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 32,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          _isLoading
                              ? '...'
                              : '${_stats.enAttente} chèque${_stats.enAttente != 1 ? 's' : ''} en attente de dépôt',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.65),
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),
                  PrimaryButton(
                    label: 'Déposer un chèque',
                    onPressed: () => context.go('/depot'),
                    icon: const Icon(Icons.photo_camera_rounded, color: Colors.white, size: 20),
                  ),
                  const SizedBox(height: 28),
                  const Text(
                    'Dépôts récents',
                    style: TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: AppColors.onSurface,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: _isLoading
                        ? const Padding(
                            padding: EdgeInsets.all(32),
                            child: Center(
                              child: CircularProgressIndicator(color: AppColors.primary),
                            ),
                          )
                        : recentDeposits.isEmpty
                            ? Padding(
                                padding: const EdgeInsets.all(32),
                                child: Center(
                                  child: Column(
                                    children: [
                                      Icon(Icons.receipt_long_outlined,
                                          size: 40, color: AppColors.outlineVariant),
                                      const SizedBox(height: 8),
                                      Text(
                                        'Aucun dépôt récent',
                                        style: TextStyle(
                                          color: AppColors.onSurfaceVariant,
                                          fontSize: 14,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              )
                            : ListView.separated(
                                shrinkWrap: true,
                                physics: const NeverScrollableScrollPhysics(),
                                itemCount: recentDeposits.length,
                                separatorBuilder: (_, __) =>
                                    const Divider(height: 1, indent: 60),
                                itemBuilder: (context, index) {
                                  final d = recentDeposits[index];
                                  final isValidated = d['status'] == 'Validé';
                                  return ListTile(
                                    leading: Container(
                                      width: 40,
                                      height: 40,
                                      decoration: BoxDecoration(
                                        color: isValidated
                                            ? const Color(0xFFD1FAE5)
                                            : const Color(0xFFFEF3C7),
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: Icon(
                                        Icons.receipt_long_rounded,
                                        color: isValidated
                                            ? const Color(0xFF059669)
                                            : const Color(0xFFD97706),
                                        size: 20,
                                      ),
                                    ),
                                    title: Text(
                                      d['label']!,
                                      style: const TextStyle(
                                        fontSize: 14,
                                        fontWeight: FontWeight.w600,
                                        color: AppColors.onSurface,
                                      ),
                                    ),
                                    subtitle: Text(
                                      d['date']!,
                                      style: TextStyle(
                                        fontSize: 12,
                                        color: AppColors.onSurfaceVariant,
                                      ),
                                    ),
                                    trailing: Column(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      crossAxisAlignment: CrossAxisAlignment.end,
                                      children: [
                                        Text(
                                          d['amount']!,
                                          style: const TextStyle(
                                            fontSize: 14,
                                            fontWeight: FontWeight.w700,
                                            color: AppColors.onSurface,
                                          ),
                                        ),
                                        Container(
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 8, vertical: 2),
                                          decoration: BoxDecoration(
                                            color: isValidated
                                                ? const Color(0xFFD1FAE5)
                                                : const Color(0xFFFEF3C7),
                                            borderRadius: BorderRadius.circular(100),
                                          ),
                                          child: Text(
                                            d['status']!,
                                            style: TextStyle(
                                              fontSize: 10,
                                              fontWeight: FontWeight.w600,
                                              color: isValidated
                                                  ? const Color(0xFF059669)
                                                  : const Color(0xFFD97706),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  );
                                },
                              ),
                  ),
                  const SizedBox(height: 20),
                ],
              ),
            ),
          ),
        ],
      ),
      bottomNavigationBar: const AppBottomNav(
        currentIndex: 0,
        homeRoute: '/home/beneficiaire',
        showScanner: true,
        chequeRoute: '/encaissements',
      ),
    ),
    );
  }
}