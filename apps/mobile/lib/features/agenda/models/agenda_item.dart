import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

/// Categorías de actividades con identidad visual Pixel.
enum ActivityCategory {
  sleep(
    label: 'Dormir & Descanso',
    primaryEmoji: '🌙',
    backgroundEmojis: ['✨', '🌙', '💤', '⭐', '🌌'],
    tintColor: Color(0xFF5C6BC0),
  ),
  work(
    label: 'Trabajo & Enfoque',
    primaryEmoji: '💼',
    backgroundEmojis: ['💻', '⚡', '📊', '🎯', '📁'],
    tintColor: Color(0xFF0288D1),
  ),
  food(
    label: 'Comida & Café',
    primaryEmoji: '☕',
    backgroundEmojis: ['☕', '🥐', '🥑', '🥞', '🍽️'],
    tintColor: Color(0xFFF57C00),
  ),
  exercise(
    label: 'Ejercicio & Salud',
    primaryEmoji: '🏃',
    backgroundEmojis: ['🏃', '💪', '🔥', '👟', '🚴'],
    tintColor: Color(0xFF43A047),
  ),
  study(
    label: 'Estudio & Lectura',
    primaryEmoji: '📚',
    backgroundEmojis: ['📚', '💡', '✍️', '🧠', '📖'],
    tintColor: Color(0xFF8E24AA),
  ),
  leisure(
    label: 'Ocio & Social',
    primaryEmoji: '🎮',
    backgroundEmojis: ['🎮', '🍿', '🎧', '✨', '🎉'],
    tintColor: Color(0xFFE91E63),
  ),
  general(
    label: 'General',
    primaryEmoji: '📌',
    backgroundEmojis: ['📌', '⭐', '🗓️', '✨', '⏰'],
    tintColor: Color(0xFF00897B),
  );

  const ActivityCategory({
    required this.label,
    required this.primaryEmoji,
    required this.backgroundEmojis,
    required this.tintColor,
  });

  final String label;
  final String primaryEmoji;
  final List<String> backgroundEmojis;
  final Color tintColor;
}

/// Modelo de un elemento de la agenda.
class AgendaItem {
  final String id;
  final String title;
  final String? description;
  final DateTime startTime;
  final DateTime? endTime;
  final ActivityCategory category;
  final bool isCompleted;

  const AgendaItem({
    required this.id,
    required this.title,
    this.description,
    required this.startTime,
    this.endTime,
    required this.category,
    this.isCompleted = false,
  });

  String get formattedTime => DateFormat('HH:mm').format(startTime);

  String? get formattedEndTime =>
      endTime != null ? DateFormat('HH:mm').format(endTime!) : null;

  String get timeRange => formattedEndTime != null
      ? '$formattedTime - $formattedEndTime'
      : formattedTime;

  AgendaItem copyWith({
    String? id,
    String? title,
    String? description,
    DateTime? startTime,
    DateTime? endTime,
    ActivityCategory? category,
    bool? isCompleted,
  }) {
    return AgendaItem(
      id: id ?? this.id,
      title: title ?? this.title,
      description: description ?? this.description,
      startTime: startTime ?? this.startTime,
      endTime: endTime ?? this.endTime,
      category: category ?? this.category,
      isCompleted: isCompleted ?? this.isCompleted,
    );
  }
}
