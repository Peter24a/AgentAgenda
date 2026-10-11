import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/material.dart';

import '../../../../core/theme/beam_color_notifier.dart';

/// A light ribbon that follows the screen and clears the assistant button.
class AgentScreenBorder extends StatefulWidget {
  final Widget child;
  final GlobalKey? assistantKey;

  const AgentScreenBorder({super.key, required this.child, this.assistantKey});

  @override
  State<AgentScreenBorder> createState() => _AgentScreenBorderState();
}

class _AgentScreenBorderState extends State<AgentScreenBorder>
    with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  late final AnimationController _controller;
  final _canvasKey = GlobalKey();
  final _assistantBounds = ValueNotifier<Rect?>(null);
  late final Listenable _repaint;
  bool _measureScheduled = false;
  bool _resumed = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 10),
    );
    _repaint = Listenable.merge([_controller, _assistantBounds]);
    BeamColorConfig.isEnabled.addListener(_updateAnimation);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _updateAnimation();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _resumed = state == AppLifecycleState.resumed;
    _updateAnimation();
  }

  void _updateAnimation() {
    final animate =
        BeamColorConfig.isEnabled.value &&
        !MediaQuery.disableAnimationsOf(context) &&
        TickerMode.valuesOf(context).enabled &&
        _resumed;
    if (animate && !_controller.isAnimating) {
      _controller.repeat();
    } else if (!animate) {
      _controller.stop();
    }
  }

  void _measureAssistant() {
    if (_measureScheduled) return;
    _measureScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _measureScheduled = false;
      if (!mounted) return;
      final canvas = _canvasKey.currentContext?.findRenderObject();
      final button = widget.assistantKey?.currentContext?.findRenderObject();
      _assistantBounds.value =
          canvas is RenderBox &&
              canvas.hasSize &&
              button is RenderBox &&
              button.hasSize
          ? canvas.globalToLocal(button.localToGlobal(Offset.zero)) &
                button.size
          : null;
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    BeamColorConfig.isEnabled.removeListener(_updateAnimation);
    _controller.dispose();
    _assistantBounds.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    // Re-measure when text size or safe-area insets move the button.
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    return LayoutBuilder(
      builder: (context, constraints) {
        _measureAssistant();
        return Stack(
          fit: StackFit.expand,
          children: [
            widget.child,
            Positioned.fill(
              child: IgnorePointer(
                child: ExcludeSemantics(
                  child: RepaintBoundary(
                    child: ListenableBuilder(
                      listenable: Listenable.merge([
                        BeamColorConfig.isEnabled,
                        BeamColorConfig.currentOption,
                        BeamColorConfig.currentPathStyle,
                      ]),
                      builder: (context, _) => CustomPaint(
                        key: _canvasKey,
                        painter:
                            BeamColorConfig.isEnabled.value && !reduceMotion
                            ? _RibbonPainter(
                                animation: _controller,
                                bounds: _assistantBounds,
                                repaint: _repaint,
                                option: BeamColorConfig.currentOption.value,
                                pathStyle:
                                    BeamColorConfig.currentPathStyle.value,
                                isDark: isDark,
                              )
                            : null,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _RibbonPainter extends CustomPainter {
  final Animation<double> animation;
  final ValueNotifier<Rect?> bounds;
  final BeamThemeOption option;
  final BeamPathStyle pathStyle;
  final bool isDark;
  Size? _cachedSize;
  Rect? _cachedBounds;
  PathMetric? _metric;

  _RibbonPainter({
    required this.animation,
    required this.bounds,
    required Listenable repaint,
    required this.option,
    required this.pathStyle,
    required this.isDark,
  }) : super(repaint: repaint);

  PathMetric? _pathMetric(Size size) {
    if (_cachedSize == size && _cachedBounds == bounds.value) return _metric;
    _cachedSize = size;
    _cachedBounds = bounds.value;
    if (size.shortestSide < 24) return _metric = null;

    const inset = 3.0;
    final edge = (Offset.zero & size).deflate(inset);
    final radius = math.min(44.0, size.shortestSide * 0.1);
    final button = bounds.value;
    final loop = pathStyle == BeamPathStyle.saraAssistantLoop && button != null
        ? button.inflate(7)
        : null;
    // Leave room for the transition even on narrow screens or large text.
    final bottomRadius = loop == null
        ? radius
        : math.min(radius, math.max(4.0, (edge.width - loop.width) / 2 - 6));
    final path = Path()
      ..moveTo(size.width / 2, edge.top)
      ..lineTo(edge.right - radius, edge.top)
      ..arcToPoint(
        Offset(edge.right, edge.top + radius),
        radius: Radius.circular(radius),
      )
      ..lineTo(edge.right, edge.bottom - bottomRadius)
      ..arcToPoint(
        Offset(edge.right - bottomRadius, edge.bottom),
        radius: Radius.circular(bottomRadius),
      );

    if (loop != null &&
        edge.contains(loop.topLeft) &&
        edge.contains(loop.bottomRight)) {
      final r = math.min(22.0, loop.height / 2);
      final transition = math.max(
        0.0,
        (edge.width - loop.width) / 2 - bottomRadius,
      );
      // A single continuous arc skirts the button; it never crosses its label.
      path
        ..lineTo(loop.right + transition / 2, edge.bottom)
        ..cubicTo(
          loop.right,
          edge.bottom,
          loop.right,
          loop.bottom,
          loop.right,
          loop.top + r,
        )
        ..arcToPoint(
          Offset(loop.right - r, loop.top),
          radius: Radius.circular(r),
          clockwise: false,
        )
        ..lineTo(loop.left + r, loop.top)
        ..arcToPoint(
          Offset(loop.left, loop.top + r),
          radius: Radius.circular(r),
          clockwise: false,
        )
        ..cubicTo(
          loop.left,
          loop.bottom,
          loop.left,
          edge.bottom,
          loop.left - transition / 2,
          edge.bottom,
        );
    }
    path
      ..lineTo(edge.left + bottomRadius, edge.bottom)
      ..arcToPoint(
        Offset(edge.left, edge.bottom - bottomRadius),
        radius: Radius.circular(bottomRadius),
      )
      ..lineTo(edge.left, edge.top + radius)
      ..arcToPoint(
        Offset(edge.left + radius, edge.top),
        radius: Radius.circular(radius),
      )
      ..close();
    return _metric = path.computeMetrics().first;
  }

  @override
  void paint(Canvas canvas, Size size) {
    final metric = _pathMetric(size);
    if (metric == null || metric.length <= 0) return;
    final length = math.min(220.0, metric.length * 0.12);
    final head = animation.value * metric.length;
    final ribbon = _extract(metric, head - length, head);
    canvas.drawPath(
      ribbon,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 7
        ..strokeCap = StrokeCap.round
        ..color = option.primaryColor.withValues(alpha: isDark ? 0.2 : 0.12)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3),
    );

    // A single colored mesh avoids darker seams between translucent strokes.
    const segments = 80;
    final positions = <Offset>[];
    final colors = <Color>[];
    final palette = option.colors.isEmpty
        ? [option.primaryColor]
        : option.colors;
    Color colorAt(double t) {
      final position = t * (palette.length - 1);
      final index = position.floor();
      var color = Color.lerp(
        palette[index],
        palette[math.min(index + 1, palette.length - 1)],
        position - index,
      )!;
      if (!isDark && color.computeLuminance() > 0.7) {
        color = Color.lerp(color, const Color(0xFF6B4F73), 0.38)!;
      }
      return color.withValues(alpha: t * (isDark ? 0.92 : 0.8));
    }

    void addSection(Offset point, Offset direction, double width, Color color) {
      final normal = Offset(-direction.dy, direction.dx) * (width / 2);
      positions.addAll([point + normal, point - normal]);
      colors.addAll([color, color]);
    }

    for (var i = 0; i <= segments; i++) {
      final t = i / segments;
      final tangent = metric.getTangentForOffset(
        (head - length + t * length) % metric.length,
      );
      if (tangent == null) continue;
      addSection(tangent.position, tangent.vector, 1.1 + t * 1.3, colorAt(t));
    }
    final tip = metric.getTangentForOffset(head);
    if (tip != null) {
      for (var i = 1; i <= 4; i++) {
        final angle = i / 4 * math.pi / 2;
        addSection(
          tip.position + tip.vector * (1.2 * math.sin(angle)),
          tip.vector,
          2.4 * math.cos(angle),
          colorAt(1),
        );
      }
    }
    if (positions.length >= 4) {
      final mesh = Vertices(
        VertexMode.triangleStrip,
        positions,
        colors: colors,
      );
      canvas.drawVertices(
        mesh,
        BlendMode.modulate,
        Paint()..color = Colors.white,
      );
      mesh.dispose();
    }
  }

  Path _extract(PathMetric metric, double start, double end) {
    final s = start % metric.length;
    final e = end % metric.length;
    if (s <= e) return metric.extractPath(s, e);
    return Path()
      ..addPath(metric.extractPath(s, metric.length), Offset.zero)
      ..addPath(metric.extractPath(0, e), Offset.zero);
  }

  @override
  bool shouldRepaint(covariant _RibbonPainter oldDelegate) =>
      oldDelegate.option != option ||
      oldDelegate.pathStyle != pathStyle ||
      oldDelegate.isDark != isDark ||
      oldDelegate.animation != animation ||
      oldDelegate.bounds != bounds;
}
