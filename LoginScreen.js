// --- START OF FILE LoginScreen.js ---

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator, // To show loading spinner
  SafeAreaView,     // To avoid notches/status bars
  Image             // To show the logo
} from 'react-native';
import { supabase } from './supabaseClient'; // Make sure this path is correct
import GradientButton from './GradientButton.js'; // Ensure this import is correct

export default function LoginScreen({ navigation }) { // navigation is passed by default
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState(''); // For displaying errors inline

  // --- Handle Login Attempt ---
  const handleLogin = async () => {
    setLoading(true);
    setErrorText(''); // Clear previous errors
    console.log('Attempting login for:', email);

    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: email.trim(), // Trim whitespace
        password: password,
      });

      console.log('Supabase login response:', { data, error });

      if (error) {
        // Specific check for unverified email if confirmation is required
        if (error.message.includes('Email not confirmed') || error.message.includes('confirm your email')) { // Added more specific error message checks
          setErrorText('Please verify your email first. Check your inbox.');
          Alert.alert(
            'Email Not Verified',
            'Please check your email inbox and click the confirmation link before logging in.'
          );
        } else if (error.message.includes('Invalid login credentials')) { // Common incorrect password/email error
             setErrorText('Invalid email or password.');
        }
        else {
          // For other errors (like rate limiting, internal server errors)
          setErrorText(`Login Failed: ${error.message}`);
          // Alert.alert('Login Failed', error.message); // Optional alert
        }
      } else if (!data.session) {
          // This case should be rare for password login but good to handle
          console.warn("Login succeeded but no session returned.", data);
          setErrorText('Login unsuccessful. Please try again.');
      } else {
        console.log('Login successful! App should navigate automatically via listener.');
        // **NO navigation.navigate HERE**
        // The onAuthStateChange listener in App.js handles navigation.
        // The loading state will turn off below, screen will change.
        // Success state is implicitly handled by the App component detecting the session.
      }
    } catch (catchError) {
      // Catch any unexpected errors during the process
      console.error('Login Catch Error:', catchError);
      const message = catchError.message || 'An unknown error occurred.';
      setErrorText(`Login Failed: ${message}`);
    } finally {
      setLoading(false); // Stop loading indicator regardless of outcome
    }
  };

  // --- Handle Sign Up Attempt ---
  const handleSignUp = async () => {
    setLoading(true);
    setErrorText('');
    console.log('Attempting signup for:', email);

    try {
      const { data, error } = await supabase.auth.signUp({
        email: email.trim(),
        password: password,
      });

      console.log('Supabase signup response:', { data, error });

      if (error) {
        // Common error: User already exists
        if (error.message.includes('User already registered') || error.message.includes('already an existing user')) {
           setErrorText('This email is already registered. Please Log In instead.');
        } else {
          setErrorText(`Sign Up Failed: ${error.message}`);
        }
         // Alert.alert('Signup Failed', error.message); // Optional alert
      } else {
        // Check if email confirmation is likely required by Supabase settings
        if (data.user && !data.session) {
          setErrorText('Verification email sent! Please check your inbox and click the link.');
          Alert.alert(
            'Sign Up Successful!',
            'Please check your email inbox to verify your account before logging in.'
          );
        } else if (data.session) {
          // Auto-logged in (email confirmation might be off)
          console.log("Signup successful and auto-logged in.");
          // Listener in App.js will handle this session.
           Alert.alert('Sign Up Successful!', 'You are now logged in.'); // Give feedback
        } else {
          // Other potential outcomes from Supabase? Should be rare.
          console.warn("Signup response needs inspection:", data);
          setErrorText('Signup initiated. Follow any instructions sent to your email.');
          // Alert.alert('Sign Up Initiated', 'Follow instructions sent to your email if any.');
        }
      }
    } catch (catchError) {
        console.error('Signup Catch Error:', catchError);
        const message = catchError.message || 'An unknown error occurred.';
        setErrorText(`Sign Up Failed: ${message}`);
    } finally {
      setLoading(false);
    }
  };

  // --- Render the Screen ---
  return (
    <SafeAreaView style={styles.containerSafeArea}>
      <View style={styles.container}>

        {/* App Logo */}
        <Image
          source={{ uri: 'https://placehold.co/120x120/0052cc/ffffff?text=Vedi%E2%9A%95%EF%B8%8F' }} // Logo with Stethoscope
          style={styles.logo}
          resizeMode="contain"
        />

        {/* App Title */}
        <Text style={styles.title}>Vedi</Text>

        {/* Email Input */}
        <TextInput
          placeholder="Email"
          value={email}
          onChangeText={setEmail}
          style={styles.input}
          keyboardType="email-address"
          autoCapitalize="none"
          placeholderTextColor="#9ca3af"
          autoComplete="email" // Helps with autofill
          textContentType="emailAddress" // iOS autofill
        />

        {/* Password Input */}
        <TextInput
          placeholder="Password"
          value={password}
          onChangeText={setPassword}
          style={styles.input}
          secureTextEntry // Hides password
          placeholderTextColor="#9ca3af"
          autoComplete="current-password" // Helps with autofill
          textContentType="password" // iOS autofill
        />

        {/* Display Error Text */}
        {errorText ? <Text style={styles.errorText}>{errorText}</Text> : null}

        {/* Show loading indicator OR buttons */}
        {loading ? (
          <ActivityIndicator size="large" color="#0052cc" style={styles.loader} />
        ) : (
          <>
            {/* Login Button */}
            <GradientButton // Use GradientButton component
               title="Log In"
               onPress={handleLogin}
               colors={['#0052cc', '#2684ff']} // Blue gradient
               style={(!email || !password) && styles.buttonDisabled} // Apply disabled style to GradientButton container
               disabled={!email || !password || loading} // Disable if no input or loading
            />

            {/* Sign Up Button */}
            <GradientButton // Use GradientButton component
              title="Sign Up"
              onPress={handleSignUp}
              colors={['#16a34a', '#22c55e']} // Green gradient
               style={(!email || !password) && styles.buttonDisabled} // Apply disabled style
              disabled={!email || !password || loading} // Disable if no input or loading
            />
          </>
        )}
      </View>
    </SafeAreaView>
  );
}

// --- Styles (Keeping the same styles as provided) ---
const styles = StyleSheet.create({
  containerSafeArea: {
    flex: 1,
    backgroundColor: '#f8fafc', // Light background for the whole screen
  },
  container: {
    flex: 1,
    justifyContent: 'center', // Center content vertically
    padding: 30,             // Padding around the content
  },
  logo: {
    width: 120,               // Logo size
    height: 120,
    alignSelf: 'center',      // Center the logo
    marginBottom: 20,         // Space below logo
  },
  title: {
    fontSize: 36,             // Larger title
    fontWeight: 'bold',
    marginBottom: 35,         // Space below title
    textAlign: 'center',
    color: '#1e3a8a',         // App theme color
  },
  input: {
    borderWidth: 1,
    borderColor: '#d1d5db',   // Input border color
    backgroundColor: '#ffffff', // White input background
    paddingVertical: 14,
    paddingHorizontal: 12,
    borderRadius: 8,          // Rounded corners
    marginBottom: 18,
    fontSize: 16,
    color: '#1f2937',         // Input text color
  },
  // Removed the old button styles and buttonDisabled style here,
  // as GradientButton handles its own styling and disabled state appearance.
  // The buttonDisabled style is kept above to apply to the *container* style
  // of the GradientButton to visually indicate disabled state if needed,
  // but GradientButton itself has opacity built-in.
  buttonDisabled: { // This style is applied to the container of GradientButton
    opacity: 0.6,
  },
  buttonText: { // This style is internal to GradientButton now
    color: 'white',
    fontWeight: 'bold',
    fontSize: 16,
  },
  errorText: {
    color: '#dc2626',         // Red error color
    textAlign: 'center',
    marginBottom: 15,         // Space below error message
    fontSize: 14,
    fontWeight: '500',
  },
  loader: {
    marginVertical: 20,       // Space around loading spinner
  }
});
// --- END OF FILE LoginScreen.js ---