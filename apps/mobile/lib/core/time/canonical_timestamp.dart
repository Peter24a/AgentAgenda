/// The backend stores canonical timestamps as UTC, sometimes without an offset.
/// Explicit Z/offset values already parse as UTC; timezone-free values must not
/// inherit the device timezone before being shown locally.
DateTime parseCanonicalTimestamp(String value) {
  final hasTime = RegExp(r'[Tt ]\d').hasMatch(value);
  final hasOffset =
      hasTime && RegExp(r'(?:[zZ]|[+-]\d{2}(?::?\d{2})?)$').hasMatch(value);
  // Parse as UTC before applying the device zone: parsing a naive instant as
  // local first can change its clock fields at a daylight-saving transition.
  final explicitUtc = hasOffset
      ? value
      : hasTime
      ? '${value}Z'
      : '${value}T00:00:00Z';
  return DateTime.parse(explicitUtc).toLocal();
}
