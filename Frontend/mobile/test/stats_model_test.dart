import 'package:flutter_test/flutter_test.dart';
import 'package:chequepro_app/models/cheque.dart';

void main() {

  group('MobileDashboardStats.fromJson', () {

    test('parse correctement les statistiques complètes du bénéficiaire', () {
      final json = {
        'totalCheques':        12,
        'enTraitement':         1,
        'valides':              8,
        'rejetes':              2,
        'enAttente':            1,
        'montantValide':     4500.750,
        'totalEmissions':      10,
        'emissionsEnAttente':   0,
        'emissionsValidees':    9,
        'montantEnCours':     200.000,
      };

      final stats = MobileDashboardStats.fromJson(json);

      expect(stats.totalCheques,   equals(12));
      expect(stats.valides,        equals(8));
      expect(stats.rejetes,        equals(2));
      expect(stats.montantValide,  equals(4500.750));
      expect(stats.montantEnCours, equals(200.000));
    });

    test('gère les champs manquants avec des zéros (réponse backend partielle)', () {
      final json = {
        'totalCheques': 3,
        'valides':      2,
      };

      final stats = MobileDashboardStats.fromJson(json);

      expect(stats.totalCheques,  equals(3));
      expect(stats.valides,       equals(2));
      expect(stats.rejetes,       equals(0));
      expect(stats.montantValide, equals(0.0));
    });
  });

  group('MobileDashboardStats.empty()', () {

    test('retourne un objet neutre quand le serveur est inaccessible', () {
      final empty = MobileDashboardStats.empty();

      expect(empty.totalCheques,   equals(0));
      expect(empty.valides,        equals(0));
      expect(empty.rejetes,        equals(0));
      expect(empty.montantValide,  equals(0.0));
      expect(empty.montantEnCours, equals(0.0));
    });
  });

  group('ChequeStatusX.label', () {

    test('retourne le bon libellé en français pour chaque statut', () {
      expect(ChequeStatus.enAttente.label,      equals('En attente'));
      expect(ChequeStatus.enTraitement.label,   equals('En traitement'));
      expect(ChequeStatus.valide.label,         equals('Validé'));
      expect(ChequeStatus.rejete.label,         equals('Rejeté'));
      expect(ChequeStatus.fraudeDetectee.label, equals('Fraude détectée'));
    });

    test('tous les statuts ont un label non vide', () {
      for (final status in ChequeStatus.values) {
        expect(status.label, isNotEmpty,
            reason: 'Le statut $status n\'a pas de label défini');
      }
    });
  });
}