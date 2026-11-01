enum ChequeStatus { enAttente, enTraitement, valide, rejete, fraudeDetectee }

extension ChequeStatusX on ChequeStatus {
  String get label {
    switch (this) {
      case ChequeStatus.enAttente:      return 'En attente';
      case ChequeStatus.enTraitement:   return 'En traitement';
      case ChequeStatus.valide:         return 'Validé';
      case ChequeStatus.rejete:         return 'Rejeté';
      case ChequeStatus.fraudeDetectee: return 'Fraude détectée';
    }
  }
}

ChequeStatus statusFromString(String s) {
  switch (s) {
    case 'EN_ATTENTE':      return ChequeStatus.enAttente;
    case 'EN_TRAITEMENT':   return ChequeStatus.enTraitement;
    case 'VALIDE':          return ChequeStatus.valide;
    case 'REJETE':          return ChequeStatus.rejete;
    case 'FRAUDE_DETECTEE': return ChequeStatus.fraudeDetectee;
    default:                return ChequeStatus.enAttente;
  }
}

class Cheque {
  final String id;
  final String? numeroCheque;
  final String? imageRectoUrl;
  final String? imageVersoUrl;
  final double? montantExtrait;
  final String? montantLettres;
  final String? beneficiaireNom;
  final String? dateEmission;
  final String? ribEmetteur;
  final ChequeStatus status;
  final double? aiScoreGlobal;
  final bool fraudeDetectee;
  final String? motifRejet;
  final String? source;
  final String createdAt;
  final String? validatedAt;

  const Cheque({
    required this.id,
    required this.status,
    required this.createdAt,
    required this.fraudeDetectee,
    this.numeroCheque,
    this.imageRectoUrl,
    this.imageVersoUrl,
    this.montantExtrait,
    this.montantLettres,
    this.beneficiaireNom,
    this.dateEmission,
    this.ribEmetteur,
    this.aiScoreGlobal,
    this.motifRejet,
    this.source,
    this.validatedAt,
  });

  factory Cheque.fromJson(Map<String, dynamic> json) => Cheque(
    id:              json['id'] as String,
    numeroCheque:    json['numeroCheque'] as String?,
    imageRectoUrl:   json['imageRectoUrl'] as String?,
    imageVersoUrl:   json['imageVersoUrl'] as String?,
    montantExtrait:  (json['montantExtrait'] as num?)?.toDouble(),
    montantLettres:  json['montantLettres'] as String?,
    beneficiaireNom: json['beneficiaireNom'] as String?,
    dateEmission:    json['dateEmission'] as String?,
    ribEmetteur:     json['ribEmetteur'] as String?,
    status:          statusFromString(json['status'] as String? ?? 'EN_ATTENTE'),
    aiScoreGlobal:   (json['aiScoreGlobal'] as num?)?.toDouble(),
    fraudeDetectee:  json['fraudeDetectee'] as bool? ?? false,
    motifRejet:      json['motifRejet'] as String?,
    source:          json['source'] as String?,
    createdAt:       json['createdAt'] as String? ?? DateTime.now().toIso8601String(),
    validatedAt:     json['validatedAt'] as String?,
  );

  String get montantFormate {
    if (montantExtrait == null) return '—';
    return '${montantExtrait!.toStringAsFixed(3)} DT';
  }
}

class MobileDashboardStats {
  final int totalCheques;
  final int enTraitement;
  final int valides;
  final int rejetes;
  final int enAttente;
  final double montantValide;
  final int totalEmissions;
  final int emissionsEnAttente;
  final int emissionsValidees;
  final double montantEnCours;

  const MobileDashboardStats({
    required this.totalCheques,
    required this.enTraitement,
    required this.valides,
    required this.rejetes,
    required this.enAttente,
    required this.montantValide,
    required this.totalEmissions,
    required this.emissionsEnAttente,
    required this.emissionsValidees,
    required this.montantEnCours,
  });

  factory MobileDashboardStats.fromJson(Map<String, dynamic> json) => MobileDashboardStats(
    totalCheques:      json['totalCheques'] as int? ?? 0,
    enTraitement:      json['enTraitement'] as int? ?? 0,
    valides:           json['valides'] as int? ?? 0,
    rejetes:           json['rejetes'] as int? ?? 0,
    enAttente:         json['enAttente'] as int? ?? 0,
    montantValide:     (json['montantValide'] as num?)?.toDouble() ?? 0,
    totalEmissions:    json['totalEmissions'] as int? ?? 0,
    emissionsEnAttente:json['emissionsEnAttente'] as int? ?? 0,
    emissionsValidees: json['emissionsValidees'] as int? ?? 0,
    montantEnCours:    (json['montantEnCours'] as num?)?.toDouble() ?? 0,
  );

  factory MobileDashboardStats.empty() => const MobileDashboardStats(
    totalCheques: 0, enTraitement: 0, valides: 0, rejetes: 0, enAttente: 0,
    montantValide: 0, totalEmissions: 0, emissionsEnAttente: 0, emissionsValidees: 0, montantEnCours: 0,
  );
}

class PagedCheques {
  final List<Cheque> content;
  final int totalElements;
  final int totalPages;
  final int currentPage;

  const PagedCheques({
    required this.content,
    required this.totalElements,
    required this.totalPages,
    required this.currentPage,
  });

  factory PagedCheques.fromJson(Map<String, dynamic> json) => PagedCheques(
    content:       (json['content'] as List<dynamic>?)
        ?.map((e) => Cheque.fromJson(e as Map<String, dynamic>))
        .toList() ?? [],
    totalElements: json['totalElements'] as int? ?? 0,
    totalPages:    json['totalPages'] as int? ?? 0,
    currentPage:   json['number'] as int? ?? 0,
  );
}
