import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme.dart';
import '../widgets/primary_button.dart';
import '../widgets/glass_card.dart';
import '../services/auth_service.dart';
import '../services/api_client.dart';

class RegisterGuestCompleteScreen extends StatefulWidget {
  final String sessionId;
  final String fullName;
  final String phone;
  final String email;
  final String cinNumber;

  const RegisterGuestCompleteScreen({
    super.key,
    required this.sessionId,
    this.fullName = '',
    this.phone = '',
    this.email = '',
    this.cinNumber = '',
  });

  @override
  State<RegisterGuestCompleteScreen> createState() =>
      _RegisterGuestCompleteScreenState();
}

class _RegisterGuestCompleteScreenState
    extends State<RegisterGuestCompleteScreen> {
  // Step 0 = email entry, 1 = enter PIN, 2 = confirm PIN
  int _step = 0;

  final _emailController = TextEditingController();
  final _emailFocus = FocusNode();
  String _emailError = '';

  final List<String> _pin = [];
  List<String> _firstPin = [];
  static const int _pinLength = 6;

  bool _isLoading = false;
  bool _isError = false;
  String _errorMessage = '';

  @override
  void initState() {
    super.initState();
    _step = 1; // Démarrer directement au PIN — email non obligatoire
    if (widget.email.isNotEmpty) _emailController.text = widget.email;
  }

  @override
  void dispose() {
    _emailController.dispose();
    _emailFocus.dispose();
    super.dispose();
  }

  void _onNextFromEmail() {
    final email = _emailController.text.trim();
    final emailRegex = RegExp(r'^[\w\-.]+@[\w\-.]+\.\w{2,}$');
    if (!emailRegex.hasMatch(email)) {
      setState(() => _emailError = 'Adresse email invalide.');
      return;
    }
    setState(() {
      _emailError = '';
      _step = 1;
    });
  }

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

    if (_step == 1) {
      setState(() {
        _firstPin = List.from(_pin);
        _pin.clear();
        _step = 2;
      });
    } else {
      if (_pin.join() == _firstPin.join()) {
        await _complete();
      } else {
        setState(() {
          _isError = true;
          _errorMessage = 'Les codes PIN ne correspondent pas. Recommencez.';
          _pin.clear();
          _firstPin.clear();
          _step = 1;
        });
        await Future.delayed(const Duration(milliseconds: 1500));
        if (mounted) setState(() { _isError = false; _errorMessage = ''; });
      }
    }
  }

  Future<void> _complete() async {
    setState(() => _isLoading = true);
    try {
      await AuthService.instance.kycComplete(
        sessionId:  widget.sessionId,
        fullName:   widget.fullName,
        phone:      widget.phone,
        pin:        _pin.join(),
        pinConfirm: _firstPin.join(),
        email:      _emailController.text.trim().isNotEmpty ? _emailController.text.trim() : null,
        cinNumber:  widget.cinNumber.isNotEmpty ? widget.cinNumber : null,
      );
      if (mounted) context.go('/home/beneficiaire');
    } on ApiException catch (e) {
      _showError(e.message);
    } catch (_) {
      _showError('Erreur lors de la création du compte.');
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
      _firstPin.clear();
      _step = 1;
    });
    Future.delayed(const Duration(milliseconds: 2500), () {
      if (mounted) setState(() { _isError = false; _errorMessage = ''; });
    });
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) {
          if (_step > 0) {
            setState(() {
              _pin.clear();
              _firstPin.clear();
              _step = _step == 2 ? 1 : 0;
              _isError = false;
            });
          } else {
            context.go('/register/guest/selfie',
                extra: {'sessionId': widget.sessionId});
          }
        }
      },
      child: Scaffold(
        backgroundColor: AppColors.surfaceContainerLow,
        appBar: AppBar(
          title: Text(_step == 0 ? 'Votre email' : 'Code PIN'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded),
            onPressed: () {
              if (_step > 0) {
                setState(() {
                  _pin.clear();
                  _firstPin.clear();
                  _step = _step == 2 ? 1 : 0;
                  _isError = false;
                });
              } else {
                context.go('/register/guest/selfie',
                    extra: {'sessionId': widget.sessionId});
              }
            },
          ),
        ),
        body: _step == 0 ? _buildEmailStep() : _buildPinStep(),
      ),
    );
  }

  Widget _buildEmailStep() {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 24),
            const Text(
              'Créez votre compte',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.w800,
                color: AppColors.onSurface,
                letterSpacing: -0.5,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Renseignez votre adresse email pour accéder à votre espace bénéficiaire.',
              style: TextStyle(
                fontSize: 14,
                color: AppColors.onSurfaceVariant,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 32),
            Container(
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.04),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Adresse email',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: AppColors.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _emailController,
                      focusNode: _emailFocus,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.done,
                      onSubmitted: (_) => _onNextFromEmail(),
                      decoration: InputDecoration(
                        hintText: 'exemple@email.com',
                        prefixIcon: const Icon(Icons.email_outlined, size: 20),
                        errorText: _emailError.isNotEmpty ? _emailError : null,
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
                          borderSide: BorderSide(color: AppColors.primary, width: 2),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const Spacer(),
            PrimaryButton(
              label: 'Suivant',
              onPressed: _onNextFromEmail,
              icon: const Icon(Icons.arrow_forward_rounded,
                  color: Colors.white, size: 20),
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _buildPinStep() {
    return SafeArea(
      child: Column(
        children: [
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
              _step == 1 ? Icons.lock_rounded : Icons.lock_reset_rounded,
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
                  _step == 1 ? 'Créez votre code PIN' : 'Confirmez votre code PIN',
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    color: AppColors.onSurface,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _step == 1
                      ? 'Choisissez un code à 6 chiffres'
                      : 'Saisissez à nouveau votre code',
                  style: TextStyle(
                    fontSize: 14,
                    color: AppColors.onSurfaceVariant,
                  ),
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
                  Icon(Icons.error_outline_rounded,
                      color: AppColors.error, size: 18),
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
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _StepDot(active: _step == 1, done: _step > 1),
              const SizedBox(width: 8),
              _StepDot(active: _step == 2, done: false),
            ],
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
                        child: CircularProgressIndicator(
                            color: AppColors.primary),
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
                              margin:
                                  const EdgeInsets.symmetric(horizontal: 8),
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
                                    ? [
                                        BoxShadow(
                                          color: AppColors.primary
                                              .withOpacity(0.4),
                                          blurRadius: 6,
                                        )
                                      ]
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
                            _KeypadButton(
                                label: '0', onTap: () => _onKey('0')),
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
          if (_step == 2)
            TextButton(
              onPressed: () => setState(() {
                _step = 1;
                _pin.clear();
                _firstPin.clear();
                _isError = false;
              }),
              child: Text('Recommencer',
                  style: TextStyle(color: AppColors.onSurfaceVariant)),
            ),
          const SizedBox(height: 24),
        ],
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
          border: Border.all(
              color: AppColors.outlineVariant.withOpacity(0.5)),
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
