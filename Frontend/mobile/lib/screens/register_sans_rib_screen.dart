import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../widgets/primary_button.dart';

class RegisterSansRibScreen extends StatefulWidget {
  const RegisterSansRibScreen({super.key});

  @override
  State<RegisterSansRibScreen> createState() => _RegisterSansRibScreenState();
}

class _RegisterSansRibScreenState extends State<RegisterSansRibScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nomController = TextEditingController();
  final _prenomController = TextEditingController();
  final _cinController = TextEditingController();
  final _dateNaissanceController = TextEditingController();
  final _adresseController = TextEditingController();
  final _villeController = TextEditingController();
  final _codePostalController = TextEditingController();
  final _telephoneController = TextEditingController();
  final _emailController = TextEditingController();
  bool _isLoading = false;

  @override
  void dispose() {
    _nomController.dispose();
    _prenomController.dispose();
    _cinController.dispose();
    _dateNaissanceController.dispose();
    _adresseController.dispose();
    _villeController.dispose();
    _codePostalController.dispose();
    _telephoneController.dispose();
    _emailController.dispose();
    super.dispose();
  }

  void _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _isLoading = true);
    await Future.delayed(const Duration(milliseconds: 900));
    if (mounted) {
      setState(() => _isLoading = false);
      context.go('/register/guest/id', extra: {
        'fullName':  '${_prenomController.text.trim()} ${_nomController.text.trim()}',
        'phone':     '+216${_telephoneController.text.trim()}',
        'email':     _emailController.text.trim(),
        'cinNumber': _cinController.text.trim(),
      });
    }
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime(now.year - 25, now.month, now.day),
      firstDate: DateTime(1920),
      lastDate: DateTime(now.year - 18, now.month, now.day),
      helpText: 'Date de naissance',
      locale: const Locale('fr'),
    );
    if (picked != null) {
      _dateNaissanceController.text =
          '${picked.day.toString().padLeft(2, '0')}/${picked.month.toString().padLeft(2, '0')}/${picked.year}';
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.go('/register/rib');
      },
      child: Scaffold(
        backgroundColor: AppColors.surfaceContainerLow,
        appBar: AppBar(
          title: const Text('Inscription sans RIB'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded),
            onPressed: () => context.go('/register/rib'),
          ),
        ),
        body: SafeArea(
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Header
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppColors.secondaryContainer,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: AppColors.primary,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(Icons.person_add_rounded,
                              color: Colors.white, size: 22),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'Accès sans RIB',
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.primary,
                                ),
                              ),
                              Text(
                                'Renseignez vos informations personnelles pour créer votre compte.',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: AppColors.onSurfaceVariant,
                                  height: 1.4,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),

                  // ── État civil ──────────────────────────────────────────
                  _SectionTitle(title: 'État civil'),
                  const SizedBox(height: 12),
                  _FieldCard(children: [
                    _Field(
                      controller: _nomController,
                      label: 'Nom de famille',
                      hint: 'Ben Ali',
                      icon: Icons.badge_rounded,
                      textCapitalization: TextCapitalization.words,
                      validator: _required,
                    ),
                    const SizedBox(height: 16),
                    _Field(
                      controller: _prenomController,
                      label: 'Prénom',
                      hint: 'Jean',
                      icon: Icons.person_rounded,
                      textCapitalization: TextCapitalization.words,
                      validator: _required,
                    ),
                    const SizedBox(height: 16),
                    // Date de naissance (date picker)
                    GestureDetector(
                      onTap: _pickDate,
                      child: AbsorbPointer(
                        child: _Field(
                          controller: _dateNaissanceController,
                          label: 'Date de naissance',
                          hint: 'JJ/MM/AAAA',
                          icon: Icons.cake_rounded,
                          keyboardType: TextInputType.datetime,
                          validator: _required,
                          suffixIcon: const Icon(Icons.calendar_today_rounded,
                              size: 18),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    _Field(
                      controller: _cinController,
                      label: 'Numéro de carte d\'identité',
                      hint: '12345678',
                      icon: Icons.credit_card_rounded,
                      keyboardType: TextInputType.number,
                      maxLength: 8,
                      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) return 'Ce champ est obligatoire';
                        if (v.trim().length != 8) return 'Le numéro CIN doit contenir 8 chiffres';
                        return null;
                      },
                    ),
                  ]),
                  const SizedBox(height: 20),

                  // ── Adresse ─────────────────────────────────────────────
                  _SectionTitle(title: 'Adresse de résidence'),
                  const SizedBox(height: 12),
                  _FieldCard(children: [
                    _Field(
                      controller: _adresseController,
                      label: 'Adresse',
                      hint: '12 rue de la Paix',
                      icon: Icons.home_rounded,
                      textCapitalization: TextCapitalization.sentences,
                      validator: _required,
                    ),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        Expanded(
                          flex: 2,
                          child: _Field(
                            controller: _villeController,
                            label: 'Ville',
                            hint: 'Paris',
                            icon: Icons.location_city_rounded,
                            textCapitalization: TextCapitalization.words,
                            validator: _required,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          flex: 1,
                          child: _Field(
                            controller: _codePostalController,
                            label: 'Code postal',
                            hint: '1000',
                            icon: Icons.markunread_mailbox_rounded,
                            keyboardType: TextInputType.number,
                            maxLength: 4,
                            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                            validator: (v) {
                              if (v == null || v.trim().isEmpty) return 'Requis';
                              if (v.trim().length != 4) return 'Invalide';
                              return null;
                            },
                          ),
                        ),
                      ],
                    ),
                  ]),
                  const SizedBox(height: 20),

                  // ── Contact ─────────────────────────────────────────────
                  _SectionTitle(title: 'Coordonnées'),
                  const SizedBox(height: 12),
                  _FieldCard(children: [
                    _Field(
                      controller: _telephoneController,
                      label: 'Numéro de téléphone',
                      hint: '12 345 678',
                      icon: Icons.phone_rounded,
                      keyboardType: TextInputType.phone,
                      maxLength: 8,
                      prefixText: '+216 ',
                      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) {
                          return 'Veuillez saisir votre numéro';
                        }
                        if (v.trim().length != 8) return 'Numéro invalide (8 chiffres)';
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),
                    _Field(
                      controller: _emailController,
                      label: 'Adresse e-mail',
                      hint: 'jean.dupont@email.com',
                      icon: Icons.email_rounded,
                      keyboardType: TextInputType.emailAddress,
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) {
                          return 'Veuillez saisir votre email';
                        }
                        if (!v.contains('@')) return 'Email invalide';
                        return null;
                      },
                    ),
                  ]),
                  const SizedBox(height: 12),

                  // Notice
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEF3C7),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.info_outline_rounded,
                            color: Color(0xFFD97706), size: 18),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            'Vous devrez ensuite photographier votre carte d\'identité et prendre un selfie pour valider votre identité.',
                            style: TextStyle(
                              fontSize: 12,
                              color: const Color(0xFF92400E),
                              height: 1.4,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 28),

                  PrimaryButton(
                    label: 'Continuer vers la vérification',
                    onPressed: _submit,
                    isLoading: _isLoading,
                    icon: const Icon(Icons.arrow_forward_rounded,
                        color: Colors.white, size: 20),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  String? _required(String? v) {
    if (v == null || v.trim().isEmpty) return 'Ce champ est obligatoire';
    return null;
  }
}

class _SectionTitle extends StatelessWidget {
  final String title;
  const _SectionTitle({required this.title});

  @override
  Widget build(BuildContext context) {
    return Text(
      title.toUpperCase(),
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w700,
        color: AppColors.onSurfaceVariant,
        letterSpacing: 1.2,
      ),
    );
  }
}

class _FieldCard extends StatelessWidget {
  final List<Widget> children;
  const _FieldCard({required this.children});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: children,
      ),
    );
  }
}

class _Field extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;
  final IconData icon;
  final TextInputType keyboardType;
  final TextCapitalization textCapitalization;
  final String? Function(String?) validator;
  final Widget? suffixIcon;
  final int? maxLength;
  final String? prefixText;
  final List<TextInputFormatter>? inputFormatters;

  const _Field({
    required this.controller,
    required this.label,
    required this.hint,
    required this.icon,
    required this.validator,
    this.keyboardType = TextInputType.text,
    this.textCapitalization = TextCapitalization.none,
    this.suffixIcon,
    this.maxLength,
    this.prefixText,
    this.inputFormatters,
  });

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      keyboardType: keyboardType,
      textCapitalization: textCapitalization,
      maxLength: maxLength,
      inputFormatters: inputFormatters,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        prefixIcon: Icon(icon, color: AppColors.primary, size: 20),
        prefixText: prefixText,
        prefixStyle: const TextStyle(color: Color(0xFF1A1A2E), fontSize: 13),
        suffixIcon: suffixIcon,
        counterText: '',
        labelStyle: TextStyle(color: AppColors.onSurfaceVariant, fontSize: 13),
        hintStyle: TextStyle(color: AppColors.onSurfaceVariant.withOpacity(0.5), fontSize: 13),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: AppColors.outlineVariant),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: AppColors.outlineVariant),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: AppColors.error),
        ),
        filled: true,
        fillColor: AppColors.surfaceContainerLow,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      ),
      validator: validator,
    );
  }
}