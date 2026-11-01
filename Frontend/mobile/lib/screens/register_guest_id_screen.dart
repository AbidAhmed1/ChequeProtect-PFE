import 'dart:io';
import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image/image.dart' as img;
import '../theme.dart';
import '../widgets/primary_button.dart';
import '../services/auth_service.dart';
import '../services/api_client.dart';

// Returns [laplacian_variance, mean_brightness]
List<double> _analyzeImageCin(Uint8List bytes) {
  final decoded = img.decodeImage(bytes);
  if (decoded == null) return [999, 128];
  final resized = img.copyResize(decoded, width: 120);
  double sumLap = 0, sumLapSq = 0, sumBright = 0;
  int n = 0;
  for (int y = 1; y < resized.height - 1; y++) {
    for (int x = 1; x < resized.width - 1; x++) {
      final p  = resized.getPixel(x, y);
      final pt = resized.getPixel(x, y - 1);
      final pb = resized.getPixel(x, y + 1);
      final pl = resized.getPixel(x - 1, y);
      final pr = resized.getPixel(x + 1, y);
      double lum(img.Pixel px) =>
          0.299 * px.r.toDouble() + 0.587 * px.g.toDouble() + 0.114 * px.b.toDouble();
      final lumP = lum(p);
      sumBright += lumP;
      final lap = 4 * lumP - lum(pt) - lum(pb) - lum(pl) - lum(pr);
      sumLap   += lap;
      sumLapSq += lap * lap;
      n++;
    }
  }
  if (n == 0) return [0, 0];
  final mean = sumLap / n;
  return [(sumLapSq / n) - mean * mean, sumBright / n];
}

class RegisterGuestIdScreen extends StatefulWidget {
  final String email;
  final String fullName;
  final String phone;
  final String cinNumber;
  const RegisterGuestIdScreen({super.key, this.email = '', this.fullName = '', this.phone = '', this.cinNumber = ''});

  @override
  State<RegisterGuestIdScreen> createState() => _RegisterGuestIdScreenState();
}

class _RegisterGuestIdScreenState extends State<RegisterGuestIdScreen>
    with WidgetsBindingObserver {
  int _step = 0; // 0 = recto, 1 = verso
  bool _isCapturing = false;
  bool _isUploading = false;
  bool _cameraReady = false;
  bool _flashOn = false;
  CameraController? _controller;
  File? _rectoImage;
  File? _versoImage;

  // Vérification OCR du numéro CIN
  bool _cinVerifying = false;
  bool? _cinMatch;        // null = pas encore vérifié, true = ok, false = mismatch
  String _cinExtracted = '';  // numéro lu par OCR

  bool get _rectoCaptured => _rectoImage != null;
  bool get _versoCaptured => _versoImage != null;
  bool get _bothCaptured => _rectoCaptured && _versoCaptured;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initCamera();
  }

  Future<void> _initCamera() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) return;
      final rear = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      _controller = CameraController(
        rear,
        ResolutionPreset.high,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await _controller!.initialize();
      await _controller!.setFlashMode(FlashMode.off);
      await _controller!.setFocusMode(FocusMode.auto);
      await _controller!.setExposureMode(ExposureMode.auto);
      if (mounted) setState(() => _cameraReady = true);
    } catch (_) {}
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_controller == null || !_controller!.value.isInitialized) return;
    if (state == AppLifecycleState.inactive) {
      _controller!.dispose();
    } else if (state == AppLifecycleState.resumed) {
      _initCamera();
    }
  }

  Future<void> _toggleFlash() async {
    if (_controller == null || !_cameraReady) return;
    setState(() => _flashOn = !_flashOn);
    await _controller!.setFlashMode(_flashOn ? FlashMode.torch : FlashMode.off);
  }

  Future<void> _onTapFocus(TapDownDetails details, BoxConstraints constraints) async {
    if (_controller == null || !_cameraReady) return;
    final point = Offset(
      details.localPosition.dx / constraints.maxWidth,
      details.localPosition.dy / constraints.maxHeight,
    );
    try {
      await _controller!.setFocusPoint(point);
      await _controller!.setExposurePoint(point);
    } catch (_) {}
  }

  Future<void> _capture() async {
    if (!_cameraReady || _controller == null || _isCapturing) return;
    setState(() => _isCapturing = true);
    try {
      try { await _controller!.setFocusMode(FocusMode.locked); } catch (_) {}
      final XFile image = await _controller!.takePicture();
      try { await _controller!.setFocusMode(FocusMode.auto); } catch (_) {}
      if (!mounted) return;

      final bytes = await File(image.path).readAsBytes();
      final metrics = await compute(_analyzeImageCin, bytes);
      final variance   = metrics[0];
      final brightness = metrics[1];

      String? qualityError;
      if (brightness < 30) {
        qualityError = 'Image trop sombre. Éclairez mieux votre CIN et réessayez.';
      } else if (brightness > 225) {
        qualityError = 'Image surexposée. Évitez les reflets et les lumières directes.';
      } else if (variance < 80) {
        qualityError = 'Image trop floue. Maintenez le téléphone stable et réessayez.';
      }

      if (qualityError != null) {
        if (mounted) {
          _showError(qualityError);
          setState(() => _isCapturing = false);
        }
        return;
      }

      if (_step == 0) {
        final rectoFile = File(image.path);
        setState(() {
          _rectoImage = rectoFile;
          _isCapturing = false;
        });
        if (widget.cinNumber.isNotEmpty) {
          await _verifyCinNumber(rectoFile);
          if (!mounted) return;
          if (_cinMatch == false) return;
        }
        if (mounted) setState(() => _step = 1);
      } else {
        setState(() {
          _versoImage = File(image.path);
          _isCapturing = false;
        });
      }
    } catch (e) {
      if (mounted) {
        _showError('Erreur lors de la capture. Réessayez.');
        setState(() => _isCapturing = false);
      }
    }
  }

  void _retake(int side) {
    setState(() {
      if (side == 0) {
        _rectoImage = null;
        _step = 0;
        _cinMatch = null;
        _cinExtracted = '';
      } else {
        _versoImage = null;
        _step = 1;
      }
    });
  }

  Future<void> _verifyCinNumber(File rectoFile) async {
    setState(() => _cinVerifying = true);
    try {
      final result = await ApiClient.instance.postMultipartAI(
        '/api/ai/cin-verify-number',
        {'cin_recto': rectoFile},
        fields: {'declared_cin': widget.cinNumber},
        timeout: const Duration(seconds: 45),
      );

      if (!mounted) return;

      final ocrAvailable = result['ocr_available'] as bool? ?? false;
      if (!ocrAvailable) {
        if (mounted) {
          setState(() { _cinVerifying = false; _cinMatch = false; });
          _showCinMismatchDialog('');
        }
        return;
      }

      final match = result['match'] as bool?;
      final extracted = result['extracted_cin'] as String? ?? '';
      setState(() {
        _cinVerifying = false;
        _cinMatch = match;
        _cinExtracted = extracted;
      });

      if (match == false && mounted) {
        _showCinMismatchDialog(extracted);
      }
    } catch (_) {
      if (mounted) {
        setState(() { _cinVerifying = false; _cinMatch = false; });
        _showError('Service de vérification indisponible. Vérifiez votre réseau.');
      }
    }
  }

  void _showCinMismatchDialog(String extracted) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(children: [
          Icon(Icons.warning_amber_rounded, color: Color(0xFFD97706)),
          SizedBox(width: 8),
          Text('Numéro CIN différent', style: TextStyle(fontSize: 16)),
        ]),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Le numéro saisi : ${widget.cinNumber}',
                style: const TextStyle(fontSize: 13)),
            const SizedBox(height: 4),
            Text(
              extracted.isNotEmpty
                  ? 'Numéro lu sur la carte : $extracted'
                  : 'Numéro lu sur la carte : non lisible',
              style: const TextStyle(fontSize: 13),
            ),
            const SizedBox(height: 12),
            const Text(
              'Vérifiez le numéro saisi ou reprenez la photo recto.',
              style: TextStyle(fontSize: 12, color: Color(0xFF6B7280)),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _retake(0);
            },
            child: const Text('Reprendre le recto'),
          ),
        ],
      ),
    );
  }

  Future<void> _uploadAndContinue() async {
    if (_rectoImage == null || _versoImage == null) return;
    if (_flashOn) _controller?.setFlashMode(FlashMode.off);
    setState(() => _isUploading = true);
    try {
      final sessionId = await AuthService.instance.kycUploadCin(_rectoImage!, _versoImage!);
      if (!mounted) return;
      context.go('/register/guest/selfie', extra: {'sessionId': sessionId, 'fullName': widget.fullName, 'phone': widget.phone, 'email': widget.email, 'cinNumber': widget.cinNumber});
    } on ApiException catch (e) {
      if (!mounted) return;
      _showError(e.message);
    } catch (_) {
      if (!mounted) return;
      _showError('Erreur lors de l\'envoi. Vérifiez votre réseau.');
    } finally {
      if (mounted) setState(() => _isUploading = false);
    }
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(SnackBar(
        content: Text(msg),
        backgroundColor: const Color(0xFFDC2626),
        behavior: SnackBarBehavior.floating,
      ));
  }

  void _goBack() {
    if (_flashOn) _controller?.setFlashMode(FlashMode.off);
    context.go('/register/sans-rib');
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.setFlashMode(FlashMode.off);
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _goBack();
      },
      child: Scaffold(
        backgroundColor: AppColors.surfaceContainerLow,
        appBar: AppBar(
          title: const Text('Carte d\'identité'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded),
            onPressed: _goBack,
          ),
          actions: [
            if (_cameraReady && !_bothCaptured)
              IconButton(
                icon: Icon(
                  _flashOn ? Icons.flash_on_rounded : Icons.flash_off_rounded,
                  color: _flashOn ? Colors.amber : null,
                ),
                onPressed: _toggleFlash,
              ),
          ],
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 12),
                const Text(
                  'Capture de la\ncarte d\'identité',
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w800,
                    color: AppColors.onSurface,
                    height: 1.2,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  'Photographiez le recto puis le verso de votre carte.',
                  style: TextStyle(fontSize: 14, color: AppColors.onSurfaceVariant, height: 1.5),
                ),
                const SizedBox(height: 12),
                // Step indicators
                Row(
                  children: [
                    _StepChip(label: 'Recto', done: _rectoCaptured, active: _step == 0 && !_rectoCaptured),
                    const SizedBox(width: 10),
                    const Icon(Icons.arrow_forward_rounded, size: 16, color: AppColors.onSurfaceVariant),
                    const SizedBox(width: 10),
                    _StepChip(label: 'Verso', done: _versoCaptured, active: _step == 1 && !_versoCaptured),
                  ],
                ),
                const SizedBox(height: 8),
                // Indicateur vérification CIN
                if (widget.cinNumber.isNotEmpty && (_cinVerifying || _cinMatch != null))
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 300),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                    decoration: BoxDecoration(
                      color: _cinVerifying
                          ? const Color(0xFFF3F4F6)
                          : _cinMatch == true
                              ? const Color(0xFFD1FAE5)
                              : const Color(0xFFFEF3C7),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (_cinVerifying)
                          const SizedBox(
                            width: 14, height: 14,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        else
                          Icon(
                            _cinMatch == true
                                ? Icons.check_circle_rounded
                                : Icons.warning_amber_rounded,
                            size: 16,
                            color: _cinMatch == true
                                ? const Color(0xFF059669)
                                : const Color(0xFFD97706),
                          ),
                        const SizedBox(width: 6),
                        Text(
                          _cinVerifying
                              ? 'Vérification du numéro CIN...'
                              : _cinMatch == true
                                  ? 'Numéro CIN confirmé'
                                  : 'Numéro CIN différent — vérifiez',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: _cinVerifying
                                ? const Color(0xFF6B7280)
                                : _cinMatch == true
                                    ? const Color(0xFF065F46)
                                    : const Color(0xFF92400E),
                          ),
                        ),
                      ],
                    ),
                  ),
                const SizedBox(height: 8),
                // Recto/verso instruction card
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: _step == 0
                        ? const Color(0xFFEFF6FF)
                        : const Color(0xFFF0FDF4),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: _step == 0
                          ? const Color(0xFF3B82F6)
                          : const Color(0xFF22C55E),
                      width: 1,
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        _step == 0 ? Icons.person_rounded : Icons.article_rounded,
                        size: 18,
                        color: _step == 0 ? const Color(0xFF3B82F6) : const Color(0xFF22C55E),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _step == 0
                              ? 'RECTO — Face avec votre PHOTO (côté gauche) et votre NOM'
                              : 'VERSO — Face avec l\'EMPREINTE DIGITALE et le code-barres',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: _step == 0 ? const Color(0xFF1E40AF) : const Color(0xFF166534),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 10),

                // Viewfinder
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      final currentImage = _step == 0 ? _rectoImage : _versoImage;
                      final isCaptured = currentImage != null;

                      return GestureDetector(
                        onTapDown: (!isCaptured && _cameraReady)
                            ? (d) => _onTapFocus(d, constraints)
                            : null,
                        child: Container(
                          width: double.infinity,
                          decoration: BoxDecoration(
                            color: const Color(0xFF0F172A),
                            borderRadius: BorderRadius.circular(24),
                            border: Border.all(
                              color: isCaptured ? const Color(0xFF059669) : AppColors.primary,
                              width: 2,
                            ),
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(22),
                            child: Stack(
                              fit: StackFit.expand,
                              children: [
                                // Live preview or captured image
                                if (isCaptured)
                                  Image.file(currentImage, fit: BoxFit.cover)
                                else if (_cameraReady)
                                  CameraPreview(_controller!)
                                else
                                  _buildPlaceholder(),

                                // Corner brackets
                                if (!isCaptured) ...[
                                  Positioned(top: 20, left: 20, child: _CornerBracket(color: AppColors.primary, position: _CP.topLeft)),
                                  Positioned(top: 20, right: 20, child: _CornerBracket(color: AppColors.primary, position: _CP.topRight)),
                                  Positioned(bottom: 20, left: 20, child: _CornerBracket(color: AppColors.primary, position: _CP.bottomLeft)),
                                  Positioned(bottom: 20, right: 20, child: _CornerBracket(color: AppColors.primary, position: _CP.bottomRight)),
                                ],

                                // ID card guide frame
                                if (!isCaptured && _cameraReady)
                                  Center(
                                    child: Container(
                                      width: constraints.maxWidth * 0.75,
                                      height: constraints.maxWidth * 0.75 * 0.63,
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(10),
                                        border: Border.all(
                                          color: Colors.white.withOpacity(0.5),
                                          width: 1.5,
                                        ),
                                      ),
                                    ),
                                  ),

                                // Hint label
                                if (!isCaptured && _cameraReady && !_isCapturing)
                                  Positioned(
                                    bottom: 14,
                                    left: 0,
                                    right: 0,
                                    child: Center(
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
                                        decoration: BoxDecoration(
                                          color: Colors.black.withOpacity(0.55),
                                          borderRadius: BorderRadius.circular(20),
                                        ),
                                        child: Text(
                                          _step == 0 ? 'Face avant (recto)' : 'Face arrière (verso)',
                                          style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w500),
                                        ),
                                      ),
                                    ),
                                  ),

                                // Retake button on captured image
                                if (isCaptured)
                                  Positioned(
                                    top: 12,
                                    right: 12,
                                    child: GestureDetector(
                                      onTap: () => _retake(_step == 0 ? 0 : 1),
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                        decoration: BoxDecoration(
                                          color: Colors.black.withOpacity(0.6),
                                          borderRadius: BorderRadius.circular(20),
                                        ),
                                        child: const Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            Icon(Icons.refresh_rounded, color: Colors.white, size: 14),
                                            SizedBox(width: 4),
                                            Text('Reprendre', style: TextStyle(color: Colors.white, fontSize: 12)),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),

                                if (_isCapturing)
                                  Container(
                                    color: Colors.white.withOpacity(0.3),
                                    child: const Center(
                                      child: CircularProgressIndicator(color: Colors.white, strokeWidth: 3),
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),

                const SizedBox(height: 12),

                // Thumbnails row when both captured
                if (_bothCaptured)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Row(
                      children: [
                        Expanded(child: _Thumbnail(label: 'Recto', file: _rectoImage!, onRetake: () => _retake(0))),
                        const SizedBox(width: 12),
                        Expanded(child: _Thumbnail(label: 'Verso', file: _versoImage!, onRetake: () => _retake(1))),
                      ],
                    ),
                  ),

                PrimaryButton(
                  label: _bothCaptured
                      ? 'Continuer'
                      : _cinVerifying
                          ? 'Vérification CIN...'
                          : 'Capturer le ${_step == 0 ? "recto" : "verso"}',
                  onPressed: _bothCaptured
                      ? _isUploading ? () {} : _uploadAndContinue
                      : (_isCapturing || _cinVerifying || !_cameraReady) ? () {} : _capture,
                  isLoading: _isCapturing || _isUploading,
                  icon: Icon(
                    _bothCaptured ? Icons.arrow_forward_rounded : Icons.camera_alt_rounded,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
                const SizedBox(height: 20),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPlaceholder() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.credit_card_rounded, color: Colors.white.withOpacity(0.3), size: 64),
          const SizedBox(height: 12),
          Text(
            'Initialisation de la caméra...',
            style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 13),
          ),
        ],
      ),
    );
  }
}

class _StepChip extends StatelessWidget {
  final String label;
  final bool done;
  final bool active;
  const _StepChip({required this.label, required this.done, required this.active});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      decoration: BoxDecoration(
        color: done
            ? const Color(0xFFD1FAE5)
            : active
                ? AppColors.secondaryContainer
                : AppColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(100),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            done ? Icons.check_circle_rounded : Icons.radio_button_unchecked_rounded,
            size: 14,
            color: done ? const Color(0xFF059669) : active ? AppColors.primary : AppColors.onSurfaceVariant,
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: done ? const Color(0xFF059669) : active ? AppColors.primary : AppColors.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _Thumbnail extends StatelessWidget {
  final String label;
  final File file;
  final VoidCallback onRetake;
  const _Thumbnail({required this.label, required this.file, required this.onRetake});

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Image.file(file, height: 80, width: double.infinity, fit: BoxFit.cover),
        ),
        Positioned(
          top: 4, left: 6,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(6)),
            child: Text(label, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600)),
          ),
        ),
        Positioned(
          top: 4, right: 4,
          child: GestureDetector(
            onTap: onRetake,
            child: Container(
              padding: const EdgeInsets.all(4),
              decoration: const BoxDecoration(color: Colors.black54, shape: BoxShape.circle),
              child: const Icon(Icons.refresh_rounded, color: Colors.white, size: 14),
            ),
          ),
        ),
      ],
    );
  }
}

enum _CP { topLeft, topRight, bottomLeft, bottomRight }

class _CornerBracket extends StatelessWidget {
  final Color color;
  final _CP position;
  const _CornerBracket({required this.color, required this.position});

  @override
  Widget build(BuildContext context) {
    final isTop = position == _CP.topLeft || position == _CP.topRight;
    final isLeft = position == _CP.topLeft || position == _CP.bottomLeft;
    return SizedBox(
      width: 30,
      height: 30,
      child: CustomPaint(painter: _BracketPainter(color: color, isTop: isTop, isLeft: isLeft)),
    );
  }
}

class _BracketPainter extends CustomPainter {
  final Color color;
  final bool isTop;
  final bool isLeft;
  _BracketPainter({required this.color, required this.isTop, required this.isLeft});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 3.5
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    final path = Path();
    if (isTop && isLeft) {
      path.moveTo(0, size.height); path.lineTo(0, 0); path.lineTo(size.width, 0);
    } else if (isTop && !isLeft) {
      path.moveTo(0, 0); path.lineTo(size.width, 0); path.lineTo(size.width, size.height);
    } else if (!isTop && isLeft) {
      path.moveTo(0, 0); path.lineTo(0, size.height); path.lineTo(size.width, size.height);
    } else {
      path.moveTo(size.width, 0); path.lineTo(size.width, size.height); path.lineTo(0, size.height);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
