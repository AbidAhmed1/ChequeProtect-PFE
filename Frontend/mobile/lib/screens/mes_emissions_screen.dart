import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../widgets/app_bottom_nav.dart';
import '../services/cheque_service.dart';
import '../models/cheque.dart';

enum EmissionsMode { all, pending, history }

class MesEmissionsScreen extends StatefulWidget {
  final String homeRoute;
  final bool showScanner;
  final EmissionsMode mode;
  final String? chequeRoute;

  const MesEmissionsScreen({
    super.key,
    this.homeRoute = '/home/titulaire',
    this.showScanner = false,
    this.mode = EmissionsMode.all,
    this.chequeRoute,
  });

  @override
  State<MesEmissionsScreen> createState() => _MesEmissionsScreenState();
}

class _MesEmissionsScreenState extends State<MesEmissionsScreen> {
  late String _selectedFilter;
  List<Cheque> _allCheques = [];
  bool _isLoading = true;

  List<String> get _filters {
    switch (widget.mode) {
      case EmissionsMode.pending:
        return ['En attente'];
      case EmissionsMode.history:
        return ['Tous', 'Validé', 'Rejeté'];
      case EmissionsMode.all:
        return ['Tous', 'En attente', 'Validé', 'Rejeté'];
    }
  }

  String get _title {
    switch (widget.mode) {
      case EmissionsMode.pending: return 'Mes Chèques';
      case EmissionsMode.history: return 'Historique';
      case EmissionsMode.all:     return 'Mes Émissions';
    }
  }

  String get _bannerLabel {
    switch (widget.mode) {
      case EmissionsMode.pending: return 'En attente';
      case EmissionsMode.history: return 'Traités';
      case EmissionsMode.all:     return 'Total émis';
    }
  }

  @override
  void initState() {
    super.initState();
    _selectedFilter = _filters.first;
    _loadCheques();
  }

  Future<void> _loadCheques() async {
    try {
      final paged = await ChequeService.instance.getMesCheques(size: 100, espace: 'tireur');
      if (mounted) setState(() { _allCheques = paged.content; _isLoading = false; });
    } catch (_) {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  List<Map<String, dynamic>> get _cheques {
    var list = _allCheques.map((c) => {
      'id':          c.id,
      'number':      c.id.length >= 8 ? c.id.substring(0, 8).toUpperCase() : c.id.toUpperCase(),
      'beneficiary': c.beneficiaireNom ?? '—',
      'amount':      c.montantFormate,
      'date':        c.createdAt.length >= 16
          ? '${c.createdAt.substring(0, 10)}  ${c.createdAt.substring(11, 16)}'
          : c.createdAt.substring(0, 10),
      'status':      c.status.label,
    }).toList();

    // Mode pre-filter
    switch (widget.mode) {
      case EmissionsMode.pending:
        return list.where((c) => c['status'] == 'En attente').toList();
      case EmissionsMode.history:
        return list.where((c) => c['status'] == 'Validé' || c['status'] == 'Rejeté').toList();
      case EmissionsMode.all:
        return list;
    }
  }

  List<Map<String, dynamic>> get _filtered {
    if (_selectedFilter == 'Tous') return _cheques;
    return _cheques.where((c) => c['status'] == _selectedFilter).toList();
  }

  String get _bannerAmount {
    if (_allCheques.isEmpty) return '0,000 DT';
    switch (widget.mode) {
      case EmissionsMode.pending:
        final count = _cheques.length;
        return '$count chèque${count != 1 ? 's' : ''}';
      case EmissionsMode.history:
      case EmissionsMode.all:
        final total = _allCheques
            .where((c) => c.montantExtrait != null)
            .where((c) => widget.mode == EmissionsMode.history
                ? (c.status.label == 'Validé')
                : true)
            .fold(0.0, (sum, c) => sum + c.montantExtrait!);
        return '${total.toStringAsFixed(3)} DT';
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'Validé':  return const Color(0xFF059669);
      case 'Rejeté':  return AppColors.error;
      default:        return const Color(0xFFD97706);
    }
  }

  Color _statusBg(String status) {
    switch (status) {
      case 'Validé':  return const Color(0xFFD1FAE5);
      case 'Rejeté':  return AppColors.errorContainer;
      default:        return const Color(0xFFFEF3C7);
    }
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _filtered;
    final showFilterBar = _filters.length > 1;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.go(widget.homeRoute);
      },
      child: Scaffold(
        backgroundColor: AppColors.surfaceContainerLow,
        appBar: AppBar(
          title: Text(_title),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded),
            onPressed: () => context.go(widget.homeRoute),
          ),
        ),
        body: Column(
          children: [
            // Banner
            Container(
              width: double.infinity,
              color: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _bannerLabel,
                        style: TextStyle(fontSize: 13, color: AppColors.onSurfaceVariant),
                      ),
                      Text(
                        _isLoading ? '...' : _bannerAmount,
                        style: const TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w800,
                          color: AppColors.primary,
                        ),
                      ),
                    ],
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: AppColors.secondaryContainer,
                      borderRadius: BorderRadius.circular(100),
                    ),
                    child: Text(
                      '${_cheques.length} chèques',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: AppColors.primary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            // Filters (hidden if only one option)
            if (showFilterBar)
              SizedBox(
                height: 52,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  itemCount: _filters.length,
                  itemBuilder: (context, index) {
                    final filter = _filters[index];
                    final isSelected = _selectedFilter == filter;
                    return GestureDetector(
                      onTap: () => setState(() => _selectedFilter = filter),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        margin: const EdgeInsets.only(right: 8),
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                        decoration: BoxDecoration(
                          color: isSelected ? AppColors.primary : Colors.white,
                          borderRadius: BorderRadius.circular(100),
                          border: Border.all(
                            color: isSelected ? AppColors.primary : AppColors.outlineVariant,
                          ),
                        ),
                        child: Text(
                          filter,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: isSelected ? Colors.white : AppColors.onSurfaceVariant,
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            // List
            Expanded(
              child: _isLoading
                  ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
                  : filtered.isEmpty
                      ? Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.receipt_long_outlined, size: 48, color: AppColors.outlineVariant),
                              const SizedBox(height: 12),
                              Text(
                                widget.mode == EmissionsMode.pending
                                    ? 'Aucun chèque en attente'
                                    : widget.mode == EmissionsMode.history
                                        ? 'Aucun chèque traité'
                                        : 'Aucun chèque',
                                style: TextStyle(color: AppColors.onSurfaceVariant, fontSize: 15),
                              ),
                            ],
                          ),
                        )
                      : ListView.builder(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                          itemCount: filtered.length,
                          itemBuilder: (context, index) {
                            final cheque = filtered[index];
                            final raw = _allCheques.firstWhere((c) => c.id == cheque['id']);
                            return GestureDetector(
                              onTap: () => context.push('/cheque-detail',
                                  extra: {'cheque': raw, 'homeRoute': widget.homeRoute}),
                              child: Container(
                              margin: const EdgeInsets.only(bottom: 12),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(16),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withOpacity(0.04),
                                    blurRadius: 8,
                                    offset: const Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: ListTile(
                                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                leading: Container(
                                  width: 44,
                                  height: 44,
                                  decoration: BoxDecoration(
                                    color: _statusBg(cheque['status']),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: Icon(
                                    Icons.receipt_long_rounded,
                                    color: _statusColor(cheque['status']),
                                    size: 22,
                                  ),
                                ),
                                title: Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        'Réf. ${cheque['number']}',
                                        style: const TextStyle(
                                          fontSize: 14,
                                          fontWeight: FontWeight.w700,
                                          color: AppColors.onSurface,
                                        ),
                                      ),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                                      decoration: BoxDecoration(
                                        color: _statusBg(cheque['status']),
                                        borderRadius: BorderRadius.circular(100),
                                      ),
                                      child: Text(
                                        cheque['status'],
                                        style: TextStyle(
                                          fontSize: 11,
                                          fontWeight: FontWeight.w600,
                                          color: _statusColor(cheque['status']),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                subtitle: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const SizedBox(height: 4),
                                    Text(cheque['beneficiary'],
                                        style: const TextStyle(fontSize: 13, color: AppColors.onSurface)),
                                    const SizedBox(height: 2),
                                    Text(cheque['date'],
                                        style: TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant)),
                                  ],
                                ),
                                trailing: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(
                                      cheque['amount'],
                                      style: const TextStyle(
                                        fontSize: 15,
                                        fontWeight: FontWeight.w800,
                                        color: AppColors.primary,
                                      ),
                                    ),
                                    const SizedBox(width: 4),
                                    const Icon(Icons.chevron_right_rounded,
                                        color: AppColors.onSurfaceVariant, size: 20),
                                  ],
                                ),
                              ),
                            ));
                          },
                        ),
            ),
          ],
        ),
        bottomNavigationBar: AppBottomNav(
          currentIndex: 1,
          homeRoute: widget.homeRoute,
          showScanner: widget.showScanner,
          chequeRoute: widget.chequeRoute ?? '/emissions',
        ),
      ),
    );
  }
}
