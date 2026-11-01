import 'dart:io';
import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image/image.dart' as img;
import 'package:image_picker/image_picker.dart';
import '../theme.dart';
import '../widgets/app_bottom_nav.dart';
import '../widgets/primary_button.dart';
import '../services/cheque_service.dart';
import '../services/api_client.dart';
import '../models/cheque.dart';

// Top-level function so it can run in a compute isolate.
// Applies EXIF rotation and resizes to max 1920px width.
Uint8List _processImageBytes(Uint8List bytes) {
  final decoded = img.decodeImage(bytes);
  if (decoded == null) return bytes;
  final resized = decoded.width > 1920
      ? img.copyResize(decoded, width: 1920, interpolation: img.Interpolation.linear)
      : decoded;
  return Uint8List.fromList(img.encodeJpg(resized, quality: 85));
}

class DepotChequeScreen extends StatefulWidget {
  const DepotChequeScreen({super.key});

  @override
  State<DepotChequeScreen> createState() => _DepotChequeScreenState();
}

class _DepotChequeScreenState extends State<DepotChequeScreen> with WidgetsBindingObserver {
  int _currentStep = 1;   // démarre directement au recto (étape 0 = préparer, toujours cochée)
  bool _isCapturing = false;
  bool _cameraReady = false;
  bool _flashOn = false;
  CameraController? _controller;
  final List<File> _capturedImages = [];

  final List<Map<String, dynamic>> _steps = [
    {
      'title': 'Préparez votre chèque',
      'subtitle': 'Posez-le sur une surface plane et bien éclairée',
      'icon': Icons.task_alt_rounded,
    },
    {
      'title': 'Capturez le recto',
      'subtitle': 'Face avec le montant et la signature',
      'icon': Icons.flip_to_front_rounded,
    },
    {
      'title': 'Capturez le verso',
      'subtitle': 'Face avec votre endossement',
      'icon': Icons.flip_to_back_rounded,
    },
  ];

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

  // Applies EXIF rotation and compresses in a background isolate.
  Future<File> _processImage(String path) async {
    try {
      final bytes = await File(path).readAsBytes();
      final processed = await compute(_processImageBytes, bytes);
      final outFile = File(path);
      await outFile.writeAsBytes(processed);
      return outFile;
    } catch (_) {
      return File(path);
    }
  }

  Future<void> _capture() async {
    if (_controller == null || !_cameraReady || _isCapturing) return;
    setState(() => _isCapturing = true);
    try {
      await _controller!.setFocusMode(FocusMode.locked);
      final XFile xfile = await _controller!.takePicture();
      await _controller!.setFocusMode(FocusMode.auto);
      if (!mounted) return;
      final processedFile = await _processImage(xfile.path);
      _capturedImages.add(processedFile);
      if (_currentStep < 2) {
        setState(() { _isCapturing = false; _currentStep++; });
      } else {
        if (_flashOn) await _controller!.setFlashMode(FlashMode.off);
        await _uploadCheque();
      }
    } catch (_) {
      if (mounted) setState(() => _isCapturing = false);
    }
  }

  Future<void> _pickFromGallery() async {
    if (_isCapturing) return;
    try {
      final picked = await ImagePicker().pickImage(
        source: ImageSource.gallery,
        imageQuality: 100,
      );
      if (picked == null || !mounted) return;
      setState(() => _isCapturing = true);
      final processedFile = await _processImage(picked.path);
      _capturedImages.add(processedFile);
      if (_currentStep < 2) {
        setState(() { _isCapturing = false; _currentStep++; });
      } else {
        await _uploadCheque();
      }
    } catch (_) {
      if (mounted) setState(() => _isCapturing = false);
    }
  }

  Future<void> _uploadCheque() async {
    if (_capturedImages.isEmpty) return;
    setState(() => _isCapturing = true);
    try {
      final recto = _capturedImages[0];
      final verso = _capturedImages.length > 1 ? _capturedImages[1] : null;
      final cheque = await ChequeService.instance.uploadCheque(recto, verso: verso);
      if (mounted) {
        context.go('/depot/confirmation', extra: {
          'numeroCheque': cheque.numeroCheque ?? '—',
          'montant':      cheque.montantFormate,
          'statut':       cheque.status.label,
          'chequeId':     cheque.id,
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
        // Naviguer quand même en mode dégradé
        context.go('/depot/confirmation');
      }
    } finally {
      if (mounted) setState(() => _isCapturing = false);
    }
  }

  void _goBack() {
    if (_flashOn) _controller?.setFlashMode(FlashMode.off);
    context.go('/home/beneficiaire');
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
          title: const Text('Dépôt de chèque'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded),
            onPressed: _goBack,
          ),
          actions: [
            if (_cameraReady)
              IconButton(
                icon: Icon(
                  _flashOn ? Icons.flash_on_rounded : Icons.flash_off_rounded,
                  color: _flashOn ? Colors.amber : null,
                ),
                onPressed: _toggleFlash,
                tooltip: _flashOn ? 'Flash activé' : 'Flash désactivé',
              ),
          ],
        ),
        body: SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Steps list
                Container(
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: ListView.separated(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: _steps.length,
                    separatorBuilder: (_, __) => const Divider(height: 1, indent: 56),
                    itemBuilder: (context, index) {
                      final step = _steps[index];
                      final isCompleted = index < _currentStep;
                      final isCurrent = index == _currentStep;
                      return ListTile(
                        leading: Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: isCompleted
                                ? const Color(0xFFD1FAE5)
                                : isCurrent
                                    ? AppColors.secondaryContainer
                                    : AppColors.surfaceContainerLow,
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            isCompleted ? Icons.check_rounded : (step['icon'] as IconData),
                            color: isCompleted
                                ? const Color(0xFF059669)
                                : isCurrent
                                    ? AppColors.primary
                                    : AppColors.onSurfaceVariant,
                            size: 18,
                          ),
                        ),
                        title: Text(
                          step['title'],
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: isCurrent ? FontWeight.w700 : FontWeight.w500,
                            color: isCurrent ? AppColors.onSurface : AppColors.onSurfaceVariant,
                          ),
                        ),
                        subtitle: Text(
                          step['subtitle'],
                          style: TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant),
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: 16),

                // Camera viewfinder
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, constraints) => GestureDetector(
                      onTapDown: (d) => _onTapFocus(d, constraints),
                      child: Container(
                        width: double.infinity,
                        decoration: BoxDecoration(
                          color: const Color(0xFF0F172A),
                          borderRadius: BorderRadius.circular(24),
                          border: Border.all(
                            color: AppColors.primary,
                            width: 2,
                          ),
                        ),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(22),
                          child: Stack(
                            fit: StackFit.expand,
                            children: [
                              // Live camera preview
                              if (_cameraReady)
                                CameraPreview(_controller!)
                              else
                                _buildPlaceholder(),

                              // Corner bracket overlay
                              ...[
                                Positioned(top: 20, left: 20, child: _CornerBracket(color: AppColors.primary, position: _Pos.topLeft)),
                                Positioned(top: 20, right: 20, child: _CornerBracket(color: AppColors.primary, position: _Pos.topRight)),
                                Positioned(bottom: 20, left: 20, child: _CornerBracket(color: AppColors.primary, position: _Pos.bottomLeft)),
                                Positioned(bottom: 20, right: 20, child: _CornerBracket(color: AppColors.primary, position: _Pos.bottomRight)),
                              ],

                              // Scanning guide line
                              if (_cameraReady && !_isCapturing)
                                _ScanLine(),

                              // Status overlay
                              if (!_isCapturing)
                                Positioned(
                                  bottom: 16,
                                  left: 0,
                                  right: 0,
                                  child: Center(
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                                      decoration: BoxDecoration(
                                        color: Colors.black.withOpacity(0.55),
                                        borderRadius: BorderRadius.circular(20),
                                      ),
                                      child: Text(
                                        _cameraReady
                                            ? 'Appuyez pour mettre au point'
                                            : 'Initialisation de la caméra...',
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 12,
                                          fontWeight: FontWeight.w500,
                                        ),
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
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: PrimaryButton(
                        label: _currentStep == 1 ? 'Capturer le recto' : 'Capturer le verso',
                        onPressed: _capture,
                        isLoading: _isCapturing,
                        icon: const Icon(Icons.camera_alt_rounded, color: Colors.white, size: 20),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Tooltip(
                      message: 'Importer depuis la galerie',
                      child: SizedBox(
                        width: 52,
                        height: 52,
                        child: OutlinedButton(
                          onPressed: _isCapturing ? null : _pickFromGallery,
                          style: OutlinedButton.styleFrom(
                            side: const BorderSide(color: AppColors.primary, width: 1.5),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                            padding: EdgeInsets.zero,
                          ),
                          child: const Icon(Icons.attach_file_rounded, color: AppColors.primary, size: 24),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        bottomNavigationBar: AppBottomNav(
          currentIndex: 2,
          homeRoute: '/home/beneficiaire',
          showScanner: true,
          onScannerTap: _capture,
        ),
      ),
    );
  }

  Widget _buildPlaceholder() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          Icons.payments_rounded,
          color: Colors.white.withOpacity(0.35),
          size: 72,
        ),
        const SizedBox(height: 16),
        Text(
          'Préparez votre chèque',
          style: TextStyle(color: Colors.white.withOpacity(0.6), fontSize: 15, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        Text(
          'Surface plane · bonne lumière · lisible',
          style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 12),
        ),
      ],
    );
  }
}

// Animated scanning line
class _ScanLine extends StatefulWidget {
  @override
  State<_ScanLine> createState() => _ScanLineState();
}

class _ScanLineState extends State<_ScanLine> with SingleTickerProviderStateMixin {
  late final AnimationController _anim;
  late final Animation<double> _pos;

  @override
  void initState() {
    super.initState();
    _anim = AnimationController(vsync: this, duration: const Duration(seconds: 2))
      ..repeat(reverse: true);
    _pos = Tween<double>(begin: 0.15, end: 0.85).animate(
      CurvedAnimation(parent: _anim, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _anim.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _pos,
      builder: (context, _) => Positioned.fill(
        child: Align(
          alignment: Alignment(_pos.value * 2 - 1, 0),
          child: Container(
            width: 2,
            height: double.infinity,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  AppColors.primary.withOpacity(0),
                  AppColors.primary.withOpacity(0.8),
                  AppColors.primary.withOpacity(0),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

enum _Pos { topLeft, topRight, bottomLeft, bottomRight }

class _CornerBracket extends StatelessWidget {
  final Color color;
  final _Pos position;
  const _CornerBracket({required this.color, required this.position});

  @override
  Widget build(BuildContext context) {
    final isTop = position == _Pos.topLeft || position == _Pos.topRight;
    final isLeft = position == _Pos.topLeft || position == _Pos.bottomLeft;
    return SizedBox(
      width: 32,
      height: 32,
      child: CustomPaint(
        painter: _BracketPainter(color: color, isTop: isTop, isLeft: isLeft),
      ),
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
      path.moveTo(0, size.height);
      path.lineTo(0, 0);
      path.lineTo(size.width, 0);
    } else if (isTop && !isLeft) {
      path.moveTo(0, 0);
      path.lineTo(size.width, 0);
      path.lineTo(size.width, size.height);
    } else if (!isTop && isLeft) {
      path.moveTo(0, 0);
      path.lineTo(0, size.height);
      path.lineTo(size.width, size.height);
    } else {
      path.moveTo(size.width, 0);
      path.lineTo(size.width, size.height);
      path.lineTo(0, size.height);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

