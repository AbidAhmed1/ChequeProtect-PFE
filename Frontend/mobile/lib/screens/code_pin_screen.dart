import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../widgets/glass_card.dart';
import '../services/auth_service.dart';
import '../services/api_client.dart';

class CodePinScreen extends StatefulWidget {
  final bool loginMode;
  final String? telephone;
  final String? sessionId;
  final String? tokenInscription;

  const CodePinScreen({
    super.key,
    this.loginMode = false,
    this.telephone,
    this.sessionId,
    this.tokenInscription,
  });

  @override
  State<CodePinScreen> createState() => _CodePinScreenState();
}

class _CodePinScreenState extends State<CodePinScreen> {
  final List<String> _pin = [];
  static const int _pinLength = 6;

  int _step = 0;
  List<String> _firstPin = [];
  bool _isError = false;
  bool _isLoading = false;
  String _errorMessage = '';

  void _onKey(String value) {
    if (_pin.length < _pinLength) {
      setState(() {
        _pin.add(value);
        _isError = false;
        _errorMessage = '';
      });
      if (_pin.length == _pinLength) {
        _onPinComplete();
      }
    }
  }

  void _onBackspace() {
    if (_pin.isNotEmpty) {
      setState(() {
        _pin.removeLast();
        _isError = false;
        _errorMessage = '';
      });
    }
  }

  Future<void> _onPinComplete() async {
    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;

    if (widget.loginMode) {
      await _doLogin();
      return;
    }

    if (_step == 0) {
      setState(() {
        _firstPin = List.from(_pin);
        _pin.clear();
        _step = 1;
      });
    } else {
      if (_pin.join() == _firstPin.join()) {
        await _doCreatePin();
      } else {
        setState(() {
          _isError = true;
          _errorMessage = 'Les codes PIN ne correspondent pas. Recommencez.';
          _pin.clear();
          _firstPin.clear();
          _step = 0;
        });
        await Future.delayed(const Duration(milliseconds: 1500));
        if (mounted) setState(() { _isError = false; _errorMessage = ''; });
      }
    }
  }

  Future<void> _doLogin() async {
    if (widget.telephone == null) {
      _showError('Numéro de téléphone manquant.');
      return;
    }
    setState(() => _isLoading = true);
    try {
      await AuthService.instance.loginWithPin(widget.telephone!, _pin.join());
      if (mounted) context.go('/select-space');
    } on ApiException catch (e) {
      if (e.statusCode == 401) {
        _showError('Code PIN incorrect.');
      } else if (e.statusCode == 404) {
        _showError('Numéro de téléphone non enregistré. Vérifiez votre numéro.');
      } else {
        _showError(e.message);
      }
    } catch (_) {
      _showError('Connexion impossible. Vérifiez votre réseau.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _doCreatePin() async {
    if (widget.sessionId == null || widget.tokenInscription == null) {
      // Création locale (pas de session backend) — flux non connecté
      if (mounted) context.go('/select-space');
      return;
    }
    setState(() => _isLoading = true);
    try {
      await AuthService.instance.ribSetPin(
        widget.sessionId!,
        _pin.join(),
        _firstPin.join(),
        widget.tokenInscription!,
      );
      if (mounted) context.go('/select-space');
    } on ApiException catch (e) {
      _showError(e.message);
    } catch (_) {
      _showError('Erreur lors de la création du PIN.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showError(String msg) {
    if (!mounted) return;
    setState(() {
      _isError = true;
      _errorMessage = msg;
      _pin.clear();
    });
    Future.delayed(const Duration(milliseconds: 2000), () {
      if (mounted) setState(() { _isError = false; _errorMessage = ''; });
    });
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.go('/welcome');
      },
      child: Scaffold(
        body: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              colors: [AppColors.surfaceContainerLow, AppColors.background],
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
            ),
          ),
          child: SafeArea(
            child: Column(
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: IconButton(
                    icon: const Icon(Icons.arrow_back_ios_new_rounded),
                    color: AppColors.onSurface,
                    onPressed: () => context.go('/welcome'),
                  ),
                ),
                const SizedBox(height: 16),
                Container(
                  width: 72,
                  height: 72,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [AppColors.primary, AppColors.primaryContainer],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: [
                      BoxShadow(
                        color: AppColors.primary.withOpacity(0.35),
                        blurRadius: 16,
                        offset: const Offset(0, 6),
                      ),
                    ],
                  ),
                  child: Icon(
                    _step == 0 ? Icons.lock_rounded : Icons.lock_reset_rounded,
                    color: Colors.white,
                    size: 36,
                  ),
                ),
                const SizedBox(height: 24),
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 250),
                  child: Column(
                    key: ValueKey(_step),
                    children: [
                      Text(
                        widget.loginMode
                            ? 'Saisissez votre code PIN'
                            : (_step == 0 ? 'Créez votre code PIN' : 'Confirmez votre code PIN'),
                        style: const TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w700,
                          color: AppColors.onSurface,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        widget.loginMode
                            ? 'Entrez votre code à 6 chiffres'
                            : (_step == 0
                                ? 'Choisissez un code à 6 chiffres'
                                : 'Saisissez à nouveau votre code'),
                        style: TextStyle(fontSize: 14, color: AppColors.onSurfaceVariant),
                      ),
                    ],
                  ),
                ),
                if (_isError) ...[
                  const SizedBox(height: 12),
                  Container(
                    margin: const EdgeInsets.symmetric(horizontal: 32),
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppColors.errorContainer,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.error_outline_rounded, color: AppColors.error, size: 18),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _errorMessage,
                            style: TextStyle(
                              fontSize: 13,
                              color: AppColors.error,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 32),
                if (!widget.loginMode) ...[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _StepDot(active: _step == 0, done: _step > 0),
                      const SizedBox(width: 8),
                      _StepDot(active: _step == 1, done: false),
                    ],
                  ),
                  const SizedBox(height: 24),
                ],
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  child: GlassCard(
                    borderRadius: 24,
                    opacity: 0.85,
                    color: Colors.white,
                    child: _isLoading
                        ? const SizedBox(
                            height: 120,
                            child: Center(
                              child: CircularProgressIndicator(color: AppColors.primary),
                            ),
                          )
                        : Column(
                            children: [
                              Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: List.generate(_pinLength, (index) {
                                  final filled = index < _pin.length;
                                  return AnimatedContainer(
                                    duration: const Duration(milliseconds: 200),
                                    margin: const EdgeInsets.symmetric(horizontal: 8),
                                    width: filled ? 16 : 14,
                                    height: filled ? 16 : 14,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      color: _isError
                                          ? AppColors.error
                                          : filled
                                              ? AppColors.primary
                                              : AppColors.outlineVariant,
                                      boxShadow: filled && !_isError
                                          ? [BoxShadow(color: AppColors.primary.withOpacity(0.4), blurRadius: 6)]
                                          : null,
                                    ),
                                  );
                                }),
                              ),
                              const SizedBox(height: 32),
                              for (var row = 0; row < 3; row++) ...[
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                                  children: [
                                    for (var col = 1; col <= 3; col++)
                                      _KeypadButton(
                                        label: '${row * 3 + col}',
                                        onTap: () => _onKey('${row * 3 + col}'),
                                      ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                              ],
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                                children: [
                                  const SizedBox(width: 72),
                                  _KeypadButton(label: '0', onTap: () => _onKey('0')),
                                  _KeypadButton(icon: Icons.backspace_outlined, onTap: _onBackspace),
                                ],
                              ),
                            ],
                          ),
                  ),
                ),
                const Spacer(),
                if (!widget.loginMode && _step == 1)
                  TextButton(
                    onPressed: () => setState(() {
                      _step = 0;
                      _pin.clear();
                      _firstPin.clear();
                      _isError = false;
                    }),
                    child: Text('Recommencer',
                        style: TextStyle(color: AppColors.onSurfaceVariant)),
                  )
                else if (widget.loginMode) ...[
                  TextButton(
                    onPressed: () => context.push('/pin-oublie'),
                    child: Text('Code PIN oublié ?',
                        style: TextStyle(color: AppColors.primary)),
                  ),
                  TextButton(
                    onPressed: () => context.go('/login'),
                    child: Text(
                      'Se connecter avec un autre numéro',
                      style: TextStyle(
                        color: AppColors.onSurfaceVariant,
                        fontSize: 13,
                      ),
                    ),
                  ),
                ]
                else
                  TextButton(
                    onPressed: () => context.push('/pin-oublie'),
                    child: Text('Code PIN oublié ?',
                        style: TextStyle(color: AppColors.primary)),
                  ),
                const SizedBox(height: 24),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StepDot extends StatelessWidget {
  final bool active;
  final bool done;
  const _StepDot({required this.active, required this.done});

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 250),
      width: active ? 24 : 8,
      height: 8,
      decoration: BoxDecoration(
        color: active || done ? AppColors.primary : AppColors.outlineVariant,
        borderRadius: BorderRadius.circular(4),
      ),
    );
  }
}

class _KeypadButton extends StatelessWidget {
  final String? label;
  final IconData? icon;
  final VoidCallback onTap;
  const _KeypadButton({this.label, this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 72,
        height: 56,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: AppColors.surfaceContainerLow,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.outlineVariant.withOpacity(0.5)),
        ),
        child: icon != null
            ? Icon(icon, color: AppColors.onSurface, size: 22)
            : Text(
                label!,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w600,
                  color: AppColors.onSurface,
                ),
              ),
      ),
    );
  }
}
