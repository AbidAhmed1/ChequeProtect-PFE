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

// Returns [laplacian_variance, mean_brightness, overexposed_ratio 0..1]
List<double> _analyzeImageSelfie(Uint8List bytes) {
  final decoded = img.decodeImage(bytes);
  if (decoded == null) return [999, 128, 0];
  final resized = img.copyResize(decoded, width: 120);
  double sumLap = 0, sumLapSq = 0, sumBright = 0;
  int n = 0, overexposed = 0;
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
      if (lumP > 240) overexposed++;
      final lap = 4 * lumP - lum(pt) - lum(pb) - lum(pl) - lum(pr);
      sumLap   += lap;
      sumLapSq += lap * lap;
      n++;
    }
  }
  if (n == 0) return [0, 0, 0];
  final mean = sumLap / n;
  return [(sumLapSq / n) - mean * mean, sumBright / n, overexposed / n];
}

class RegisterGuestSelfieScreen extends StatefulWidget {
  final String sessionId;
  final String email;
  final String fullName;
  final String phone;
  final String cinNumber;

  const RegisterGuestSelfieScreen({
    super.key,
    required this.sessionId,
    this.email = '',
    this.fullName = '',
    this.phone = '',
    this.cinNumber = '',
  });

  @override
  State<RegisterGuestSelfieScreen> createState() =>
      _RegisterGuestSelfieScreenState();
}

class _RegisterGuestSelfieScreenState extends State<RegisterGuestSelfieScreen>
    with WidgetsBindingObserver {
  File? _selfieImage;
  bool _isCapturing = false;
  bool _isVerifying = false;
  bool _cameraReady = false;
  CameraController? _controller;

  bool get _captured => _selfieImage != null;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initCamera();
  }

  Future<void> _initCamera() async {
    if (mounted) setState(() => _cameraReady = false);
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) return;
      final front = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.front,
        orElse: () => cameras.first,
      );
      _controller = CameraController(
        front,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await _controller!.initialize();
      try { await _controller!.setExposureMode(ExposureMode.auto); } catch (_) {}
      if (mounted) {
        setState(() => _cameraReady = true);
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) setState(() {});
        });
      }
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

  Future<void> _capture() async {
    if (!_cameraReady || _controller == null || _isCapturing) return;
    setState(() => _isCapturing = true);
    try {
      final XFile image = await _controller!.takePicture();
      if (!mounted) return;

      final bytes = await File(image.path).readAsBytes();
      final metrics = await compute(_analyzeImageSelfie, bytes);
      final variance   = metrics[0];
      final brightness = metrics[1];

      final overexposedRatio = metrics[2];
      String? qualityError;
      if (brightness < 35) {
        qualityError = 'Trop sombre. Allumez une lumière devant vous et réessayez.';
      } else if (overexposedRatio > 0.15) {
        qualityError = 'Contre-jour détecté (lumière derrière vous). '
            'Tournez-vous face à une lampe ou une fenêtre.';
      } else if (variance < 25) {
        qualityError = 'Selfie flou. Restez immobile et assurez-vous d\'être bien éclairé.';
      }

      if (qualityError != null) {
        if (mounted) {
          _showError(qualityError);
          setState(() => _isCapturing = false);
        }
        return;
      }

      setState(() {
        _selfieImage = File(image.path);
        _isCapturing = false;
      });
    } catch (e) {
      if (mounted) {
        _showError('Erreur lors de la capture. Réessayez.');
        setState(() => _isCapturing = false);
      }
    }
  }

  void _retake() {
    setState(() => _selfieImage = null);
  }

  Future<void> _verifyAndContinue() async {
    if (_selfieImage == null) return;
    setState(() => _isVerifying = true);
    try {
      await AuthService.instance.kycFaceVerify(_selfieImage!, widget.sessionId);
      if (!mounted) return;
      context.go('/register/guest/complete', extra: {'sessionId': widget.sessionId, 'fullName': widget.fullName, 'phone': widget.phone, 'email': widget.email, 'cinNumber': widget.cinNumber});
    } on ApiException catch (e) {
      if (!mounted) return;
      _showError(e.message);
      setState(() => _selfieImage = null);
    } catch (_) {
      if (!mounted) return;
      _showError('Erreur de vérification. Vérifiez votre réseau.');
    } finally {
      if (mounted) setState(() => _isVerifying = false);
    }
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: const Color(0xFFDC2626),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.go('/register/guest/id');
      },
      child: Scaffold(
        backgroundColor: AppColors.surfaceContainerLow,
        appBar: AppBar(
          title: const Text('Selfie de vérification'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded),
            onPressed: () => context.go('/register/guest/id'),
          ),
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 12),
                const Text(
                  'Prenez un selfie',
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w800,
                    color: AppColors.onSurface,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  'Regardez la caméra frontale, visage bien éclairé de face. Évitez les fenêtres ou lumières derrière vous.',
                  style: TextStyle(fontSize: 13, color: AppColors.onSurfaceVariant, height: 1.5),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    _TipChip(icon: Icons.wb_sunny_rounded, label: 'Lumière de face'),
                    const SizedBox(width: 8),
                    _TipChip(icon: Icons.visibility_rounded, label: 'Regardez la caméra'),
                    const SizedBox(width: 8),
                    _TipChip(icon: Icons.stay_current_portrait_rounded, label: 'Téléphone droit'),
                  ],
                ),
                const SizedBox(height: 14),

                // Viewfinder
                Expanded(
                  child: Container(
                    width: double.infinity,
                    decoration: BoxDecoration(
                      color: const Color(0xFF0F172A),
                      borderRadius: BorderRadius.circular(24),
                      border: Border.all(
                        color: _captured ? const Color(0xFF059669) : AppColors.primary,
                        width: 2,
                      ),
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(22),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          // Live preview or captured photo
                          if (_captured)
                            Image.file(_selfieImage!, fit: BoxFit.cover)
                          else if (_cameraReady)
                            CameraPreview(_controller!)
                          else
                            _buildPlaceholder(),

                          // Oval face guide overlay (only when live preview active)
                          if (!_captured && _cameraReady)
                            LayoutBuilder(
                              builder: (context, constraints) => CustomPaint(
                                size: Size(constraints.maxWidth, constraints.maxHeight),
                                painter: _OvalGuidePainter(),
                              ),
                            ),

                          // Hint text
                          if (!_captured && _cameraReady && !_isCapturing)
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
                                  child: const Text(
                                    'Centrez votre visage dans le cadre',
                                    style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w500),
                                  ),
                                ),
                              ),
                            ),

                          // Retake button on captured photo
                          if (_captured)
                            Positioned(
                              top: 12,
                              right: 12,
                              child: GestureDetector(
                                onTap: _retake,
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
                ),

                const SizedBox(height: 20),
                PrimaryButton(
                  label: _captured ? 'Vérifier mon identité' : 'Prendre le selfie',
                  onPressed: _captured
                      ? _isVerifying ? () {} : _verifyAndContinue
                      : (_isCapturing || !_cameraReady)
                          ? () {}
                          : _capture,
                  isLoading: _isCapturing || _isVerifying,
                  icon: Icon(
                    _captured ? Icons.verified_user_rounded : Icons.camera_front_rounded,
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
          Icon(Icons.face_rounded, color: Colors.white.withOpacity(0.3), size: 80),
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

class _TipChip extends StatelessWidget {
  final IconData icon;
  final String label;
  const _TipChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.secondaryContainer,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: AppColors.primary),
          const SizedBox(width: 4),
          Text(label, style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: AppColors.primary)),
        ],
      ),
    );
  }
}

class _OvalGuidePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final ovalW = size.width * 0.72;
    final ovalH = size.height * 0.60;
    final center = Offset(size.width / 2, size.height * 0.45);
    final ovalRect = Rect.fromCenter(center: center, width: ovalW, height: ovalH);

    // Light dark overlay outside the oval
    final bgPaint = Paint()..color = Colors.black.withOpacity(0.22);
    final path = Path()
      ..addRect(Rect.fromLTWH(0, 0, size.width, size.height))
      ..addOval(ovalRect)
      ..fillType = PathFillType.evenOdd;
    canvas.drawPath(path, bgPaint);

    // White dashed border
    final borderPaint = Paint()
      ..color = Colors.white.withOpacity(0.90)
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke;
    canvas.drawOval(ovalRect, borderPaint);

    // Four corner arcs for a modern KYC look
    final arcPaint = Paint()
      ..color = AppColors.primary
      ..strokeWidth = 4.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;
    const sweep = 0.45; // radians
    canvas.drawArc(ovalRect, -1.57,  sweep, false, arcPaint); // top
    canvas.drawArc(ovalRect, -1.57, -sweep, false, arcPaint);
    canvas.drawArc(ovalRect,  1.57,  sweep, false, arcPaint); // bottom
    canvas.drawArc(ovalRect,  1.57, -sweep, false, arcPaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
