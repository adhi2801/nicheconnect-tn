import 'package:flutter/material.dart';
import 'colyv_tokens.dart';
import 'screens.dart';
import 'theme.dart';
import 'widgets.dart';

void main() => runApp(const ColyvApp());

class ColyvApp extends StatelessWidget {
  const ColyvApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(title: 'Colyv', debugShowCheckedModeBanner: false, theme: colyvTheme(), home: const PreviewShell());
}

/// Preview shell: three screens to look at. The real app will start from sign-in and pick the role's tabs.
class PreviewShell extends StatefulWidget {
  const PreviewShell({super.key});
  @override
  State<PreviewShell> createState() => _PreviewShellState();
}

class _PreviewShellState extends State<PreviewShell> {
  int i = 0;
  static const creatorTabs = [DockItem('Today', Icons.home_outlined), DockItem('Discover', Icons.explore_outlined), DockItem('Deals', Icons.assignment_outlined), DockItem('Inbox', Icons.notifications_none), DockItem('Me', Icons.person_outline)];
  static const brandTabs = [DockItem('Today', Icons.home_outlined), DockItem('Campaigns', Icons.campaign_outlined), DockItem('Deals', Icons.assignment_outlined), DockItem('Inbox', Icons.notifications_none), DockItem('Me', Icons.person_outline)];
  static const names = ['Brand views a creator', "Creator's Today", 'Creator reads a brand'];

  Widget phone(bool framed) {
    final screens = const [CreatorProfile(), CreatorToday(), BrandCard()];
    final tabs = i == 0 ? brandTabs : creatorTabs;
    final cur = i == 0 ? 1 : (i == 1 ? 0 : 1);
    final body = Stack(children: [
      Positioned.fill(child: AnimatedSwitcher(duration: const Duration(milliseconds: 420), switchInCurve: ease, child: KeyedSubtree(key: ValueKey(i), child: screens[i]))),
      Positioned(left: 0, right: 0, bottom: 0, child: Dock(items: tabs, index: cur)),
    ]);
    if (!framed) return body;
    return Container(
      width: 390,
      height: 800,
      decoration: BoxDecoration(color: ColyvTokens.cGround, borderRadius: BorderRadius.circular(44), boxShadow: const [BoxShadow(color: Color(0x2E101012), blurRadius: 60, offset: Offset(0, 30), spreadRadius: -24)]),
      clipBehavior: Clip.antiAlias,
      child: body,
    );
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width > 640;
    return Scaffold(
      backgroundColor: wide ? const Color(0xFFE6E2DA) : ColyvTokens.cGround,
      body: SafeArea(
        child: wide
            ? Center(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  SizedBox(width: 390, child: Seg(options: const ['Brand view', 'Today', 'Brand card'], index: i, onChanged: (v) => setState(() => i = v))),
                  const SizedBox(height: 14),
                  phone(true),
                  const SizedBox(height: 10),
                  Text(names[i], style: Txt.caption),
                ]),
              )
            : Column(children: [
                Padding(padding: const EdgeInsets.fromLTRB(18, 8, 18, 0), child: Seg(options: const ['Brand view', 'Today', 'Brand card'], index: i, onChanged: (v) => setState(() => i = v))),
                Expanded(child: phone(false)),
              ]),
      ),
    );
  }
}
