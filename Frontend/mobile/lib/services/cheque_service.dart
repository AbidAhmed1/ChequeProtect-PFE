import 'dart:io';
import 'api_client.dart';
import '../models/cheque.dart';

class ChequeService {
  ChequeService._();
  static final ChequeService instance = ChequeService._();

  // ── Upload ────────────────────────────────────────────────────────────────

  Future<Cheque> uploadCheque(File recto, {File? verso}) async {
    final files = <String, File>{'recto': recto};
    if (verso != null) files['verso'] = verso;

    final json = await ApiClient.instance.postMultipart(
      '/api/cheques/upload',
      files,
    );
    return Cheque.fromJson(json);
  }

  // ── Liste paginée ─────────────────────────────────────────────────────────

  Future<PagedCheques> getMesCheques({
    int page = 0,
    int size = 10,
    String? statut,
    String espace = 'beneficiaire',
  }) async {
    final params = <String, String>{
      'page': '$page',
      'size': '$size',
      'espace': espace,
      if (statut != null && statut.isNotEmpty) 'statut': statut,
    };
    final json = await ApiClient.instance.get('/api/cheques/mes-cheques', queryParams: params);
    return PagedCheques.fromJson(json);
  }

  // ── Détail ────────────────────────────────────────────────────────────────

  Future<Cheque> getChequeById(String id) async {
    final json = await ApiClient.instance.get('/api/cheques/$id');
    return Cheque.fromJson(json);
  }

  // ── Dashboard stats ───────────────────────────────────────────────────────

  Future<MobileDashboardStats> getDashboardStats({String espace = 'beneficiaire'}) async {
    try {
      final json = await ApiClient.instance.get(
        '/api/cheques/mobile/stats',
        queryParams: {'espace': espace},
      );
      return MobileDashboardStats.fromJson(json);
    } catch (_) {
      return MobileDashboardStats.empty();
    }
  }
}
