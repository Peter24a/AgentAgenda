import 'package:flutter/material.dart';

/// Tokens de diseño y paletas cromáticas oficiales de SARA (v0.4.0).
/// Ciruela desaturado (#6B4F73 / #C5AED0), superficies neutras de alta legibilidad
/// y cero degradados en componentes estándar.
class SaraColors {
  SaraColors._();

  // Modo Claro
  static const Color lightBackground = Color(0xFFF7F5F2);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightSurfaceSubtle = Color(0xFFEEEAEF);
  static const Color lightText = Color(0xFF251F29);
  static const Color lightTextSecondary = Color(0xFF6C636F);
  static const Color lightBorder = Color(0xFFDED8E2);
  static const Color lightBorderControl = Color(0xFF8C8292);
  static const Color lightAction = Color(0xFF6B4F73);
  static const Color lightActionHover = Color(0xFF5B4263);
  static const Color lightActionActive = Color(0xFF4C3654);
  static const Color lightOnAction = Color(0xFFFFFFFF);
  static const Color lightActionSoft = Color(0xFFEEE8F1);
  static const Color lightSuccess = Color(0xFF24724A);
  static const Color lightSuccessSoft = Color(0xFFDFF3E7);
  static const Color lightWarning = Color(0xFF8A5800);
  static const Color lightWarningSoft = Color(0xFFFFF3DB);
  static const Color lightError = Color(0xFFBA1A1A);
  static const Color lightErrorSoft = Color(0xFFFDECEC);
  static const Color lightInfo = Color(0xFF5B4F60);
  static const Color lightInfoSoft = Color(0xFFEEEAEF);

  // Modo Oscuro
  static const Color darkBackground = Color(0xFF151217);
  static const Color darkSurface = Color(0xFF1E1A22);
  static const Color darkSurfaceSubtle = Color(0xFF28232C);
  static const Color darkText = Color(0xFFF3EEF5);
  static const Color darkTextSecondary = Color(0xFFBEB4C4);
  static const Color darkBorder = Color(0xFF3D3544);
  static const Color darkBorderControl = Color(0xFF807488);
  static const Color darkAction = Color(0xFFC5AED0);
  static const Color darkActionHover = Color(0xFFD3BFDC);
  static const Color darkActionActive = Color(0xFFB69CC3);
  static const Color darkOnAction = Color(0xFF231B28);
  static const Color darkActionSoft = Color(0xFF302635);
  static const Color darkSuccess = Color(0xFF81C995);
  static const Color darkSuccessSoft = Color(0xFF173B2C);
  static const Color darkWarning = Color(0xFFFFD28A);
  static const Color darkWarningSoft = Color(0xFF3D2F14);
  static const Color darkError = Color(0xFFFFA6A0);
  static const Color darkErrorSoft = Color(0xFF49292D);
  static const Color darkInfo = Color(0xFFBEB4C4);
  static const Color darkInfoSoft = Color(0xFF28232C);
}

class AppColorSchemes {
  AppColorSchemes._();

  static const Color primaryLight = SaraColors.lightAction;
  static const Color primaryDark = SaraColors.darkAction;

  static const ColorScheme lightColorScheme = ColorScheme(
    brightness: Brightness.light,
    primary: SaraColors.lightAction,
    onPrimary: SaraColors.lightOnAction,
    primaryContainer: SaraColors.lightActionSoft,
    onPrimaryContainer: SaraColors.lightText,
    secondary: SaraColors.lightTextSecondary,
    onSecondary: SaraColors.lightSurface,
    secondaryContainer: SaraColors.lightSurfaceSubtle,
    onSecondaryContainer: SaraColors.lightText,
    tertiary: SaraColors.lightInfo,
    onTertiary: SaraColors.lightSurface,
    tertiaryContainer: SaraColors.lightInfoSoft,
    onTertiaryContainer: SaraColors.lightText,
    error: SaraColors.lightError,
    onError: SaraColors.lightSurface,
    errorContainer: SaraColors.lightErrorSoft,
    onErrorContainer: SaraColors.lightError,
    surface: SaraColors.lightBackground,
    onSurface: SaraColors.lightText,
    onSurfaceVariant: SaraColors.lightTextSecondary,
    surfaceContainerLowest: SaraColors.lightSurface,
    surfaceContainerLow: SaraColors.lightSurface,
    surfaceContainer: SaraColors.lightSurfaceSubtle,
    surfaceContainerHigh: SaraColors.lightActionSoft,
    surfaceContainerHighest: Color(0xFFE8E4EA),
    outline: SaraColors.lightBorderControl,
    outlineVariant: SaraColors.lightBorder,
  );

  static const ColorScheme darkColorScheme = ColorScheme(
    brightness: Brightness.dark,
    primary: SaraColors.darkAction,
    onPrimary: SaraColors.darkOnAction,
    primaryContainer: SaraColors.darkActionSoft,
    onPrimaryContainer: SaraColors.darkText,
    secondary: SaraColors.darkTextSecondary,
    onSecondary: SaraColors.darkOnAction,
    secondaryContainer: SaraColors.darkSurfaceSubtle,
    onSecondaryContainer: SaraColors.darkText,
    tertiary: SaraColors.darkInfo,
    onTertiary: SaraColors.darkOnAction,
    tertiaryContainer: SaraColors.darkInfoSoft,
    onTertiaryContainer: SaraColors.darkText,
    error: SaraColors.darkError,
    onError: SaraColors.darkErrorSoft,
    errorContainer: SaraColors.darkErrorSoft,
    onErrorContainer: SaraColors.darkError,
    surface: SaraColors.darkBackground,
    onSurface: SaraColors.darkText,
    onSurfaceVariant: SaraColors.darkTextSecondary,
    surfaceContainerLowest: SaraColors.darkBackground,
    surfaceContainerLow: SaraColors.darkSurface,
    surfaceContainer: SaraColors.darkSurface,
    surfaceContainerHigh: SaraColors.darkSurfaceSubtle,
    surfaceContainerHighest: SaraColors.darkBorder,
    outline: SaraColors.darkBorderControl,
    outlineVariant: SaraColors.darkBorder,
  );
}
