/// The picture on the system clipboard, read through the runtime channel.
///
/// Android keeps a copied image behind a content:// URI, so Flutter's text-only clipboard
/// cannot see it; the native side reads the bytes. BMP is decoded and re-encoded as PNG
/// because the chat accepts PNG, JPEG, GIF and WebP only.
library;

import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// One image off the clipboard, already in a format the chat accepts.
class ClipboardImage {
  const ClipboardImage({required this.bytes, required this.mime, required this.extension});

  final Uint8List bytes;
  final String mime;
  final String extension;
}

final clipboardImageProvider = Provider<ClipboardImageReader>((ref) => ClipboardImageReader());

class ClipboardImageReader {
  static const _channel = MethodChannel('dsh/runtime');

  /// Null when the clip holds no picture (or the platform has no reader).
  Future<ClipboardImage?> read() async {
    final Map<String, Object?>? map;
    try {
      map = await _channel.invokeMapMethod<String, Object?>('readClipboardImage');
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
    final raw = map?['bytes'];
    final Uint8List? bytes = switch (raw) {
      final Uint8List value => value,
      final List<Object?> value => Uint8List.fromList(value.whereType<int>().toList()),
      _ => null,
    };
    if (bytes == null || bytes.isEmpty) return null;
    final mime = map?['mime'] as String? ?? 'image/png';
    if (mime == 'image/bmp') {
      final png = await _toPng(bytes);
      return png == null ? null : ClipboardImage(bytes: png, mime: 'image/png', extension: 'png');
    }
    return ClipboardImage(bytes: bytes, mime: mime, extension: _extensionFor(mime));
  }

  Future<Uint8List?> _toPng(Uint8List bytes) async {
    try {
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final data = await frame.image.toByteData(format: ui.ImageByteFormat.png);
      frame.image.dispose();
      return data?.buffer.asUint8List();
    } catch (_) {
      return null;
    }
  }

  String _extensionFor(String mime) => switch (mime) {
    'image/png' => 'png',
    'image/jpeg' => 'jpg',
    'image/gif' => 'gif',
    'image/webp' => 'webp',
    _ => 'png',
  };
}
