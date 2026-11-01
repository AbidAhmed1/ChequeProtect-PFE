import 'api_client.dart';
import '../models/app_notification.dart';

class NotificationService {
  NotificationService._();
  static final NotificationService instance = NotificationService._();

  Future<List<AppNotification>> getNotifications(String userId) async {
    final list = await ApiClient.instance.getList('/api/notifications/user/$userId');
    return list
        .whereType<Map<String, dynamic>>()
        .map(AppNotification.fromJson)
        .toList();
  }

  Future<void> markAllRead(String userId) async {
    await ApiClient.instance.patch('/api/notifications/user/$userId/read-all');
  }

  Future<void> markRead(String notifId) async {
    await ApiClient.instance.patch('/api/notifications/$notifId/read');
  }
}
