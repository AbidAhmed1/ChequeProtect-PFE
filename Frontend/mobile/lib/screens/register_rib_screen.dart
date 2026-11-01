import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../widgets/primary_button.dart';
import '../services/auth_service.dart';
import '../services/api_client.dart';

class RegisterRibScreen extends StatefulWidget {
  const RegisterRibScreen({super.key});

  @override
  State<RegisterRibScreen> createState() => _RegisterRibScreenState();
}

class _RegisterRibScreenState extends State<RegisterRibScreen> {
  final _formKey = GlobalKey<FormState>();
  final _ribController = TextEditingController();
  bool _isLoading = false;

  @override
  void dispose() {
    _ribController.dispose();
    super.dispose();
  }

  void _continue() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _isLoading = true);
    try {
      final resp = await AuthService.instance.ribInitiate(_ribController.text.trim());
      if (mounted) {
        context.go('/register/confirm-phone', extra: {
          'sessionId':       resp.sessionId,
          'telephoneMasque': resp.telephoneMasque ?? '**********',
        });
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message), backgroundColor: AppColors.error),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Connexion impossible. Vérifiez votre réseau.'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.go('/welcome');
      },
      child: Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded),
          onPressed: () => context.go('/welcome'),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 24),
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    color: AppColors.secondaryContainer,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Icon(
                    Icons.credit_card_rounded,
                    color: AppColors.primary,
                    size: 28,
                  ),
                ),
                const SizedBox(height: 24),
                const Text(
                  'Votre RIB',
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                    color: AppColors.onSurface,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Saisissez votre Relevé d\'Identité Bancaire pour vérifier votre compte.',
                  style: TextStyle(
                    fontSize: 15,
                    color: AppColors.onSurfaceVariant,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 36),
                TextFormField(
                  controller: _ribController,
                  keyboardType: TextInputType.number,
                  maxLength: 20,
                  decoration: InputDecoration(
                    labelText: 'Numéro RIB (20 chiffres)',
                    hintText: 'Ex : 08010011042001092378',
                    prefixIcon: const Icon(
                      Icons.credit_card_rounded,
                      color: AppColors.primary,
                    ),
                    labelStyle: const TextStyle(color: AppColors.onSurfaceVariant),
                    counterText: '',
                  ),
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return 'Veuillez saisir votre RIB';
                    }
                    if (!RegExp(r'^\d{20}$').hasMatch(value)) {
                      return 'Le RIB doit contenir exactement 20 chiffres';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 24),
                PrimaryButton(
                  label: 'Continuer',
                  onPressed: _continue,
                  isLoading: _isLoading,
                ),
                const SizedBox(height: 16),
                Center(
                  child: TextButton(
                    onPressed: () => context.go('/register/sans-rib'),
                    child: Text(
                      'Je n\'ai pas de RIB (Accès invité)',
                      style: TextStyle(
                        color: AppColors.primary,
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
    );
  }
}
