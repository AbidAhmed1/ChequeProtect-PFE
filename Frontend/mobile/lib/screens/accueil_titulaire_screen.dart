import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../widgets/app_bottom_nav.dart';
import '../services/cheque_service.dart';
import '../services/auth_service.dart';
import '../models/cheque.dart';

class AccueilTitulaireScreen extends StatefulWidget {
  const AccueilTitulaireScreen({super.key});

  @override
  State<AccueilTitulaireScreen> createState() => _AccueilTitulaireScreenState();
}

class _AccueilTitulaireScreenState extends State<AccueilTitulaireScreen> {
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
        ChequeService.instance.getMesCheques(size: 5, espace: 'tireur'),
        ChequeService.instance.getDashboardStats(espace: 'tireur'),
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

  String get _maskedRib {
    final rib = AuthService.instance.currentUser?.rib;
    if (rib == null || rib.length < 8) return '**** **** **** ****';
    return '${rib.substring(0, 2)} ${rib.substring(2, 5)} **** **** ${rib.substring(rib.length - 3)}';
  }

  @override
  Widget build(BuildContext context) {
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
            expandedHeight: 0,
            backgroundColor: Colors.white,
            elevation: 0,
            automaticallyImplyLeading: false,
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
                            colors: [AppColors.primary, AppColors.primaryContainer],
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
                            'Espace Tireur',
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
            toolbarHeight: 70,
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _BankingCard(
                    maskedRib: _maskedRib,
                    ownerName: AuthService.instance.currentUser?.fullName ?? '—',
                    stats: _stats,
                    isLoading: _isLoading,
                  ),
                  const SizedBox(height: 24),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      _QuickAction(
                        icon: Icons.payments_rounded,
                        label: 'Mes chèques',
                        onTap: () => context.go('/mes-cheques'),
                      ),
                      _QuickAction(
                        icon: Icons.history_rounded,
                        label: 'Historique',
                        onTap: () => context.go('/historique/tireur'),
                      ),
                      _QuickAction(
                        icon: Icons.person_rounded,
                        label: 'Profil',
                        onTap: () => context.push('/profil'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 28),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Chèques récents',
                        style: TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.w700,
                          color: AppColors.onSurface,
                        ),
                      ),
                      TextButton(
                        onPressed: () => context.go('/emissions'),
                        child: const Text(
                          'Voir tout',
                          style: TextStyle(color: AppColors.primary, fontSize: 13),
                        ),
                      ), // /emissions = toutes les émissions
                    ],
                  ),
                  const SizedBox(height: 8),
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
                        : _recentCheques.isEmpty
                            ? Padding(
                                padding: const EdgeInsets.all(32),
                                child: Center(
                                  child: Column(
                                    children: [
                                      Icon(Icons.receipt_long_outlined,
                                          size: 40, color: AppColors.outlineVariant),
                                      const SizedBox(height: 8),
                                      Text(
                                        'Aucun chèque émis',
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
                                itemCount: _recentCheques.length,
                                separatorBuilder: (_, __) =>
                                    const Divider(height: 1, indent: 60),
                                itemBuilder: (context, index) {
                                  final c = _recentCheques[index];
                                  final isValidated = c.status == ChequeStatus.valide;
                                  final isRejected = c.status == ChequeStatus.rejete ||
                                      c.status == ChequeStatus.fraudeDetectee;
                                  Color iconBg, iconColor;
                                  if (isValidated) {
                                    iconBg = const Color(0xFFD1FAE5);
                                    iconColor = const Color(0xFF059669);
                                  } else if (isRejected) {
                                    iconBg = AppColors.errorContainer;
                                    iconColor = AppColors.error;
                                  } else {
                                    iconBg = const Color(0xFFFEF3C7);
                                    iconColor = const Color(0xFFD97706);
                                  }
                                  return ListTile(
                                    leading: Container(
                                      width: 40,
                                      height: 40,
                                      decoration: BoxDecoration(
                                        color: iconBg,
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: Icon(Icons.payments_rounded,
                                          color: iconColor, size: 20),
                                    ),
                                    title: Text(
                                      'Réf. ${c.id.substring(0, 8).toUpperCase()}',
                                      style: const TextStyle(
                                        fontSize: 14,
                                        fontWeight: FontWeight.w600,
                                        color: AppColors.onSurface,
                                      ),
                                    ),
                                    subtitle: Text(
                                      c.createdAt.length >= 10
                                          ? c.createdAt.substring(0, 10)
                                          : c.createdAt,
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
                                          c.montantFormate,
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
                                            color: iconBg,
                                            borderRadius: BorderRadius.circular(100),
                                          ),
                                          child: Text(
                                            c.status.label,
                                            style: TextStyle(
                                              fontSize: 10,
                                              fontWeight: FontWeight.w600,
                                              color: iconColor,
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
        homeRoute: '/home/titulaire',
        chequeRoute: '/mes-cheques',
      ),
    ),
    );
  }
}

class _BankingCard extends StatelessWidget {
  final String maskedRib;
  final String ownerName;
  final MobileDashboardStats stats;
  final bool isLoading;

  const _BankingCard({
    required this.maskedRib,
    required this.ownerName,
    required this.stats,
    required this.isLoading,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppColors.primary, AppColors.primaryContainer, Color(0xFF7C3AED)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withOpacity(0.4),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Stack(
        children: [
          Positioned(
            top: -30,
            right: -30,
            child: Container(
              width: 160,
              height: 160,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withOpacity(0.07),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      'Identité Bancaire',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.75),
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        letterSpacing: 1,
                      ),
                    ),
                    const Spacer(),
                    Icon(Icons.account_balance_wallet_rounded,
                        color: Colors.white.withOpacity(0.7), size: 20),
                  ],
                ),
                const SizedBox(height: 12),
                Text(
                  maskedRib,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 1.2,
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('TITULAIRE',
                            style: TextStyle(
                                color: Colors.white.withOpacity(0.6),
                                fontSize: 10,
                                letterSpacing: 1)),
                        Text(ownerName,
                            style: const TextStyle(
                                color: Colors.white,
                                fontSize: 14,
                                fontWeight: FontWeight.w600)),
                      ],
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text('CHÈQUES ÉMIS',
                            style: TextStyle(
                                color: Colors.white.withOpacity(0.6),
                                fontSize: 10,
                                letterSpacing: 1)),
                        isLoading
                            ? const SizedBox(
                                width: 60,
                                height: 20,
                                child: LinearProgressIndicator(
                                  backgroundColor: Colors.white24,
                                  color: Colors.white,
                                ),
                              )
                            : Text(
                                '${stats.totalEmissions}',
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 22,
                                    fontWeight: FontWeight.w800)),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    _StatChip(
                      label: 'En attente',
                      value: '${stats.emissionsEnAttente}',
                      isLoading: isLoading,
                    ),
                    const SizedBox(width: 8),
                    _StatChip(
                      label: 'Validés',
                      value: '${stats.emissionsValidees}',
                      isLoading: isLoading,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final bool isLoading;
  const _StatChip({required this.label, required this.value, required this.isLoading});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.15),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        isLoading ? '— $label' : '$value $label',
        style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w500),
      ),
    );
  }
}

class _QuickAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  const _QuickAction({required this.icon, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                    color: Colors.black.withOpacity(0.06),
                    blurRadius: 8,
                    offset: const Offset(0, 2)),
              ],
            ),
            child: Icon(icon, color: AppColors.primary, size: 26),
          ),
          const SizedBox(height: 8),
          Text(label,
              style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                  color: AppColors.onSurface)),
        ],
      ),
    );
  }
}
