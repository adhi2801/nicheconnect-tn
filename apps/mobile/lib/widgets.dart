import 'dart:ui';
import 'package:flutter/material.dart';
import 'colyv_tokens.dart';
import 'theme.dart';

/// Press feedback: a card or button sinks a little under the finger and springs back.
class Press extends StatefulWidget {
  const Press({super.key, required this.child, this.onTap, this.scale = 0.975});
  final Widget child;
  final VoidCallback? onTap;
  final double scale;
  @override
  State<Press> createState() => _PressState();
}

class _PressState extends State<Press> {
  bool down = false;
  @override
  Widget build(BuildContext context) => GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: (_) => setState(() => down = true),
        onTapUp: (_) => setState(() => down = false),
        onTapCancel: () => setState(() => down = false),
        onTap: widget.onTap ?? () {},
        child: AnimatedScale(scale: down ? widget.scale : 1, duration: const Duration(milliseconds: 160), curve: ease, child: widget.child),
      );
}

/// Content rises and fades in once when it first appears. [delay] staggers siblings.
class Rise extends StatelessWidget {
  const Rise({super.key, required this.child, this.delay = 0});
  final Widget child;
  final int delay;
  @override
  Widget build(BuildContext context) {
    final total = 700 + delay;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: Duration(milliseconds: total),
      curve: Interval(delay / total, 1, curve: ease),
      builder: (_, t, c) => Opacity(opacity: t, child: Transform.translate(offset: Offset(0, 16 * (1 - t)), child: c)),
      child: child,
    );
  }
}

/// A number that counts to its new value whenever the value changes.
class CountNum extends StatelessWidget {
  const CountNum({super.key, required this.value, required this.format, required this.style});
  final double value;
  final String Function(double) format;
  final TextStyle style;
  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
        tween: Tween(end: value),
        duration: const Duration(milliseconds: 520),
        curve: ease,
        builder: (_, v, _) => Text(format(v), style: style),
      );
}

class GlanceColors {
  const GlanceColors(this.from, this.to);
  final Color from, to;
  static const gold = GlanceColors(ColyvTokens.cGlanceGoldFrom, ColyvTokens.cGlanceGoldTo);
  static const terracotta = GlanceColors(ColyvTokens.cGlanceTerracottaFrom, ColyvTokens.cGlanceTerracottaTo);
  static const berry = GlanceColors(ColyvTokens.cGlanceBerryFrom, ColyvTokens.cGlanceBerryTo);
  static const sand = GlanceColors(ColyvTokens.cGlanceSandFrom, ColyvTokens.cGlanceSandTo);
}

/// The glanceable card: soft gradient, a faint highlight in the corner, one big number.
class Glance extends StatelessWidget {
  const Glance({super.key, required this.colors, required this.label, required this.value, this.foot, this.spark, this.height = 158});
  final GlanceColors colors;
  final String label;
  final Widget value;
  final String? foot;
  final Widget? spark;
  final double height;
  @override
  Widget build(BuildContext context) => Press(
        child: Container(
          height: height,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(ColyvTokens.rXl),
            gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [colors.from, colors.to]),
            boxShadow: const [BoxShadow(color: Color(0x1F101012), blurRadius: 28, offset: Offset(0, 12), spreadRadius: -16)],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(ColyvTokens.rXl),
            child: Stack(children: [
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: RadialGradient(center: Alignment.topLeft, radius: 1.1, colors: [Colors.white.withValues(alpha: 0.5), Colors.white.withValues(alpha: 0)]),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 14),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                  Text(label, style: Txt.label.copyWith(color: Txt.ink.withValues(alpha: 0.72))),
                  value,
                  if (spark != null) SizedBox(height: 28, child: spark) else Text(foot ?? '', style: Txt.small.copyWith(fontSize: 11.5, color: Txt.ink.withValues(alpha: 0.72), fontWeight: FontWeight.w500)),
                ]),
              ),
            ]),
          ),
        ),
      );
}

/// A sparkline that draws itself left to right; the endpoint is emphasised.
class Spark extends StatelessWidget {
  const Spark({super.key, required this.data});
  final List<num> data;
  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
        key: ValueKey(data.join(',')),
        tween: Tween(begin: 0, end: 1),
        duration: const Duration(milliseconds: 700),
        curve: ease,
        builder: (_, t, _) => CustomPaint(painter: _SparkPainter(data, t), size: Size.infinite),
      );
}

class _SparkPainter extends CustomPainter {
  _SparkPainter(this.d, this.t);
  final List<num> d;
  final double t;
  @override
  void paint(Canvas c, Size s) {
    final mx = d.reduce((a, b) => a > b ? a : b), mn = d.reduce((a, b) => a < b ? a : b);
    Offset p(int i) => Offset(s.width * i / (d.length - 1), s.height - 4 - ((d[i] - mn) / (mx - mn == 0 ? 1 : mx - mn) * (s.height - 10)).toDouble());
    final line = Path()..moveTo(p(0).dx, p(0).dy);
    for (var i = 1; i < d.length; i++) {
      line.lineTo(p(i).dx, p(i).dy);
    }
    final w = s.width * t;
    c.save();
    c.clipRect(Rect.fromLTWH(0, 0, w, s.height));
    final fill = Path.from(line)..lineTo(s.width, s.height)..lineTo(0, s.height)..close();
    c.drawPath(fill, Paint()..color = Txt.ink.withValues(alpha: 0.12));
    c.drawPath(line, Paint()..style = PaintingStyle.stroke..strokeWidth = 1.7..strokeCap = StrokeCap.round..strokeJoin = StrokeJoin.round..color = Txt.ink);
    c.restore();
    if (t > 0.98) c.drawCircle(p(d.length - 1) - const Offset(2, 0), 2.4, Paint()..color = Txt.ink);
  }

  @override
  bool shouldRepaint(_SparkPainter o) => o.t != t || o.d != d;
}

/// A grouped surface: a heading and hairline-separated rows.
class Panel extends StatelessWidget {
  const Panel({super.key, this.title, required this.children, this.foot});
  final String? title;
  final List<Widget> children;
  final String? foot;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        decoration: BoxDecoration(
          color: ColyvTokens.cSurface,
          borderRadius: BorderRadius.circular(ColyvTokens.rXl),
          boxShadow: const [BoxShadow(color: Color(0x1F101012), blurRadius: 28, offset: Offset(0, 12), spreadRadius: -16)],
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (title != null) Padding(padding: const EdgeInsets.only(top: 16, bottom: 6), child: Text(title!, style: Txt.title.copyWith(fontSize: 13))),
          for (var i = 0; i < children.length; i++) ...[
            if (i > 0) const Divider(height: 1, thickness: 1, color: ColyvTokens.cLine),
            children[i],
          ],
          if (foot != null) Padding(padding: const EdgeInsets.only(top: 6, bottom: 14), child: Text(foot!, style: Txt.small)) else const SizedBox(height: 6),
        ]),
      );
}

class RowLine extends StatelessWidget {
  const RowLine(this.label, this.value, {super.key});
  final String label;
  final Widget value;
  @override
  Widget build(BuildContext context) => SizedBox(
        height: 50,
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(label, style: Txt.body.copyWith(color: Txt.muted)), value]),
      );
}

class Tag extends StatelessWidget {
  const Tag(this.text, {super.key, this.dot});
  final String text;
  final Color? dot;
  @override
  Widget build(BuildContext context) => Container(
        height: 28,
        padding: const EdgeInsets.symmetric(horizontal: 11),
        decoration: BoxDecoration(color: ColyvTokens.cSurface, borderRadius: BorderRadius.circular(ColyvTokens.rPill), border: Border.all(color: ColyvTokens.cLine)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (dot != null) ...[Container(width: 7, height: 7, decoration: BoxDecoration(color: dot, shape: BoxShape.circle)), const SizedBox(width: 6)],
          Text(text, style: Txt.chip),
        ]),
      );
}

class PillButton extends StatelessWidget {
  const PillButton(this.text, {super.key, this.wide = false, this.onTap});
  final String text;
  final bool wide;
  final VoidCallback? onTap;
  @override
  Widget build(BuildContext context) => Press(
        scale: 0.96,
        onTap: onTap,
        child: Container(
          height: wide ? 54 : 46,
          width: wide ? double.infinity : null,
          padding: const EdgeInsets.symmetric(horizontal: 22),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: ColyvTokens.cAccent,
            borderRadius: BorderRadius.circular(ColyvTokens.rPill),
            boxShadow: [BoxShadow(color: ColyvTokens.cAccent.withValues(alpha: 0.35), blurRadius: 18, offset: const Offset(0, 8), spreadRadius: -8)],
          ),
          child: Text(text, style: const TextStyle(color: ColyvTokens.cOnAccent, fontSize: 14.5, fontWeight: FontWeight.w600)),
        ),
      );
}

/// Segmented control with one pill that slides to the chosen option.
class Seg extends StatelessWidget {
  const Seg({super.key, required this.options, required this.index, required this.onChanged});
  final List<String> options;
  final int index;
  final ValueChanged<int> onChanged;
  @override
  Widget build(BuildContext context) => Container(
        height: 46,
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(color: ColyvTokens.cSurfaceSunk, borderRadius: BorderRadius.circular(ColyvTokens.rPill)),
        child: Stack(children: [
          AnimatedAlign(
            duration: const Duration(milliseconds: 450),
            curve: ease,
            alignment: Alignment(-1 + 2 * index / (options.length - 1), 0),
            child: FractionallySizedBox(
              widthFactor: 1 / options.length,
              child: Container(decoration: BoxDecoration(color: ColyvTokens.cSurface, borderRadius: BorderRadius.circular(ColyvTokens.rPill), boxShadow: const [BoxShadow(color: Color(0x1F101012), blurRadius: 4, offset: Offset(0, 1))])),
            ),
          ),
          Row(children: [
            for (var i = 0; i < options.length; i++)
              Expanded(
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () => onChanged(i),
                  child: Center(child: AnimatedDefaultTextStyle(duration: const Duration(milliseconds: 250), style: TextStyle(fontFamily: 'Geist', fontSize: 12.5, fontWeight: FontWeight.w600, color: i == index ? Txt.ink : Txt.muted), child: Text(options[i]))),
                ),
              ),
          ]),
        ]),
      );
}

class DockItem {
  const DockItem(this.label, this.icon);
  final String label;
  final IconData icon;
}

/// The floating tab bar: frosted, with the current tab filled.
class Dock extends StatelessWidget {
  const Dock({super.key, required this.items, required this.index, this.onChanged});
  final List<DockItem> items;
  final int index;
  final ValueChanged<int>? onChanged;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(30),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
            child: Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.78), borderRadius: BorderRadius.circular(30), border: Border.all(color: const Color(0x0F101012))),
              child: Row(children: [
                for (var i = 0; i < items.length; i++)
                  Expanded(
                    child: Semantics(
                      button: true,
                      selected: i == index,
                      label: items[i].label,
                      child: GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTap: () => onChanged?.call(i),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 350),
                          curve: ease,
                          height: 54,
                          decoration: BoxDecoration(color: i == index ? ColyvTokens.cInk : Colors.transparent, borderRadius: BorderRadius.circular(24)),
                          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                            Icon(items[i].icon, size: 21, color: i == index ? Colors.white : Txt.muted),
                            const SizedBox(height: 2),
                            Text(items[i].label, maxLines: 1, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: i == index ? Colors.white : Txt.muted)),
                          ]),
                        ),
                      ),
                    ),
                  ),
              ]),
            ),
          ),
        ),
      );
}
