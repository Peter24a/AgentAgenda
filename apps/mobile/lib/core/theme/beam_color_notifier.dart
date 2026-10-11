import 'package:flutter/material.dart';

/// Opciones de color y recorrido del lazo de luz.
class BeamColorConfig {
  BeamColorConfig._();

  static const List<BeamThemeOption> options = [
    BeamThemeOption(
      name: 'Ciruela SARA',
      primaryColor: Color(0xFF6B4F73),
      colors: [
        Color(0xFF6B4F73), // Ciruela institucional SARA
        Color(0xFF9E80A8), // Malva intermedio
        Color(0xFFC5AED0), // Malva claro de acción
        Color(0xFFFFFFFF), // Cabeza blanca luminosa
      ],
      isMulticolor: false,
    ),
    BeamThemeOption(
      name: 'Multicolor',
      isMulticolor: true,
      primaryColor: Color(0xFF4285F4),
      colors: [
        Color(0xFF4285F4), // Azul
        Color(0xFF9C27B0), // Púrpura
        Color(0xFFEA4335), // Rojo
        Color(0xFFFBBC05), // Amarillo
        Color(0xFF34A853), // Verde
        Color(0xFF26C6DA), // Cian
      ],
    ),
    BeamThemeOption(
      name: 'Malva',
      primaryColor: Color(0xFFC5AED0),
      colors: [Color(0xFFC5AED0)],
    ),
    BeamThemeOption(
      name: 'Perla',
      primaryColor: Color(0xFFFFFFFF),
      colors: [Color(0xFFFFFFFF)],
    ),
    BeamThemeOption(
      name: 'Azul',
      primaryColor: Color(0xFF8AB4F8),
      colors: [Color(0xFF8AB4F8)],
    ),
    BeamThemeOption(
      name: 'Menta',
      primaryColor: Color(0xFF53DBC9),
      colors: [Color(0xFF53DBC9)],
    ),
    BeamThemeOption(
      name: 'Dorado',
      primaryColor: Color(0xFFFDD663),
      colors: [Color(0xFFFDD663)],
    ),
    BeamThemeOption(
      name: 'Coral',
      primaryColor: Color(0xFFF28B82),
      colors: [Color(0xFFF28B82)],
    ),
  ];

  static final ValueNotifier<BeamThemeOption> currentOption =
      ValueNotifier<BeamThemeOption>(options[0]);

  static final ValueNotifier<bool> isEnabled = ValueNotifier<bool>(true);

  static final ValueNotifier<BeamPathStyle> currentPathStyle =
      ValueNotifier<BeamPathStyle>(BeamPathStyle.saraAssistantLoop);
}

enum BeamPathStyle {
  saraAssistantLoop(
    'Junto al asistente',
    'La luz recorre el borde y rodea el botón del asistente.',
  ),
  fullBezel('Todo el contorno', 'La luz sigue el borde de la pantalla.');

  final String label;
  final String description;
  const BeamPathStyle(this.label, this.description);
}

class BeamThemeOption {
  final String name;
  final Color primaryColor;
  final List<Color> colors;
  final bool isMulticolor;

  const BeamThemeOption({
    required this.name,
    required this.primaryColor,
    required this.colors,
    this.isMulticolor = false,
  });
}
