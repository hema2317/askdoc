

export default {
  expo: {
    name: 'askdoc',
    slug: 'askdoc-mobile',
    version: '1.0.0',
    orientation: 'portrait',
    icon: './assets/icon.png',
    userInterfaceStyle: 'light',
    splash: {
      image: './assets/splash-icon.png',
      resizeMode: 'contain',
      backgroundColor: '#ffffff'
    },
    ios: {
      supportsTablet: true,
      bundleIdentifier: 'com.veda24.askdoc'
    },
    android: {
      adaptiveIcon: {
        foregroundImage: './assets/adaptive-icon.png',
        backgroundColor: '#ffffff'
      },
      package: 'com.veda24.askdoc'
    },
    web: {
      favicon: './assets/favicon.png'
    },
    extra: {
      // Access environment variables directly via process.env
      supabaseUrl: process.env.SUPABASE_URL,
      supabaseKey: process.env.SUPABASE_KEY,
      eas: {
        projectId: 'a02b4527-6bf5-4273-aeeb-4e2a9c05420b'
      }
    },
    // Removed the expo-build-properties plugin entry as discussed
    plugins: [
      // Keep other plugins here if you have any.
      // If this was the only plugin, the array should be empty.
      // Based on your original file, it seems this was the only one,
      // so the plugins array is now empty.
    ]
    // Removed the separate 'runtimeVersion', 'updates', 'assetBundlePatterns'
    // as these are typically defined inside the 'expo' block or are default EAS values.
    // Keeping the essential 'expo' block content.
    // If you need specific native configurations beyond name/slug/version, etc.,
    // they go under ios/android *within* the 'expo' block, as they are currently.
  }
};
