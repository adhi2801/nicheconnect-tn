import 'package:flutter/material.dart';
import 'colyv_tokens.dart';
import 'theme.dart';
import 'widgets.dart';

/// Every figure on these screens is sample data until the screens are wired to the API.
String _k(double v) {
  if (v >= 1e5) return '${(v / 1e3).round()}K';
  if (v >= 1e3) return '${(v / 1e3).toStringAsFixed(1)}K';
  return v.round().toString();
}

class Avatar extends StatelessWidget {
  const Avatar(this.initials, {super.key, this.square = false});
  final String initials;
  final bool square;
  @override
  Widget build(BuildContext context) => Container(
        width: 56,
        height: 56,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          shape: square ? BoxShape.rectangle : BoxShape.circle,
          borderRadius: square ? BorderRadius.circular(18) : null,
          gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: square ? const [ColyvTokens.cGlanceSandFrom, ColyvTokens.cGlanceSandTo] : const [ColyvTokens.cGlanceClayFrom, ColyvTokens.cGlanceTerracottaTo]),
          border: Border.all(color: ColyvTokens.cSurface, width: 3),
          boxShadow: const [BoxShadow(color: Color(0x1F101012), blurRadius: 14, offset: Offset(0, 6), spreadRadius: -6)],
        ),
        child: Text(initials, style: Txt.title.copyWith(fontSize: 16)),
      );
}

class _Page extends StatelessWidget {
  const _Page({required this.children});
  final List<Widget> children;
  @override
  Widget build(BuildContext context) => ListView(
        physics: const BouncingScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(18, 26, 18, 120),
        children: [for (var i = 0; i < children.length; i++) Padding(padding: const EdgeInsets.only(bottom: 16), child: Rise(delay: 70 * i, child: children[i]))],
      );
}

class _Two extends StatelessWidget {
  const _Two(this.a, this.b);
  final Widget a, b;
  @override
  Widget build(BuildContext context) => Row(children: [Expanded(child: a), const SizedBox(width: 12), Expanded(child: b)]);
}

class _Sample extends StatelessWidget {
  const _Sample();
  @override
  Widget build(BuildContext context) => const Padding(padding: EdgeInsets.only(left: 2), child: Text('Sample data', style: Txt.caption));
}

/// A brand reads a creator's connected Instagram numbers and Colyv delivery record.
class CreatorProfile extends StatefulWidget {
  const CreatorProfile({super.key});
  @override
  State<CreatorProfile> createState() => _CreatorProfileState();
}

class _CreatorProfileState extends State<CreatorProfile> {
  int p = 1;
  static const data = [
    (reach: 11400.0, views: 28900.0, eng: 3.8, chg: '+82 in 7 days', s1: [6.0, 5, 7, 6, 8, 7, 9], s2: [5.0, 6, 6, 8, 7, 9, 10]),
    (reach: 48200.0, views: 121000.0, eng: 4.1, chg: '+340 in 30 days', s1: [3.0, 4, 3, 5, 6, 5, 7, 6, 8, 7, 9, 10], s2: [5.0, 4, 6, 6, 5, 8, 7, 9, 8, 10, 9, 11]),
    (reach: 131000.0, views: 340000.0, eng: 4.4, chg: '+910 in 90 days', s1: [2.0, 3, 3, 4, 4, 5, 5, 6, 6, 7, 8, 8, 9, 10], s2: [3.0, 3, 4, 5, 5, 6, 7, 7, 8, 9, 9, 10, 11, 12]),
  ];
  @override
  Widget build(BuildContext context) {
    final d = data[p];
    return _Page(children: [
      const Row(children: [
        Avatar('DN'),
        SizedBox(width: 14),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('Display name', style: Txt.name), SizedBox(height: 2), Text('@handle · Madurai · Food, Lifestyle', style: Txt.small)])),
      ]),
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Flexible(child: Text.rich(TextSpan(style: Txt.small, children: [TextSpan(text: 'Instagram', style: Txt.small.copyWith(color: Txt.ink, fontWeight: FontWeight.w600)), const TextSpan(text: ', connected by the creator')]))),
        const SizedBox(width: 8),
        const Text('Updated 5 Oct', style: Txt.small),
      ]),
      Seg(options: const ['7 days', '30 days', '90 days'], index: p, onChanged: (i) => setState(() => p = i)),
      _Two(
        Glance(colors: GlanceColors.gold, label: 'Reach', value: CountNum(value: d.reach, format: _k, style: Txt.big), spark: Spark(data: d.s1)),
        Glance(colors: GlanceColors.terracotta, label: 'Views', value: CountNum(value: d.views, format: _k, style: Txt.big), spark: Spark(data: d.s2)),
      ),
      _Two(
        Glance(colors: GlanceColors.clay, label: 'Engagement', value: CountNum(value: d.eng, format: (v) => '${v.toStringAsFixed(1)}%', style: Txt.big), foot: 'interactions ÷ reach'),
        Glance(colors: GlanceColors.sand, label: 'Followers', value: const CountNum(value: 12400, format: _k, style: Txt.big), foot: d.chg),
      ),
      Panel(title: 'Recent posts', children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Row(children: [
            for (final t in const [('Reel · 22K', ColyvTokens.cGlanceGoldFrom, ColyvTokens.cGlanceGoldTo), ('Post · 6K', ColyvTokens.cGlanceClayFrom, ColyvTokens.cGlanceClayTo), ('Reel · 32K', ColyvTokens.cGlanceSandFrom, ColyvTokens.cGlanceSandTo)])
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: AspectRatio(
                    aspectRatio: 0.8,
                    child: Container(
                      padding: const EdgeInsets.all(8),
                      alignment: Alignment.bottomLeft,
                      decoration: BoxDecoration(borderRadius: BorderRadius.circular(14), gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [t.$2, t.$3])),
                      child: Text(t.$1, style: Txt.chip),
                    ),
                  ),
                ),
              ),
          ]),
        ),
      ]),
      Panel(title: 'Delivery on Colyv', foot: 'Counts shown with the deals behind them.', children: [
        RowLine('Deals delivered', const Text('8 of 9', style: Txt.num)),
        RowLine('On time', const Text('88%', style: Txt.num)),
        RowLine('Disclosure confirmed', const Text('8 of 8', style: Txt.num)),
      ]),
      const _Sample(),
    ]);
  }
}

/// A creator's morning list: what is waiting, most urgent first.
class CreatorToday extends StatelessWidget {
  const CreatorToday({super.key});
  Widget item(String title, Widget tag, String sub, String? amount, String action) => Press(
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: ColyvTokens.cSurface, borderRadius: BorderRadius.circular(ColyvTokens.rXl), boxShadow: const [BoxShadow(color: Color(0x1F101012), blurRadius: 28, offset: Offset(0, 12), spreadRadius: -16)]),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Flexible(child: Text(title, style: Txt.title.copyWith(fontSize: 15.5))), const SizedBox(width: 8), tag]),
            const SizedBox(height: 4),
            Text(sub, style: Txt.small),
            const SizedBox(height: 12),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, crossAxisAlignment: CrossAxisAlignment.center, children: [if (amount != null) Text(amount, style: Txt.mid) else const SizedBox(), PillButton(action)]),
          ]),
        ),
      );
  @override
  Widget build(BuildContext context) => _Page(children: [
        const Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('Good morning', style: Txt.small), Text('Display name', style: Txt.name)])),
          Tag('3 waiting', dot: ColyvTokens.cWarn),
        ]),
        const _Two(
          Glance(colors: GlanceColors.gold, label: 'To deliver', value: CountNum(value: 2, format: _k, style: Txt.big), foot: 'Reel 1 due 14 Oct', height: 128),
          Glance(colors: GlanceColors.terracotta, label: 'To confirm paid', value: CountNum(value: 1, format: _k, style: Txt.big), foot: '₹8,000 marked paid', height: 128),
        ),
        item('Confirm you were paid', const Tag('Late 3 days', dot: ColyvTokens.cWarn), 'Brand name · Campaign title', '₹8,000', 'Confirm'),
        item('Answer the deal memo', const Tag('2 days left'), 'Brand name · Campaign title', '₹6,500', 'Open memo'),
        item('Post and send the link', const Tag('Due 14 Oct'), 'Brand name · Reel 1 of 2', null, 'Send work'),
        const _Sample(),
      ]);
}

/// A creator reads a brand's payment record: counts, never a score.
class BrandCard extends StatelessWidget {
  const BrandCard({super.key});
  @override
  Widget build(BuildContext context) => _Page(children: [
        const Row(children: [
          Avatar('BN', square: true),
          SizedBox(width: 14),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('Brand name', style: Txt.name), SizedBox(height: 2), Text('On Colyv since Sep 2026', style: Txt.small)])),
        ]),
        const _Two(
          Glance(colors: GlanceColors.gold, label: 'Paid on time', value: Text('9 of 10', style: Txt.mid), foot: 'payments marked by the due date'),
          Glance(colors: GlanceColors.sand, label: 'Median to pay', value: Text('6 days', style: Txt.mid), foot: 'from approval of the work'),
        ),
        Panel(title: 'Behind the numbers', foot: 'Shown after three finished deals. Colyv records what the brand marked and when. It does not rate brands.', children: [
          RowLine('Deals finished', const Text('10', style: Txt.num)),
          RowLine('Overdue right now', const Text('0', style: Txt.num)),
        ]),
        Panel(title: 'Open campaigns', children: [
          RowLine('Campaign title', const Text('₹6,000 to ₹9,000', style: Txt.body)),
          RowLine('Campaign title', const Text('Barter', style: Txt.body)),
        ]),
        const PillButton('See campaigns', wide: true),
        const _Sample(),
      ]);
}
