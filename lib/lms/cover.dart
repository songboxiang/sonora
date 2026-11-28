import "dart:io";
import "dart:typed_data";
import "dart:ui" as ui;

import "package:flutter/material.dart";

import "../core/services.dart";

/// LMS cover art requires HTTP Basic Auth in a header; query parameters are
/// rejected with 401 and NetworkImage cannot set headers. This provider uses
/// the shared HttpClient so the same credentials as JSON-RPC are applied.
class LmsCoverImage extends ImageProvider<LmsCoverImage> {
  const LmsCoverImage({required this.target, required this.coverId, this.size = 160});

  final LmsTarget target;
  final String coverId;
  final int size;

  @override
  Future<LmsCoverImage> obtainKey(ImageConfiguration configuration) async => this;

  @override
  ImageStreamCompleter loadImage(LmsCoverImage key, ImageDecoderCallback decode) {
    return OneFrameImageStreamCompleter(_loadInfo(key, decode));
  }

  Future<ImageInfo> _loadInfo(LmsCoverImage key, ImageDecoderCallback decode) async {
    final image = await _load(key, decode);
    return ImageInfo(image: image);
  }

  Future<ui.Image> _load(LmsCoverImage key, ImageDecoderCallback decode) async {
    final url = "${key.target.baseUrl}/music/${key.coverId}/cover";
    final req = await httpClient.getUrl(Uri.parse(url));
    final auth = key.target.auth;
    if (auth != null) req.headers.set(HttpHeaders.authorizationHeader, auth);
    req.headers.set(HttpHeaders.connectionHeader, "close");
    final resp = await req.close();
    if (resp.statusCode != 200) {
      throw FlutterError("LMS 封面 HTTP ${resp.statusCode}");
    }
    final chunks = await resp.fold<BytesBuilder>(
      BytesBuilder(),
      (b, chunk) => b..add(chunk),
    );
    final codec = await ui.instantiateImageCodec(
      chunks.takeBytes(),
      targetWidth: key.size,
      targetHeight: key.size,
    );
    final frame = await codec.getNextFrame();
    return frame.image;
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is LmsCoverImage &&
          other.coverId == coverId &&
          other.target.baseUrl == target.baseUrl &&
          other.size == size);

  @override
  int get hashCode => Object.hash(coverId, target.baseUrl, size);
}
