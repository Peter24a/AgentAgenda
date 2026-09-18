import 'dart:math' as math;
import 'dart:ui';
import 'package:flutter/material.dart';
import '../../../../core/theme/beam_color_notifier.dart';

/// Borde perimetral ultra optimizado para 120 FPS que recorre el dispositivo.
/// Es una analogía dinámica al lazo del isotipo de SARA y al ciclo continuo de la agenda,
/// adaptado milimétricamente al radio de esquinas del Pixel 10 Pro XL (49.0 dp de curvatura interior).
class AgentScreenBorder extends StatefulWidget {
  final Widget child;

  const AgentScreenBorder({super.key, required this.child});

  @override
  State<AgentScreenBorder> createState() => _AgentScreenBorderState();
}

class _AgentScreenBorderState extends State<AgentScreenBorder>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 4000),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        widget.child,

        ValueListenableBuilder<bool>(
          valueListenable: BeamColorConfig.isEnabled,
          builder: (context, isEnabled, _) {
            if (!isEnabled) return const SizedBox.shrink();

            return Positioned.fill(
              child: IgnorePointer(
                child: RepaintBoundary(
                  child: ValueListenableBuilder<BeamThemeOption>(
                    valueListenable: BeamColorConfig.currentOption,
                    builder: (context, beamOption, _) {
                      return ValueListenableBuilder<BeamPathStyle>(
                        valueListenable: BeamColorConfig.currentPathStyle,
                        builder: (context, pathStyle, _) {
                          return AnimatedBuilder(
                            animation: _controller,
                            builder: (context, _) {
                              return CustomPaint(
                                painter: _FastPathMetricBeamPainter(
                                  progress: _controller.value,
                                  option: beamOption,
                                  pathStyle: pathStyle,
                                ),
                              );
                            },
                          );
                        },
                      );
                    },
                  ),
                ),
              ),
            );
          },
        ),
      ],
    );
  }
}

/// Pintor que utiliza [PathMetric] para garantizar velocidad lineal constante
/// y curvatura idéntica a los 123 px (50.5 dp) del hardware del Pixel 10 Pro XL.
class _FastPathMetricBeamPainter extends CustomPainter {
  final double progress;
  final BeamThemeOption option;
  final BeamPathStyle pathStyle;

  _FastPathMetricBeamPainter({
    required this.progress,
    required this.option,
    required this.pathStyle,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0 || size.height <= 0) return;

    // Medidas exactas del hardware Pixel 10 Pro XL (1080x2404 a 390dpi = 443x986dp)
    // Radio de esquinas físico: 123px / 2.4375 ≈ 50.46 dp. Con inset 1.5 dp => r = 49.0 dp.
    const inset = 1.5;
    final r = size.width > 400 ? 49.0 : 42.0;

    final x0 = inset;
    final y0 = inset;
    final x1 = size.width - inset;
    final y1 = size.height - inset;
    final cx = size.width / 2;

    final path = Path();
    path.moveTo(cx, y0);

    // 1. Borde superior derecho
    path.lineTo(x1 - r, y0);
    path.arcToPoint(Offset(x1, y0 + r), radius: Radius.circular(r));

    // 2. Borde lateral derecho
    path.lineTo(x1, y1 - r);
    path.arcToPoint(Offset(x1 - r, y1), radius: Radius.circular(r));

    // 3. Borde inferior con opción de Bucle SARA en el Asistente
    if (pathStyle == BeamPathStyle.saraAssistantLoop) {
      // Línea hasta el umbral del botón del asistente
      path.lineTo(cx + 145, y1);

      // Bucle suave que envuelve y sobrevuela el botón en un lazo continuo SARA
      // Sube y rodea la cresta superior del botón
      path.cubicTo(cx + 80, y1, cx + 60, y1 - 90, cx, y1 - 90);
      // Desciende haciendo el lazo cruzado interior
      path.cubicTo(cx - 60, y1 - 90, cx - 80, y1 - 28, cx, y1 - 28);
      // Bucle interior del isotipo
      path.cubicTo(cx + 45, y1 - 28, cx + 45, y1 - 70, cx, y1 - 70);
      // Salida continua hacia el borde inferior izquierdo
      path.cubicTo(cx - 45, y1 - 70, cx - 80, y1, cx - 145, y1);

      path.lineTo(x0 + r, y1);
    } else {
      path.lineTo(x0 + r, y1);
    }

    // 4. Borde inferior izquierdo
    path.arcToPoint(Offset(x0, y1 - r), radius: Radius.circular(r));

    // 5. Borde lateral izquierdo
    path.lineTo(x0, y0 + r);
    path.arcToPoint(Offset(x0 + r, y0), radius: Radius.circular(r));

    path.close();

    final metrics = path.computeMetrics().toList();
    if (metrics.isEmpty) return;
    final metric = metrics.first;
    final totalLength = metric.length;
    if (totalLength <= 0) return;

    // Longitud física del lazo luminoso (aprox. 220 dp)
    final beamLength = math.min(size.height * 0.24, 230.0);
    final headDist = (progress * totalLength) % totalLength;

    // Subdivisión en segmentos para degradado suave con velocidad lineal constante
    const segments = 12;
    final segLen = beamLength / segments;

    // Preparar colores del lazo
    final isSara = option.name.contains('SARA');
    final isMulti = option.isMulticolor;

    // 1. Pase exterior: Halo de resplandor ambiental
    final haloPath = _extractSubPath(metric, totalLength, headDist - beamLength, headDist);
    final haloPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 6.0
      ..strokeCap = StrokeCap.round
      ..color = (isSara ? const Color(0xFF6B4F73) : option.primaryColor).withValues(alpha: 0.28)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3.5);
    canvas.drawPath(haloPath, haloPaint);

    // 2. Pase principal: Núcleo trazado con gradiente progresivo
    for (int i = 0; i < segments; i++) {
      final t = (i + 1) / segments;
      final start = headDist - beamLength + (i * segLen);
      final end = headDist - beamLength + ((i + 1) * segLen) + 1.2; // Traslape para continuidad

      final segPath = _extractSubPath(metric, totalLength, start, end);

      Color segColor;
      if (isSara) {
        if (t < 0.40) {
          segColor = const Color(0xFF6B4F73).withValues(alpha: 0.15 + (t / 0.40) * 0.45);
        } else if (t < 0.75) {
          final factor = (t - 0.40) / 0.35;
          segColor = Color.lerp(const Color(0xFF6B4F73), const Color(0xFF9E80A8), factor)!
              .withValues(alpha: 0.60 + factor * 0.25);
        } else if (t < 0.93) {
          final factor = (t - 0.75) / 0.18;
          segColor = Color.lerp(const Color(0xFF9E80A8), const Color(0xFFC5AED0), factor)!
              .withValues(alpha: 0.85 + factor * 0.12);
        } else {
          segColor = Colors.white.withValues(alpha: 0.98);
        }
      } else if (isMulti) {
        final colors = option.colors;
        final idx = (t * (colors.length - 1)).clamp(0, colors.length - 1).toInt();
        segColor = (t > 0.94 ? Colors.white : colors[idx]).withValues(alpha: 0.25 + t * 0.72);
      } else {
        segColor = (t > 0.93
                ? Colors.white
                : Color.lerp(option.primaryColor, Colors.white, t * 0.4)!)
            .withValues(alpha: 0.15 + t * 0.82);
      }

      final strokeW = 1.8 + (t * 1.6);
      final segPaint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = strokeW
        ..strokeCap = StrokeCap.round
        ..color = segColor;

      canvas.drawPath(segPath, segPaint);
    }

    // 3. Cabeza luminosa con chispa perla
    final tangent = metric.getTangentForOffset(headDist);
    if (tangent != null) {
      final headPos = tangent.position;

      // Resplandor difuso en la punta
      canvas.drawCircle(
        headPos,
        5.5,
        Paint()
          ..color = (isSara ? const Color(0xFFC5AED0) : option.primaryColor).withValues(alpha: 0.6)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2.5),
      );

      // Núcleo blanco nítido
      canvas.drawCircle(
        headPos,
        2.2,
        Paint()..color = Colors.white,
      );
    }
  }

  Path _extractSubPath(PathMetric metric, double totalLength, double start, double end) {
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
  bool shouldRepaint(covariant _FastPathMetricBeamPainter oldDelegate) {
    return oldDelegate.progress != progress ||
        oldDelegate.option != option ||
        oldDelegate.pathStyle != pathStyle;
  }
}
