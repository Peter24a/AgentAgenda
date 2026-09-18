import 'dart:math' as math;
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Botón inferior de asistencia SARA con animación de bucle interactivo (Isotipo SARA).
/// Cumple con la Identidad Visual SARA v0.4.0:
/// - Relleno sólido ciruela (#6B4F73 en claro / #C5AED0 en oscuro)
/// - Contraste accesible AAA (texto blanco en claro / carbón #231B28 en oscuro)
/// - Isotipo vectorial SARA animado integrado
/// - Al pulsar, dispara un estallido en lazo continuo que recorre la geometría del logotipo SARA
///   antes de navegar al asistente.
class PremiumAgentButton extends StatefulWidget {
  final VoidCallback onTap;

  const PremiumAgentButton({super.key, required this.onTap});

  @override
  State<PremiumAgentButton> createState() => _PremiumAgentButtonState();
}

class _PremiumAgentButtonState extends State<PremiumAgentButton>
    with TickerProviderStateMixin {
  late final AnimationController _burstController;
  late final AnimationController _scaleController;
  late final Animation<double> _scaleAnimation;
  bool _isNavigating = false;

  @override
  void initState() {
    super.initState();
    _burstController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 320),
    );

    _scaleController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 160),
    );

    _scaleAnimation = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween<double>(begin: 1.0, end: 0.95)
            .chain(CurveTween(curve: Curves.easeOutCubic)),
        weight: 40,
      ),
      TweenSequenceItem(
        tween: Tween<double>(begin: 0.95, end: 1.0)
            .chain(CurveTween(curve: Curves.elasticOut)),
        weight: 60,
      ),
    ]).animate(_scaleController);
  }

  @override
  void dispose() {
    _burstController.dispose();
    _scaleController.dispose();
    super.dispose();
  }

  void _handleTap() {
    if (_isNavigating) return;
    _isNavigating = true;

    // Respuesta táctil y activación del bucle SARA
    HapticFeedback.mediumImpact();
    _scaleController.forward(from: 0.0);
    _burstController.forward(from: 0.0);

    // Breve pausa para apreciar la cinemática del lazo SARA
    Future.delayed(const Duration(milliseconds: 250), () {
      if (mounted) {
        widget.onTap();
        // Restablecer guardia tras la apertura de la ruta
        Future.delayed(const Duration(milliseconds: 350), () {
          if (mounted) {
            setState(() {
              _isNavigating = false;
            });
            _burstController.reset();
          }
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      child: Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: [
          // Botón físico interactivo
          ScaleTransition(
            scale: _scaleAnimation,
            child: Material(
              color: colorScheme.primary,
              borderRadius: BorderRadius.circular(12),
              elevation: isDark ? 0 : 3,
              shadowColor: Colors.black.withValues(alpha: 0.25),
              clipBehavior: Clip.antiAlias,
              child: InkWell(
                onTap: _handleTap,
                splashColor: (isDark ? Colors.black : Colors.white)
                    .withValues(alpha: 0.15),
                highlightColor: (isDark ? Colors.black : Colors.white)
                    .withValues(alpha: 0.08),
                child: Container(
                  constraints: const BoxConstraints(minHeight: 48),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 12,
                  ),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: isDark ? colorScheme.outline : Colors.transparent,
                      width: 1.0,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // Isotipo animado de SARA (lazo infinito continuo)
                      SaraLoopIcon(
                        size: 20,
                        color: colorScheme.onPrimary,
                      ),
                      const SizedBox(width: 10),
                      Text(
                        'Asistente SARA',
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                          color: colorScheme.onPrimary,
                          letterSpacing: 0.2,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '· Planear día',
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontWeight: FontWeight.w400,
                          color: colorScheme.onPrimary.withValues(alpha: 0.85),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Icon(
                        Icons.arrow_forward_rounded,
                        size: 16,
                        color: colorScheme.onPrimary.withValues(alpha: 0.85),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),

          // Estallido en bucle SARA al presionar el botón
          Positioned.fill(
            child: IgnorePointer(
              child: AnimatedBuilder(
                animation: _burstController,
                builder: (context, _) {
                  if (_burstController.value <= 0.0 ||
                      _burstController.value >= 1.0) {
                    return const SizedBox.shrink();
                  }
                  return CustomPaint(
                    painter: SaraLoopBurstPainter(
                      progress: _burstController.value,
                      isDark: isDark,
                      accentColor: isDark
                          ? const Color(0xFFC5AED0)
                          : const Color(0xFF6B4F73),
                    ),
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Icono vectorial del Isotipo de SARA con animación de resplandor continuo.
/// Representa el lazo entrelazado / cinta de Möbius oficial de la marca FIME.
class SaraLoopIcon extends StatefulWidget {
  final double size;
  final Color? color;
  final bool animate;

  const SaraLoopIcon({
    super.key,
    this.size = 20,
    this.color,
    this.animate = true,
  });

  @override
  State<SaraLoopIcon> createState() => _SaraLoopIconState();
}

class _SaraLoopIconState extends State<SaraLoopIcon>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2800),
    );
    if (widget.animate) {
      _controller.repeat();
    }
  }

  @override
  void didUpdateWidget(covariant SaraLoopIcon oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.animate && !_controller.isAnimating) {
      _controller.repeat();
    } else if (!widget.animate && _controller.isAnimating) {
      _controller.stop();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final effectiveColor =
        widget.color ?? IconTheme.of(context).color ?? const Color(0xFF6B4F73);

    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          return CustomPaint(
            painter: _SaraLoopIconPainter(
              color: effectiveColor,
              progress: widget.animate ? _controller.value : 0.0,
            ),
          );
        },
      ),
    );
  }
}

class _SaraLoopIconPainter extends CustomPainter {
  final Color color;
  final double progress;

  _SaraLoopIconPainter({required this.color, required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final w = size.width * 0.88;
    final h = size.height * 0.52;

    final path = _createLemniscatePath(cx, cy, w, h, -0.22);

    // Trazo base del lazo isotipo (reforzado para pantallas de alta densidad)
    final basePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.6
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..color = color.withValues(alpha: 0.95);

    canvas.drawPath(path, basePaint);

    // Chispa luminosa que recorre el isotipo con nitidez
    final metrics = path.computeMetrics().toList();
    if (metrics.isNotEmpty) {
      final metric = metrics.first;
      final totalLen = metric.length;
      final headDist = (progress * totalLen) % totalLen;
      final tangent = metric.getTangentForOffset(headDist);
      if (tangent != null) {
        // Chispa blanca en cabeza
        canvas.drawCircle(
          tangent.position,
          2.0,
          Paint()..color = Colors.white,
        );
        // Aura suave de la chispa
        canvas.drawCircle(
          tangent.position,
          4.5,
          Paint()
            ..color = color.withValues(alpha: 0.65)
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2.0),
        );
      }
    }
  }

  Path _createLemniscatePath(
      double cx, double cy, double w, double h, double tilt) {
    final path = Path();
    const n = 54;
    final a = w / 2;
    final b = h;
    final cosT = math.cos(tilt);
    final sinT = math.sin(tilt);

    for (int i = 0; i <= n; i++) {
      final t = (i / n) * 2 * math.pi;
      final rx = a * math.sin(t);
      final ry = (b / 2) * math.sin(2 * t);
      final px = cx + rx * cosT - ry * sinT;
      final py = cy + rx * sinT + ry * cosT;
      if (i == 0) {
        path.moveTo(px, py);
      } else {
        path.lineTo(px, py);
      }
    }
    path.close();
    return path;
  }

  @override
  bool shouldRepaint(covariant _SaraLoopIconPainter oldDelegate) {
    return oldDelegate.progress != progress || oldDelegate.color != color;
  }
}

/// Pintor del estallido en lazo SARA al presionar el botón del asistente.
/// Traza dos lazos convergentes con estela de partículas y resplandor perla.
class SaraLoopBurstPainter extends CustomPainter {
  final double progress;
  final bool isDark;
  final Color accentColor;

  SaraLoopBurstPainter({
    required this.progress,
    required this.isDark,
    required this.accentColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (progress <= 0.0 || progress >= 1.0) return;

    final cx = size.width / 2;
    final cy = size.height / 2;

    // El lazo se expande desde el botón hacia el exterior
    final expansion = 0.85 + (progress * 0.45);
    final loopW = size.width * 1.15 * expansion;
    final loopH = size.height * 1.85 * expansion;

    // Decaimiento de opacidad hacia el final del estallido
    final alphaFade = (1.0 - math.pow(progress, 1.8)).clamp(0.0, 1.0);

    final path = Path();
    const n = 64;
    final a = loopW / 2;
    final b = loopH;
    const tilt = -0.22;
    final cosT = math.cos(tilt);
    final sinT = math.sin(tilt);

    for (int i = 0; i <= n; i++) {
      final t = (i / n) * 2 * math.pi;
      final rx = a * math.sin(t);
      final ry = (b / 2) * math.sin(2 * t);
      final px = cx + rx * cosT - ry * sinT;
      final py = cy + rx * sinT + ry * cosT;
      if (i == 0) {
        path.moveTo(px, py);
      } else {
        path.lineTo(px, py);
      }
    }
    path.close();

    final metrics = path.computeMetrics().toList();
    if (metrics.isEmpty) return;
    final metric = metrics.first;
    final totalLen = metric.length;

    // Velocidad alta de la cabeza luminosa (2 revoluciones completas durante la animación)
    final headDist = (progress * 2.0 * totalLen) % totalLen;
    final beamLength = totalLen * 0.45;

    // 1. Pase exterior ambiental amplio
    final glowPath = _extractSubPath(metric, totalLen, headDist - beamLength, headDist);
    final auraPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 24.0
      ..strokeCap = StrokeCap.round
      ..color = const Color(0xFF6B4F73).withValues(alpha: 0.28 * alphaFade)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10.0);
    canvas.drawPath(glowPath, auraPaint);

    // 2. Pase de halo medio vibrante
    final glowPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 14.0
      ..strokeCap = StrokeCap.round
      ..color = const Color(0xFFC5AED0).withValues(alpha: 0.58 * alphaFade)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 5.0);
    canvas.drawPath(glowPath, glowPaint);

    // 3. Núcleo cromático en degradado SARA (Ciruela -> Malva -> Blanco)
    const segments = 12;
    final segLen = beamLength / segments;

    for (int i = 0; i < segments; i++) {
      final t = (i + 1) / segments;
      final start = headDist - beamLength + (i * segLen);
      final end = headDist - beamLength + ((i + 1) * segLen) + 2.0;

      final segPath = _extractSubPath(metric, totalLen, start, end);

      Color segColor;
      if (t < 0.35) {
        segColor = const Color(0xFF6B4F73)
            .withValues(alpha: (0.35 + t * 1.5) * alphaFade);
      } else if (t < 0.80) {
        final f = (t - 0.35) / 0.45;
        segColor = Color.lerp(const Color(0xFF6B4F73), const Color(0xFFC5AED0), f)!
            .withValues(alpha: (0.75 + f * 0.25) * alphaFade);
      } else {
        segColor = Colors.white.withValues(alpha: alphaFade);
      }

      // Grosor robusto: desde 3.8 dp hasta 8.2 dp
      final strokeW = 3.8 + (t * 4.4);
      final segPaint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = strokeW
        ..strokeCap = StrokeCap.round
        ..color = segColor;

      canvas.drawPath(segPath, segPaint);
    }

    // 4. Cabeza de chispa luminosa amplificada
    final tangent = metric.getTangentForOffset(headDist);
    if (tangent != null) {
      final headPos = tangent.position;

      canvas.drawCircle(
        headPos,
        10.0,
        Paint()
          ..color = const Color(0xFFC5AED0).withValues(alpha: 0.85 * alphaFade)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4.0),
      );

      canvas.drawCircle(
        headPos,
        4.2,
        Paint()..color = Colors.white.withValues(alpha: alphaFade),
      );
    }
  }

  Path _extractSubPath(
      PathMetric metric, double totalLength, double start, double end) {
    var s = start % totalLength;
    var e = end % totalLength;

    if (start < 0 && end <= 0) {
      s = (start % totalLength + totalLength) % totalLength;
      e = (end % totalLength + totalLength) % totalLength;
    }

    if (s <= e) {
      return metric.extractPath(s, e);
    } else {
      final p = Path();
      p.addPath(metric.extractPath(s, totalLength), Offset.zero);
      p.addPath(metric.extractPath(0, e), Offset.zero);
      return p;
    }
  }

  @override
  bool shouldRepaint(covariant SaraLoopBurstPainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}
