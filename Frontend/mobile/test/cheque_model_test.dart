import 'package:flutter_test/flutter_test.dart';
import 'package:chequepro_app/models/cheque.dart';

void main() {

  group('statusFromString — contrat backend/mobile', () {

    test('convertit correctement tous les statuts du backend', () {
      expect(statusFromString('EN_ATTENTE'),      equals(ChequeStatus.enAttente));
      expect(statusFromString('EN_TRAITEMENT'),   equals(ChequeStatus.enTraitement));
      expect(statusFromString('VALIDE'),          equals(ChequeStatus.valide));
      expect(statusFromString('REJETE'),          equals(ChequeStatus.rejete));
      expect(statusFromString('FRAUDE_DETECTEE'), equals(ChequeStatus.fraudeDetectee));
    });

    test('retourne enAttente pour tout statut inconnu (fallback sécurisé)', () {
      expect(statusFromString('NOUVEAU'),  equals(ChequeStatus.enAttente));
      expect(statusFromString(''),         equals(ChequeStatus.enAttente));
      expect(statusFromString('null'),     equals(ChequeStatus.enAttente));
    });
  });

  group('Cheque.fromJson', () {

    test('parse un chèque validé avec tous les champs renseignés', () {
      final json = {
        'id':              'cccccccc-0000-0000-0000-000000000001',
        'numeroCheque':    'TN-2026-00042',
        'beneficiaireNom': 'Salma Kammoun',
        'montantExtrait':  1250.500,
        'montantLettres':  'mille deux cent cinquante dinars',
        'status':          'VALIDE',
        'aiScoreGlobal':   0.92,
        'fraudeDetectee':  false,
        'createdAt':       '2026-05-21T09:00:00',
        'validatedAt':     '2026-05-21T10:15:00',
      };

      final cheque = Cheque.fromJson(json);

      expect(cheque.id,             equals('cccccccc-0000-0000-0000-000000000001'));
      expect(cheque.status,         equals(ChequeStatus.valide));
      expect(cheque.aiScoreGlobal,  equals(0.92));
      expect(cheque.fraudeDetectee, isFalse);
      expect(cheque.validatedAt,    isNotNull);
    });

    test('montantFormate affiche la valeur avec 3 décimales en DT', () {
      final json = {
        'id':             'cccc-0001',
        'montantExtrait': 500.0,
        'status':         'EN_ATTENTE',
        'fraudeDetectee': false,
        'createdAt':      '2026-05-21T09:00:00',
      };

      final cheque = Cheque.fromJson(json);

      expect(cheque.montantFormate, equals('500.000 DT'));
    });

    test('montantFormate retourne "—" si le montant est null (OCR non traité)', () {
      final json = {
        'id':             'cccc-0002',
        'status':         'EN_ATTENTE',
        'fraudeDetectee': false,
        'createdAt':      '2026-05-21T09:00:00',
      };

      final cheque = Cheque.fromJson(json);

      expect(cheque.montantFormate, equals('—'));
      expect(cheque.montantExtrait, isNull);
    });
  });

  group('PagedCheques.fromJson', () {

    test('parse une page avec contenu et métadonnées de pagination', () {
      final json = {
        'content': [
          {
            'id': 'id-001', 'status': 'VALIDE',
            'fraudeDetectee': false, 'createdAt': '2026-05-21T09:00:00'
          },
          {
            'id': 'id-002', 'status': 'EN_ATTENTE',
            'fraudeDetectee': false, 'createdAt': '2026-05-21T10:00:00'
          },
        ],
        'totalElements': 42,
        'totalPages':    5,
        'number':        0,
      };

      final paged = PagedCheques.fromJson(json);

      expect(paged.content.length,        equals(2));
      expect(paged.totalElements,         equals(42));
      expect(paged.totalPages,            equals(5));
      expect(paged.currentPage,           equals(0));
      expect(paged.content.first.status,  equals(ChequeStatus.valide));
    });
  });
}