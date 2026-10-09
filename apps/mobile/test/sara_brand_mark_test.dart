import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:agent_agenda/core/branding/sara_brand_mark.dart';
import 'package:agent_agenda/features/agenda/presentation/widgets/premium_agent_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'Dart mark matches the original four SVG paths pixel for pixel',
    () async {
      final source = File(
        '../../distribution/branding/source/sara_isotipo_blanco.svg',
      ).readAsStringSync();
      final originals = RegExp(r'<path\s+([^>]+)>').allMatches(source).toList();
      expect(originals, hasLength(4));
      for (final color in [Colors.white, const Color(0xFF6B4F73)]) {
        final actual = await _rasterize((canvas, size) {
          SaraIsotipoPainter(color: color).paint(canvas, size);
        });
        final expected = await _rasterize((canvas, size) {
          final scale = math.min(size.width / 720, size.height / 540);
          canvas.translate(
            (size.width - 720 * scale) / 2,
            (size.height - 540 * scale) / 2,
          );
          canvas.scale(scale);
          canvas.translate(-150, -70);
          for (final original in originals) {
            final attributes = original.group(1)!;
            final translation = RegExp(
              r'transform="translate\(([^,]+),([^\)]+)\)"',
            ).firstMatch(attributes)!;
            final pathData = RegExp(r'\bd="([^"]+)"')
                .firstMatch(attributes)!
                .group(1)!;
            final path = _svgPath(pathData).shift(
              Offset(
                double.parse(translation.group(1)!),
                double.parse(translation.group(2)!),
              ),
            );
            canvas.drawPath(path, Paint()..color = color);
          }
        });
        expect(actual, orderedEquals(expected));
      }
    },
  );

  testWidgets('Assistant button keeps its tap guard and reopens after delay', (
    tester,
  ) async {
    var openings = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          bottomNavigationBar: PremiumAgentButton(onTap: () => openings++),
        ),
      ),
    );
    final button = find.text('Asistente SARA');
    await tester.tap(button);
    await tester.tap(button);
    expect(openings, 0);
    await tester.pump(const Duration(milliseconds: 250));
    expect(openings, 1);
    await tester.tap(button);
    await tester.pump(const Duration(milliseconds: 350));
    expect(openings, 1);
    await tester.tap(button);
    await tester.pump(const Duration(milliseconds: 250));
    expect(openings, 2);
    await tester.pump(const Duration(milliseconds: 350));
  });
}

Future<List<int>> _rasterize(void Function(Canvas, Size) paint) async {
  final recorder = ui.PictureRecorder();
  paint(Canvas(recorder), const Size.square(192));
  final picture = recorder.endRecording();
  final image = await picture.toImage(192, 192);
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  image.dispose();
  picture.dispose();
  return data!.buffer.asUint8List();
}

Path _svgPath(String data) {
  final tokens = RegExp(r'[MCZ]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?')
      .allMatches(data)
      .map((match) => match.group(0)!)
      .toList();
  final path = Path();
  var position = 0;
  String? command;
  double number() => double.parse(tokens[position++]);
  while (position < tokens.length) {
    if (['M', 'C', 'Z'].contains(tokens[position])) {
      command = tokens[position++];
    }
    switch (command) {
      case 'M':
        path.moveTo(number(), number());
        command = null;
      case 'C':
        path.cubicTo(
          number(),
          number(),
          number(),
          number(),
          number(),
          number(),
        );
      case 'Z':
        path.close();
        command = null;
      default:
        throw FormatException('Unsupported command in canonical SVG');
    }
  }
  return path;
}
