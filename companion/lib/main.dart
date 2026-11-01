import 'package:flutter/widgets.dart';
import 'home.dart';

void main(List<String> args) {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(AfterglowApp(startDemo: args.contains('--demo')));
}
