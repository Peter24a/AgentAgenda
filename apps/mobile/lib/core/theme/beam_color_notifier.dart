import 'package:flutter/material.dart';

/// Notificador y opciones para el lazo luminoso ("gusanito").
class BeamColorConfig {
  BeamColorConfig._();

  static const List<BeamThemeOption> options = [
    BeamThemeOption(
      name: 'Ciruela SARA (Logo)',
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
      name: 'Multicolor Google',
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
      name: 'Malva Tonal',
      primaryColor: Color(0xFFC5AED0),
      colors: [Color(0xFFC5AED0)],
    ),
    BeamThemeOption(
      name: 'Blanco Perla',
      primaryColor: Color(0xFFFFFFFF),
      colors: [Color(0xFFFFFFFF)],
    ),
    BeamThemeOption(
      name: 'Azul Google',
      primaryColor: Color(0xFF8AB4F8),
      colors: [Color(0xFF8AB4F8)],
    ),
    BeamThemeOption(
      name: 'Cian Pixel',
      primaryColor: Color(0xFF53DBC9),
      colors: [Color(0xFF53DBC9)],
    ),
    BeamThemeOption(
      name: 'Oro Champagne',
      primaryColor: Color(0xFFFDD663),
      colors: [Color(0xFFFDD663)],
    ),
    BeamThemeOption(
      name: 'Coral Atardecer',
      primaryColor: Color(0xFFF28B82),
      colors: [Color(0xFFF28B82)],
    ),
  ];

  static final ValueNotifier<BeamThemeOption> currentOption =
      ValueNotifier<BeamThemeOption>(options[0]);

  static final ValueNotifier<bool> isEnabled = ValueNotifier<bool>(true);
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
