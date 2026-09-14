import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../../../../core/theme/beam_color_notifier.dart';

/// Borde perimetral ultra optimizado para 120 FPS con soporte multicolor y monocromático.
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
      duration: const Duration(milliseconds: 3800),
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

        Positioned.fill(
          child: IgnorePointer(
            child: RepaintBoundary(
              child: ValueListenableBuilder<BeamThemeOption>(
                valueListenable: BeamColorConfig.currentOption,
                builder: (context, beamOption, _) {
                  return AnimatedBuilder(
                    animation: _controller,
                    builder: (context, _) {
                      return CustomPaint(
                        painter: _FastShaderBeamPainter(
                          progress: _controller.value,
                          option: beamOption,
                        ),
                      );
                    },
                  );
                },
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _FastShaderBeamPainter extends CustomPainter {
  final double progress;
  final BeamThemeOption option;

  _FastShaderBeamPainter({
    required this.progress,
    required this.option,
  });

  @override
  void paint(Canvas canvas, Size size) {
    const inset = 4.0;
    const cornerRadius = 48.0;

    final rect = Rect.fromLTWH(
      inset,
      inset,
      size.width - (inset * 2),
      size.height - (inset * 2),
    );

    final rrect = RRect.fromRectAndRadius(
      rect,
      const Radius.circular(cornerRadius),
    );

    final List<Color> gradientColors;
    final List<double> gradientStops;

    if (option.isMulticolor) {
      // Degradado multicolor Google / Gemini que fluye en el cuerpo del "gusanito"
      gradientColors = [
        Colors.transparent,
        Colors.transparent,
        const Color(0xFF4285F4).withValues(alpha: 0.15), // Cola azul
        const Color(0xFF9C27B0).withValues(alpha: 0.60), // Púrpura
        const Color(0xFFEA4335).withValues(alpha: 0.75), // Rojo
        const Color(0xFFFBBC05).withValues(alpha: 0.85), // Amarillo
        const Color(0xFF34A853).withValues(alpha: 0.90), // Verde
        const Color(0xFF26C6DA).withValues(alpha: 0.95), // Cian
        Colors.white.withValues(alpha: 0.98),            // Cabeza blanca brillante
        Colors.transparent,
      ];
      gradientStops = const [
        0.0,
        0.72,
        0.75,
        0.80,
        0.85,
        0.90,
        0.94,
        0.97,
        0.995,
        1.0,
      ];
    } else {
      final color = option.primaryColor;
      gradientColors = [
        Colors.transparent,
        Colors.transparent,
        color.withValues(alpha: 0.10),
        color.withValues(alpha: 0.75),
        Colors.white.withValues(alpha: 0.95),
        Colors.transparent,
      ];
      gradientStops = const [
        0.0,
        0.74,
        0.86,
        0.97,
        0.995,
        1.0,
      ];
    }

    final shader = SweepGradient(
      center: Alignment.center,
      startAngle: 0.0,
      endAngle: math.pi * 2,
      transform: GradientRotation(progress * math.pi * 2),
      colors: gradientColors,
      stops: gradientStops,
    ).createShader(rect);

    // 1. Pase exterior: Halo difuso
    final glowPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.6
      ..strokeCap = StrokeCap.round
      ..shader = shader;

    canvas.drawRRect(rrect, glowPaint);

    // 2. Pase interior: Núcleo nítido de luz
    final corePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6
      ..strokeCap = StrokeCap.round
      ..shader = shader;

    canvas.drawRRect(rrect, corePaint);
  }

  @override
  bool shouldRepaint(covariant _FastShaderBeamPainter oldDelegate) {
    return oldDelegate.progress != progress || oldDelegate.option != option;
  }
}
