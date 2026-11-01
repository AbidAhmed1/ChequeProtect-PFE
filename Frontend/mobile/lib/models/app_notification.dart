class AppNotification {
  final String id;
  final String userId;
  final String? chequeId;
  final String? userRole;
  final String sujet;
  final String contenu;
  bool isRead;
  final DateTime createdAt;

  AppNotification({
    required this.id,
    required this.userId,
    this.chequeId,
    this.userRole,
    required this.sujet,
    required this.contenu,
    required this.isRead,
    required this.createdAt,
  });

  factory AppNotification.fromJson(Map<String, dynamic> json) => AppNotification(
    id:        json['id'] as String,
    userId:    json['userId'] as String? ?? '',
    chequeId:  json['chequeId'] as String?,
    userRole:  json['userRole'] as String?,
    sujet:     json['sujet'] as String? ?? '',
    contenu:   json['contenu'] as String? ?? '',
    isRead:    json['read'] as bool? ?? json['isRead'] as bool? ?? false,
    createdAt: json['createdAt'] != null
        ? DateTime.tryParse(json['createdAt'] as String) ?? DateTime.now()
        : DateTime.now(),
  );

  String get category {
    final s = sujet.toLowerCase();
    if (s.contains('validé') || s.contains('✅')) return 'success';
    if (s.contains('rejeté') || s.contains('❌') || s.contains('fraude')) return 'warning';
    return 'info';
  }

  String get timeAgo {
    final diff = DateTime.now().difference(createdAt);
    if (diff.inMinutes < 1) return 'À l\'instant';
    if (diff.inMinutes < 60) return 'Il y a ${diff.inMinutes} min';
    if (diff.inHours < 24) return 'Il y a ${diff.inHours}h';
    if (diff.inDays == 1) return 'Hier';
    if (diff.inDays < 7) return 'Il y a ${diff.inDays} jours';
    return '${createdAt.day.toString().padLeft(2, '0')}/${createdAt.month.toString().padLeft(2, '0')}/${createdAt.year}';
  }
}