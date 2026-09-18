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
  final bool isProvisional;

  const AgendaItem({
    required this.id,
    required this.title,
    this.description,
    required this.startTime,
    this.endTime,
    required this.category,
    this.isCompleted = false,
    this.isProvisional = false,
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
    bool? isProvisional,
  }) {
    return AgendaItem(
      id: id ?? this.id,
      title: title ?? this.title,
      description: description ?? this.description,
      startTime: startTime ?? this.startTime,
      endTime: endTime ?? this.endTime,
      category: category ?? this.category,
      isCompleted: isCompleted ?? this.isCompleted,
      isProvisional: isProvisional ?? this.isProvisional,
    );
  }

  factory AgendaItem.fromJson(Map<String, dynamic> json) {
    final catStr = json['category'] as String? ?? 'general';
    final cat = ActivityCategory.values.firstWhere(
      (c) => c.name == catStr,
      orElse: () => ActivityCategory.general,
    );

    return AgendaItem(
      id: json['id'] as String,
      title: json['title'] as String,
      description: json['description'] as String?,
      startTime: DateTime.parse(json['start_time'] as String).toLocal(),
      endTime: json['end_time'] != null
          ? DateTime.parse(json['end_time'] as String).toLocal()
          : null,
      category: cat,
      isCompleted: json['is_completed'] as bool? ?? false,
      isProvisional:
          json['is_provisional'] == true ||
          json['requires_confirmation'] == true ||
          RegExp(
            r'\[(PROVISIONAL|CONDICIONAL)\]',
            caseSensitive: false,
          ).hasMatch('${json['title'] ?? ''} ${json['description'] ?? ''}') ||
          const [
            'provisional',
            'proposed',
            'draft',
            'pending_approval',
          ].contains(json['status']),
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'description': description,
    'start_time': startTime.toUtc().toIso8601String(),
    'end_time': endTime?.toUtc().toIso8601String(),
    'category': category.name,
    'is_completed': isCompleted,
  };
}
