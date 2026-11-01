import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../widgets/glass_card.dart';
import '../services/auth_service.dart';
import '../services/api_client.dart';

class ChangerCodePinScreen extends StatefulWidget {
  final String homeRoute;
  const ChangerCodePinScreen({super.key, this.homeRoute = '/home/titulaire'});

  @override
  State<ChangerCodePinScreen> createState() => _ChangerCodePinScreenState();
}

class _ChangerCodePinScreenState extends State<ChangerCodePinScreen> {
  static const int _pinLength = 6;

  // step 0 = current PIN, step 1 = new PIN, step 2 = confirm new PIN
  int _step = 0;
  final List<String> _pin = [];
  List<String> _currentPin = [];
  List<String> _newPin = [];

  bool _isError = false;
  bool _isLoading = false;
  String _errorMessage = '';

  static const _titles = [
    'Code PIN actuel',
    'Nouveau code PIN',
    'Confirmer le nouveau PIN',
  ];
  static const _subtitles = [
    'Saisissez votre code actuel',
    'Choisissez un code à 6 chiffres',
    'Saisissez à nouveau le nouveau code',
  ];

  void _onKey(String value) {
    if (_pin.length < _pinLength) {
      setState(() {
        _pin.add(value);
        _isError = false;
        _errorMessage = '';
      });
      if (_pin.length == _pinLength) _onPinComplete();
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

    if (_step == 0) {
      setState(() {
        _currentPin = List.from(_pin);
        _pin.clear();
        _step = 1;
      });
    } else if (_step == 1) {
      setState(() {
        _newPin = List.from(_pin);
        _pin.clear();
        _step = 2;
      });
    } else {
      if (_pin.join() == _newPin.join()) {
        await _doChangePin();
      } else {
        setState(() {
          _isError = true;
          _errorMessage = 'Les codes PIN ne correspondent pas. Recommencez.';
          _pin.clear();
          _newPin.clear();
          _step = 1;
        });
        await Future.delayed(const Duration(milliseconds: 1500));
        if (mounted) setState(() { _isError = false; _errorMessage = ''; });
      }
    }
  }

  Future<void> _doChangePin() async {
    setState(() => _isLoading = true);
    try {
      await AuthService.instance.changePin(
        _currentPin.join(),
        _newPin.join(),
        _pin.join(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Code PIN modifié avec succès'),
          backgroundColor: const Color(0xFF059669),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      );
      context.go(widget.homeRoute);
    } on ApiException catch (e) {
      _showError(e.statusCode == 401
          ? 'Code PIN actuel incorrect.'
          : e.message);
    } catch (_) {
      _showError('Erreur réseau. Vérifiez votre connexion.');
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
      if (_step == 2) { _newPin.clear(); _step = 1; }
      if (msg.contains('actuel')) { _currentPin.clear(); _step = 0; }
    });
    Future.delayed(const Duration(milliseconds: 2000), () {
      if (mounted) setState(() { _isError = false; _errorMessage = ''; });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
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
                  onPressed: () => context.go(widget.homeRoute),
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
                child: const Icon(Icons.lock_reset_rounded, color: Colors.white, size: 36),
              ),
              const SizedBox(height: 24),
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 250),
                child: Column(
                  key: ValueKey(_step),
                  children: [
                    Text(
                      _titles[_step],
                      style: const TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w700,
                        color: AppColors.onSurface,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      _subtitles[_step],
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
              const SizedBox(height: 24),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(3, (i) => _StepDot(
                  active: _step == i,
                  done: _step > i,
                )),
              ),
              const SizedBox(height: 24),
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
                                        ? [BoxShadow(
                                            color: AppColors.primary.withOpacity(0.4),
                                            blurRadius: 6)]
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
                                _KeypadButton(
                                    icon: Icons.backspace_outlined,
                                    onTap: _onBackspace),
                              ],
                            ),
                          ],
                        ),
                ),
              ),
              const Spacer(),
              if (_step > 0)
                TextButton(
                  onPressed: () => setState(() {
                    _step = 0;
                    _pin.clear();
                    _currentPin.clear();
                    _newPin.clear();
                    _isError = false;
                  }),
                  child: Text('Recommencer',
                      style: TextStyle(color: AppColors.onSurfaceVariant)),
                ),
              const SizedBox(height: 24),
            ],
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
      margin: const EdgeInsets.symmetric(horizontal: 4),
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
