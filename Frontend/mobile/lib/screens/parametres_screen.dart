import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../theme.dart';
import '../widgets/app_bottom_nav.dart';

class ParametresScreen extends StatefulWidget {
  final String homeRoute;
  final bool showScanner;

  const ParametresScreen({
    super.key,
    this.homeRoute = '/home/titulaire',
    this.showScanner = false,
  });

  @override
  State<ParametresScreen> createState() => _ParametresScreenState();
}

class _ParametresScreenState extends State<ParametresScreen> {
  static const _kPush  = 'notif_push';
  static const _kEmail = 'notif_email';
  static const _kSms   = 'notif_sms';

  bool _pushNotifications  = true;
  bool _emailNotifications = false;
  bool _smsNotifications   = true;

  @override
  void initState() {
    super.initState();
    _loadPrefs();
  }

  Future<void> _loadPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted) {
      setState(() {
        _pushNotifications  = prefs.getBool(_kPush)  ?? true;
        _emailNotifications = prefs.getBool(_kEmail) ?? false;
        _smsNotifications   = prefs.getBool(_kSms)   ?? true;
      });
    }
  }

  Future<void> _setPush(bool v) async {
    setState(() => _pushNotifications = v);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kPush, v);
  }

  Future<void> _setEmail(bool v) async {
    setState(() => _emailNotifications = v);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kEmail, v);
  }

  Future<void> _setSms(bool v) async {
    setState(() => _smsNotifications = v);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kSms, v);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.go(widget.homeRoute);
      },
      child: Scaffold(
      backgroundColor: AppColors.surfaceContainerLow,
      appBar: AppBar(
        title: const Text('Paramètres'),
        automaticallyImplyLeading: false,
      ),
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SectionHeader(title: 'Compte'),
            _SettingContainer(
              children: [
                _SettingTile(
                  icon: Icons.person_rounded,
                  title: 'Informations personnelles',
                  subtitle: 'Voir et modifier vos informations',
                  onTap: () => context.push('/profil'),
                ),
                const Divider(height: 1, indent: 60),
                _SettingTile(
                  icon: Icons.receipt_long_rounded,
                  title: 'Mes émissions',
                  subtitle: 'Historique des chèques émis',
                  onTap: () => context.go('/emissions', extra: {'homeRoute': widget.homeRoute, 'showScanner': widget.showScanner}),
                ),
              ],
            ),
            _SectionHeader(title: 'Sécurité'),
            _SettingContainer(
              children: [
                _SettingTile(
                  icon: Icons.lock_rounded,
                  title: 'Changer le code PIN',
                  subtitle: 'Modifier votre code à 6 chiffres',
                  onTap: () => context.push('/changer-pin', extra: {'homeRoute': widget.homeRoute}),
                ),
              ],
            ),
            _SectionHeader(title: 'Notifications'),
            _SettingContainer(
              children: [
                _ToggleTile(
                  icon: Icons.notifications_rounded,
                  title: 'Notifications push',
                  subtitle: 'Alertes sur votre téléphone',
                  value: _pushNotifications,
                  onChanged: _setPush,
                ),
                const Divider(height: 1, indent: 60),
                _ToggleTile(
                  icon: Icons.email_rounded,
                  title: 'Notifications email',
                  subtitle: 'Alertes par e-mail',
                  value: _emailNotifications,
                  onChanged: _setEmail,
                ),
                const Divider(height: 1, indent: 60),
                _ToggleTile(
                  icon: Icons.sms_rounded,
                  title: 'Notifications SMS',
                  subtitle: 'Alertes par message texte',
                  value: _smsNotifications,
                  onChanged: _setSms,
                ),
              ],
            ),
            _SectionHeader(title: 'À propos'),
            _SettingContainer(
              children: [
                _SettingTile(
                  icon: Icons.info_outline_rounded,
                  title: 'Version de l\'application',
                  subtitle: '1.0.0',
                  onTap: () {},
                  showChevron: false,
                ),
                const Divider(height: 1, indent: 60),
                _SettingTile(
                  icon: Icons.description_rounded,
                  title: 'Conditions d\'utilisation',
                  subtitle: 'Lire les CGU',
                  onTap: () => context.push('/conditions'),
                ),
                const Divider(height: 1, indent: 60),
                _SettingTile(
                  icon: Icons.privacy_tip_rounded,
                  title: 'Politique de confidentialité',
                  subtitle: 'Données personnelles',
                  onTap: () => context.push('/confidentialite'),
                ),
                const Divider(height: 1, indent: 60),
                _SettingTile(
                  icon: Icons.chat_rounded,
                  title: 'Support & Réclamations',
                  subtitle: 'Chattez avec nous',
                  onTap: () => context.go('/chatbot', extra: {
                    'homeRoute': widget.homeRoute,
                    'showScanner': widget.showScanner,
                  }),
                ),
              ],
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
      bottomNavigationBar: AppBottomNav(
        currentIndex: 3,
        homeRoute: widget.homeRoute,
        showScanner: widget.showScanner,
      ),
    ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: AppColors.onSurfaceVariant,
          letterSpacing: 1.2,
        ),
      ),
    );
  }
}

class _SettingContainer extends StatelessWidget {
  final List<Widget> children;
  const _SettingContainer({required this.children});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(children: children),
    );
  }
}

class _SettingTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool showChevron;

  const _SettingTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.showChevron = true,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      onTap: onTap,
      leading: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: AppColors.secondaryContainer,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Icon(icon, color: AppColors.primary, size: 20),
      ),
      title: Text(
        title,
        style: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: AppColors.onSurface,
        ),
      ),
      subtitle: Text(
        subtitle,
        style: TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant),
      ),
      trailing: showChevron
          ? const Icon(Icons.chevron_right_rounded,
              color: AppColors.onSurfaceVariant, size: 20)
          : null,
    );
  }
}

class _ToggleTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  const _ToggleTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: AppColors.secondaryContainer,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Icon(icon, color: AppColors.primary, size: 20),
      ),
      title: Text(
        title,
        style: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: AppColors.onSurface,
        ),
      ),
      subtitle: Text(
        subtitle,
        style: TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant),
      ),
      trailing: Switch(
        value: value,
        onChanged: onChanged,
        activeColor: AppColors.primary,
      ),
    );
  }
}
