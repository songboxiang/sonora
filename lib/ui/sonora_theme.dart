import 'dart:ui' as ui;

import 'package:flutter/material.dart';

/// Visual language ported from the earlier CSS build: deep teal glass,
/// mint highlight and a warm gold accent on the progress bar.
class SonoraColors {
  static const background = Color(0xFF081418);
  static const surface = Color(0xFF0D2429);
  static const surface2 = Color(0xFF12333A);
  static const panel = Color(0x990D2429);
  static const primary = Color(0xFF7CC7A6);
  static const primaryDark = Color(0xFF2F6B52);
  static const gold = Color(0xFFDCB96A);
  static const text = Color(0xFFEAF3EF);
  static const text2 = Color(0xFFA6BDB6);
  static const text3 = Color(0xFF6E8984);
  static const line = Color(0xFF22444A);
}

ThemeData sonoraTheme() {
  final scheme = ColorScheme.dark(
    primary: SonoraColors.primary,
    onPrimary: SonoraColors.background,
    secondary: SonoraColors.gold,
    surface: SonoraColors.surface,
    onSurface: SonoraColors.text,
  );
  return ThemeData(
    colorScheme: scheme,
    scaffoldBackgroundColor: SonoraColors.background,
    cardColor: SonoraColors.surface,
    canvasColor: SonoraColors.background,
    primaryColor: SonoraColors.primary,
    hintColor: SonoraColors.text3,
    dividerColor: SonoraColors.line,
    appBarTheme: const AppBarTheme(
      backgroundColor: SonoraColors.surface,
      foregroundColor: SonoraColors.text,
      elevation: 0,
    ),
    tabBarTheme: const TabBarThemeData(
      labelColor: SonoraColors.primary,
      unselectedLabelColor: SonoraColors.text3,
      indicatorColor: SonoraColors.primary,
    ),
    chipTheme: ChipThemeData(
      backgroundColor: SonoraColors.surface2,
      selectedColor: SonoraColors.primary,
      disabledColor: SonoraColors.surface2,
      labelStyle: const TextStyle(color: SonoraColors.text2, fontSize: 12),
      secondaryLabelStyle:
          const TextStyle(color: SonoraColors.background, fontSize: 12),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: const BorderSide(color: SonoraColors.line),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: SonoraColors.surface2,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: SonoraColors.line),
      ),
    ),
    textTheme: const TextTheme(
      bodyMedium: TextStyle(color: SonoraColors.text),
      bodySmall: TextStyle(color: SonoraColors.text2),
      titleMedium: TextStyle(color: SonoraColors.text),
      titleLarge: TextStyle(color: SonoraColors.text),
    ),
    sliderTheme: SliderThemeData(
      activeTrackColor: SonoraColors.primary,
      inactiveTrackColor: SonoraColors.line,
      thumbColor: SonoraColors.text,
      overlayColor: Color(0x337CC7A6),
      valueIndicatorColor: SonoraColors.primaryDark,
    ),
  );
}

/// Blurred album art behind the player, matching the CSS build's .player-bg.
class SonoraBackdrop extends StatelessWidget {
  final ImageProvider? cover;
  const SonoraBackdrop({super.key, this.cover});

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          if (cover != null)
            ImageFiltered(
              imageFilter: ui.ImageFilter.blur(sigmaX: 70, sigmaY: 70),
              child: Image(
                image: cover!,
                fit: BoxFit.cover,
                width: double.infinity,
                height: double.infinity,
                errorBuilder: (_, __, ___) => const SizedBox.shrink(),
              ),
            ),
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: <Color>[Color(0xDD081418), Color(0xF2081418)],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class SonoraGlassPanel extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final double radius;
  const SonoraGlassPanel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(12),
    this.radius = 16,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: SonoraColors.panel,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: const Color(0x33FFFFFF)),
        boxShadow: const <BoxShadow>[
          BoxShadow(color: Color(0x40000000), blurRadius: 24, offset: Offset(0, 8)),
        ],
      ),
      child: child,
    );
  }
}

/// Glowing round transport button used on both the regular and fullscreen
/// player. [prominent] renders the primary play/pause control.
class SonoraRoundButton extends StatelessWidget {
  final IconData icon;
  final String? tooltip;
  final VoidCallback? onPressed;
  final bool prominent;
  final double size;
  const SonoraRoundButton({
    super.key,
    required this.icon,
    this.tooltip,
    this.onPressed,
    this.prominent = false,
    this.size = 46,
  });

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip ?? "",
      child: Container(
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: prominent ? SonoraColors.primary : const Color(0x1AFFFFFF),
          border: Border.all(
            color: prominent
                ? SonoraColors.primary
                : const Color(0x33FFFFFF),
          ),
          boxShadow: prominent
              ? const <BoxShadow>[
                  BoxShadow(
                    color: Color(0x667CC7A6),
                    blurRadius: 22,
                    spreadRadius: 1,
                  ),
                ]
              : const <BoxShadow>[
                  BoxShadow(color: Color(0x33000000), blurRadius: 10),
                ],
        ),
        child: IconButton(
          icon: Icon(
            icon,
            color: prominent ? SonoraColors.background : SonoraColors.text,
          ),
          iconSize: prominent ? size * 0.52 : size * 0.46,
          onPressed: onPressed,
        ),
      ),
    );
  }
}
