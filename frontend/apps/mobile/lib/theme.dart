import 'package:flutter/material.dart';
import 'colyv_tokens.dart';

/// One easing curve for the whole app: quick start, long soft landing.
const Curve ease = Cubic(0.22, 1, 0.36, 1);

ThemeData colyvTheme() => ThemeData(
      useMaterial3: true,
      fontFamily: 'Geist',
      scaffoldBackgroundColor: ColyvTokens.cGround,
      colorScheme: const ColorScheme.light(
        primary: ColyvTokens.cAccent,
        onPrimary: ColyvTokens.cOnAccent,
        surface: ColyvTokens.cSurface,
        onSurface: ColyvTokens.cInk,
      ),
      splashFactory: NoSplash.splashFactory,
      highlightColor: Colors.transparent,
    );

/// Text styles. Sizes follow a small scale; big numbers are light and tightly spaced.
class Txt {
  static const ink = ColyvTokens.cInk;
  static const muted = ColyvTokens.cInkMuted;
  static const name = TextStyle(fontSize: 22, height: 1.2, fontWeight: FontWeight.w600, letterSpacing: -0.6, color: ink);
  static const title = TextStyle(fontSize: 15, height: 1.3, fontWeight: FontWeight.w600, letterSpacing: -0.2, color: ink);
  static const body = TextStyle(fontSize: 14, height: 1.4, fontWeight: FontWeight.w400, color: ink);
  static const small = TextStyle(fontSize: 12.5, height: 1.4, fontWeight: FontWeight.w400, color: muted);
  static const label = TextStyle(fontSize: 12.5, height: 1.2, fontWeight: FontWeight.w600, color: ink);
  static const chip = TextStyle(fontSize: 11.5, height: 1.2, fontWeight: FontWeight.w600, color: ink);
  static const caption = TextStyle(fontSize: 11, height: 1.2, fontWeight: FontWeight.w600, letterSpacing: 0.9, color: muted);
  static const big = TextStyle(fontSize: 46, height: 1, fontWeight: FontWeight.w300, letterSpacing: -2.3, color: ink, fontFeatures: [FontFeature.tabularFigures()]);
  static const mid = TextStyle(fontSize: 30, height: 1, fontWeight: FontWeight.w300, letterSpacing: -1.2, color: ink, fontFeatures: [FontFeature.tabularFigures()]);
  static const num = TextStyle(fontSize: 22, height: 1.1, fontWeight: FontWeight.w400, letterSpacing: -0.6, color: ink, fontFeatures: [FontFeature.tabularFigures()]);
}
