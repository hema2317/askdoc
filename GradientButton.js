// --- START OF FILE GradientButton.js ---

import React from 'react';
import { TouchableOpacity, Text, StyleSheet, Dimensions, PixelRatio } from 'react-native';
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';

// --- Scaling Utilities ---
const { width } = Dimensions.get('window');
const scaleFont = (size) => PixelRatio.roundToNearestPixel(size * (width / 375));
const scaleSize = (size) => Math.min(size * (width / 375), size * 1.2);
// --- End Scaling Utilities ---

const GradientButton = ({ onPress, title, style, colors = ['#0052cc', '#2684ff'], disabled }) => {
  const scale = useSharedValue(1);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePressIn = () => {
    if (!disabled) scale.value = withSpring(0.95);
  };

  const handlePressOut = () => {
    if (!disabled) scale.value = withSpring(1);
  };

  // Use the first color for background or implement actual gradient library if needed
  const backgroundColor = disabled ? '#cccccc' : colors[0];

  return (
    <Animated.View style={[animatedStyle, style]}>
      <TouchableOpacity
        onPress={onPress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={disabled}
        activeOpacity={0.8}
        style={[
            styles.gradientButton,
            { backgroundColor: backgroundColor }, // Apply background color
            disabled && styles.buttonDisabled // Apply disabled style - Note: this style is not fully defined here but assumed from App.js
        ]}
      >
        <Text style={styles.buttonText}>{title}</Text>
      </TouchableOpacity>
    </Animated.View>
  );
};

// Define necessary styles directly in this file (these were missing in original snippet, adding them here)
const styles = StyleSheet.create({
    gradientButton: {
        paddingVertical: scaleSize(14),
        borderRadius: scaleSize(8),
        alignItems: 'center',
        justifyContent: 'center',
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.15,
        shadowRadius: 3.84,
        elevation: 3,
        minHeight: scaleSize(50), // Ensure a minimum height
      },
      buttonText: {
        color: '#ffffff',
        fontSize: scaleFont(16),
        fontWeight: '600',
      },
      buttonDisabled: {
        opacity: 0.6,
        shadowOpacity: 0,
        elevation: 0,
        backgroundColor: '#cccccc', // Ensure disabled background color overrides
      },
});

export default GradientButton;
// --- END OF FILE GradientButton.js ---