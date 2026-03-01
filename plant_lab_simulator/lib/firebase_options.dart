// Firebase configuration — values are injected at build time via --dart-define.
// Run build_web.sh (which reads .env) instead of `flutter build web` directly.
//
// Required --dart-define keys:
//   FIREBASE_API_KEY
//   FIREBASE_APP_ID
//   FIREBASE_MESSAGING_SENDER_ID
//   FIREBASE_PROJECT_ID
//   FIREBASE_AUTH_DOMAIN
//   FIREBASE_STORAGE_BUCKET

import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) return web;
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      case TargetPlatform.macOS:
        return macos;
      default:
        return web;
    }
  }

  static const FirebaseOptions web = FirebaseOptions(
    apiKey:            String.fromEnvironment('FIREBASE_API_KEY'),
    appId:             String.fromEnvironment('FIREBASE_APP_ID'),
    messagingSenderId: String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID'),
    projectId:         String.fromEnvironment('FIREBASE_PROJECT_ID'),
    authDomain:        String.fromEnvironment('FIREBASE_AUTH_DOMAIN'),
    storageBucket:     String.fromEnvironment('FIREBASE_STORAGE_BUCKET'),
  );

  static const FirebaseOptions android = FirebaseOptions(
    apiKey:            String.fromEnvironment('FIREBASE_API_KEY'),
    appId:             String.fromEnvironment('FIREBASE_ANDROID_APP_ID'),
    messagingSenderId: String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID'),
    projectId:         String.fromEnvironment('FIREBASE_PROJECT_ID'),
    storageBucket:     String.fromEnvironment('FIREBASE_STORAGE_BUCKET'),
  );

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey:            String.fromEnvironment('FIREBASE_API_KEY'),
    appId:             String.fromEnvironment('FIREBASE_IOS_APP_ID'),
    messagingSenderId: String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID'),
    projectId:         String.fromEnvironment('FIREBASE_PROJECT_ID'),
    storageBucket:     String.fromEnvironment('FIREBASE_STORAGE_BUCKET'),
    iosBundleId:       String.fromEnvironment('FIREBASE_IOS_BUNDLE_ID',
                           defaultValue: 'com.example.plantLabSimulator'),
  );

  static const FirebaseOptions macos = FirebaseOptions(
    apiKey:            String.fromEnvironment('FIREBASE_API_KEY'),
    appId:             String.fromEnvironment('FIREBASE_IOS_APP_ID'),
    messagingSenderId: String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID'),
    projectId:         String.fromEnvironment('FIREBASE_PROJECT_ID'),
    storageBucket:     String.fromEnvironment('FIREBASE_STORAGE_BUCKET'),
    iosBundleId:       String.fromEnvironment('FIREBASE_IOS_BUNDLE_ID',
                           defaultValue: 'com.example.plantLabSimulator'),
  );
}
