import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Dimensions,
  Image,
  Linking,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  FlatList,
  Modal,
  ActivityIndicator
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { NavigationContainer, useNavigation } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { createDrawerNavigator } from '@react-navigation/drawer';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaView, SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import * as Notifications from 'expo-notifications';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { supabase } from './supabaseClient'; // Assuming supabaseClient.js exists in the same directory
import * as FileSystem from 'expo-file-system';
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';
import { LinearGradient } from 'expo-linear-gradient';


// --- Navigation Initializers (Defined once) ---
const Stack = createStackNavigator();
const Drawer = createDrawerNavigator();
const Tab = createBottomTabNavigator();


// --- Global Constants (Defined once) ---
const { width, height } = Dimensions.get('window');

// API Endpoints (placeholders for backend integration)
// NOTE: These endpoints will not work as provided. They are placeholders.
const API_ENDPOINT = 'https://your-symptom-analyzer-endpoint.com/api/analyze'; // Mock endpoint
const API_ENDPOINT_LAB_REPORT = 'https://your-lab-report-endpoint.com/api/analyze'; // Mock endpoint


// --- Default Structures (Defined once) ---
const DEFAULT_PROFILE = {
  user_id: null,
  name: '',
  dob: null,
  gender: '',
  age: '',
  conditions: [],
  allergies: [],
  medications: [],
  medicalHistory: [],
  familyHistory: [],
  vaccinationHistory: '',
  bloodType: '',
  lifestyle: {
    smoker: false,
    alcohol: '',
    exercise: '',
    dietaryNotes: ''
  },
  biometrics: {
    height: '',
    weight: ''
  },
  emergencyContact: {
    name: '',
    relationship: '',
    phone: ''
  },
  state: ''
};


// --- Static Data (Defined once) ---
// Health Tips Data
const HEALTH_TIPS = [
  {
    id: 'tip-1',
    title: 'Stay Hydrated',
    summary: 'Drink at least 8 glasses of water daily to stay healthy.',
    content: 'Water is essential for maintaining bodily functions, including temperature regulation, digestion, and nutrient absorption. Aim to drink 8-10 glasses of water per day, and more if you are active or in a hot climate. Carry a reusable water bottle to remind yourself to hydrate throughout the day.'
  },
    {
    id: 'tip-2',
    title: 'Balanced Diet',
    summary: 'Eat a variety of fruits, vegetables, lean proteins, and whole grains.',
    content: 'A balanced diet provides the nutrients your body needs to function optimally. Focus on whole, unprocessed foods. Include plenty of colorful fruits and vegetables, lean protein sources (like chicken, fish, beans), whole grains (like oats, brown rice), and healthy fats (like avocados, nuts, olive oil). Limit sugary drinks, excessive saturated/trans fats, and highly processed foods.'
  },
  {
    id: 'tip-3',
    title: 'Regular Exercise',
    summary: 'Aim for at least 30 minutes of moderate exercise most days.',
    content: 'Physical activity is crucial for cardiovascular health, weight management, mental well-being, and overall fitness. Find activities you enjoy, whether it\'s walking, running, swimming, dancing, or team sports. Aim for at least 150 minutes of moderate-intensity aerobic activity or 75 minutes of vigorous-intensity activity per week, plus muscle-strengthening activities twice a week.'
  },
  {
    id: 'tip-4',
    title: 'Get Enough Sleep',
    summary: 'Most adults need 7-9 hours of quality sleep per night.',
    content: 'Sleep is vital for physical and mental restoration. Lack of sleep can impair concentration, mood, and immune function. Establish a regular sleep schedule, create a relaxing bedtime routine, ensure your bedroom is dark, quiet, and cool, and avoid caffeine and alcohol before bed. If you struggle with sleep, consult a doctor.'
  },
  {
    id: 'tip-5',
    title: 'Manage Stress',
    summary: 'Find healthy ways to cope with stress like meditation or hobbies.',
    content: 'Chronic stress can negatively impact your physical and mental health. Identify sources of stress in your life and develop healthy coping mechanisms. This could include mindfulness or meditation, deep breathing exercises, yoga, spending time in nature, pursuing hobbies, or talking to friends, family, or a therapist.'
  },
  {
    id: 'tip-6',
    title: 'Regular Check-ups',
    summary: 'Visit your doctor for preventive care and screenings.',
    content: 'Preventive care and regular medical check-ups are essential for detecting potential health problems early, managing chronic conditions, and staying up-to-date on vaccinations and screenings appropriate for your age and health history. Don\'t wait until you\'re sick to see a doctor.'
  },
  {
    id: 'tip-7',
    title: 'Practice Good Hygiene',
    summary: 'Wash hands frequently and cover coughs/sneezes.',
    content: 'Good personal hygiene habits are crucial for preventing the spread of infections. Wash your hands frequently with soap and water for at least 20 seconds, especially before eating and after using the restroom, coughing, or sneezing. Cover your mouth and nose with a tissue or your elbow when you cough or sneeze.'
  },
  {
    id: 'tip-8',
    title: 'Limit Processed Foods',
    summary: 'Reduce intake of sugary, fatty, and salty processed foods.',
    content: 'Processed foods often contain high levels of unhealthy fats, sugar, salt, and artificial additives while being low in essential nutrients and fiber. Regularly consuming these foods can contribute to weight gain, heart disease, diabetes, and other health problems. Prioritize whole, unprocessed foods whenever possible.'
  },
  {
    id: 'tip-9',
    title: 'Maintain Social Connections',
    summary: 'Stay connected with friends and family for emotional well-being.',
    content: 'Strong social connections are linked to better mental and physical health. Spend time with loved ones, participate in community activities, or volunteer. Having a support system can help reduce stress, improve mood, and provide a sense of belonging.'
  },
  {
    id: 'tip-10',
    title: 'Know Your Numbers',
    summary: 'Monitor blood pressure, cholesterol, and blood sugar.',
    content: 'Being aware of key health indicators like blood pressure, cholesterol levels, blood sugar, and body mass index (BMI) can help you understand your risk for certain chronic diseases. Discuss these numbers with your doctor and follow their recommendations for managing them.'
  }
];


// --- Utility Functions (Defined once) ---

// Function to scale fonts based on screen width
const guidelineBaseWidth = 375; // Example base width for scaling
const scaleFont = (size) => {
  const newSize = (size * width) / guidelineBaseWidth;
  return Math.round(newSize);
};

// Function to scale sizes (padding, margins, etc.) based on screen width
const scaleSize = (size) => {
  const newSize = (size * width) / guidelineBaseWidth;
  return Math.round(newSize);
};

// Function to get descriptive text for health risks based on type and level
const getRiskDescription = (type, level) => {
  const riskDescriptions = {
    cardiac: {
      low: "Your cardiac risk is low. Maintain a healthy lifestyle with regular exercise and a balanced diet to keep your heart in good shape.",
      medium: "You have a moderate cardiac risk. Consider consulting a doctor for a check-up, and focus on heart-healthy habits like reducing salt intake and staying active.",
      high: "High cardiac risk detected. Please consult a cardiologist as soon as possible for a detailed evaluation and to discuss preventive measures."
    },
    diabetic: {
      low: "Your diabetic risk is low. Continue monitoring your sugar intake and maintain an active lifestyle to prevent future issues.",
      medium: "Moderate diabetic risk. Monitor your blood sugar levels regularly and consult a doctor for advice on diet and lifestyle changes.",
      high: "High diabetic risk. Please see a doctor immediately to discuss testing for diabetes and managing your blood sugar levels."
    }
  };
  // Return the specific description or a default message
  return riskDescriptions[type]?.[level] || `No specific recommendations available for ${type} risk at ${level} level. Consult a healthcare provider.`;
};

// Function to request notification permissions from the user
const requestNotificationPermissions = async () => {
  try {
    // Check existing permissions
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    // If permissions are not granted, request them
    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync({
        // Specify permissions needed for iOS
        ios: {
          allowAlert: true,
          allowBadge: true,
          allowSound: true,
          allowAnnouncements: true
        }
      });
      finalStatus = status;
    }

    // If permissions are still not granted, warn and return false
    if (finalStatus !== 'granted') {
      console.warn("Notification permissions not granted:", finalStatus);
      // Optionally show an alert to the user asking them to go to settings
      // Alert.alert("Permissions Needed", "Please enable notifications in your device settings for reminders.");
      return false;
    }

    // For Android, set up a notification channel (important for delivery)
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: 'default',
        importance: Notifications.AndroidImportance.MAX, // High importance to ensure visibility
        vibrationPattern: [0, 250, 250, 250], // Vibration pattern
        lightColor: '#FF231F7C' // Light color for the notification LED (if supported)
      }).catch(err => console.error("Failed to set notification channel:", err)); // Catch potential errors
    }

    // If permissions are granted and channel is set (Android), return true
    return true;
  } catch (error) {
    // Catch any errors during the permission process
    console.error("Error requesting notification permissions:", error);
    return false;
  }
};

// Reusable Gradient Button component
const GradientButton = ({ title, onPress, colors = ['#0052cc', '#2684ff'], disabled = false, style }) => (
  <TouchableOpacity
    onPress={onPress}
    disabled={disabled}
    style={[styles.gradientButton, style, disabled && styles.disabledButton]}
    activeOpacity={0.8} // Slightly reduce opacity on press
  >
    <LinearGradient
      // Use grey colors when disabled, otherwise use provided colors
      colors={disabled ? ['#d1d5db', '#d1d5db'] : colors}
      start={{ x: 0, y: 0 }} // Gradient starts from left
      end={{ x: 1, y: 0 }} // Gradient ends to the right
      style={styles.gradient} // Apply gradient styles
    >
      <Text style={styles.buttonText}>{title}</Text> {/* Button text */}
    </LinearGradient>
  </TouchableOpacity>
);

// Reusable Doctor Card component for displaying doctor information
const DoctorCard = ({ doctor }) => (
  <View style={styles.doctorCard}> {/* Container for the doctor card */}
    <Text style={styles.doctorName}>{doctor.name}</Text> {/* Doctor's name */}
    <Text style={styles.doctorText}>📍 {doctor.address}</Text> {/* Doctor's address */}
    {doctor.rating && ( // Display rating only if available
      <Text style={styles.doctorText}>⭐ Rating: {doctor.rating}/5</Text>
    )}
    {doctor.phone && ( // Display phone only if available
      <Text style={styles.doctorText}>📞 {doctor.phone}</Text>
    )}
  </View>
);

// Placeholder function for taking a photo (not implemented in web simulator)
const takePhoto = () => {
   Alert.alert("Camera Feature", "Camera capture is not supported in this environment. Please use the 'Upload Image' option instead.");
   // In a real app on a native device, you would use expo-image-picker's launchCameraAsync here
   // const { status } = await ImagePicker.requestCameraPermissionsAsync();
   // if (status !== 'granted') { ... }
   // const result = await ImagePicker.launchCameraAsync({...});
   // if (!result.canceled) { processImage(result.assets[0].uri); }
};

// --- Analysis Modal Component (shared between Chat and History screens) ---
// Displays detailed analysis results (symptom or lab report) and nearby doctors.
const AnalysisModal = ({ visible, onClose, response, doctors, specialty, isLoadingDoctors = false }) => {
  // Shared value for Reanimated animation (slides modal up from bottom)
  const translateY = useSharedValue(height);

  // Effect to animate the modal position when its visibility changes
  useEffect(() => {
    // Animate modal to 0 (visible) or height (hidden) using spring animation
    translateY.value = withSpring(visible ? 0 : height, { damping: 15, stiffness: 100 });
  }, [visible, translateY]); // Dependencies: Re-run animation when visible state or translateY value changes

  // Animated style object based on the translateY shared value
  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: translateY.value }] // Apply the animated translateY transform
  }));

  // Function to save the analysis results to a text file
  const saveAnalysis = async () => {
    if (!response) {
      Alert.alert('Error', 'No analysis data to save.');
      return;
    }
    // Generate a filename with timestamp and analysis type
    const timestamp = new Date().toISOString().replace(/:/g, '-').split('.')[0];
    const filename = `HealthAnalysis_${response.type || 'Analysis'}_${timestamp}.txt`;

    // Construct the content of the text file based on the analysis type (lab report or symptom)
    const content = response.type === 'lab_report'
      ? `
Lab Report Analysis
Date: ${new Date().toLocaleString()}

Overview:
${response.medical_analysis || 'Not provided'}

Good Results:
${response.good_results?.length > 0 ? response.good_results.map((r) => `- ${r.test}: ${r.value} (${r.explanation})`).join('\n') : 'None identified'}

Bad Results:
${response.bad_results?.length > 0 ? response.bad_results.map((r) => `- ${r.test}: ${r.value} (${r.explanation}, Possible cause: ${r.potential_cause || 'N/A'})`).join('\n') : 'None identified'}

Actionable Advice:
${response.actionable_advice?.length > 0 ? response.actionable_advice.map((a) => `- ${a}`).join('\n') : 'None provided'}

Urgency Level: ${response.urgency || 'Not specified'}

Suggested Specialist: ${response.suggested_doctor || 'Not specified'}

${specialty ? `Doctors Searched For: ${specialty}` : ''}
Doctors Nearby:
${isLoadingDoctors ? 'Loading doctors...' : doctors.length > 0 ? doctors.map((doc) => `${doc.name}\n${doc.address}\nRating: ${doc.rating || 'N/A'}${doc.phone ? `\nPhone: ${doc.phone}` : ''}`).join('\n\n') : 'None found'}
`.trim()
      : `
Medical Analysis Report (Symptoms)
Date: ${new Date().toLocaleString()}

Symptoms/Query:
${response.query || response.symptoms || 'Not provided'}

Detailed Medical Analysis:
${response.medical_analysis || 'Not provided'}

${response.root_cause ? `Potential Underlying Causes:\n${response.root_cause}` : ''}

${response.remedies?.length > 0 ? `Personalized Suggestions & Remedies:\n${response.remedies.map((r) => `- ${r}`).join('\n')}` : 'None provided'}

${response.urgency ? `Urgency Level: ${response.urgency}` : 'Not specified'}

${response.medicines?.length > 0 ? `Potential Medications Mentioned:\n${response.medicines.map((m) => `- ${m}`).join('\n')}` : 'None mentioned'}

${response.health_risks?.length > 0 ? `Health Risk Assessment:\n${response.health_risks.map((risk) => `${risk.type.toUpperCase()} RISK (${risk.level})
${getRiskDescription(risk.type, risk.level)}`).join('\n\n')}` : 'None assessed'}

${response.suggested_doctor ? `Suggested Specialist: ${response.suggested_doctor}` : 'Not specified'}

${specialty ? `Doctors Searched For: ${specialty}` : ''}
Doctors Nearby:
${isLoadingDoctors ? 'Loading doctors...' : doctors.length > 0 ? doctors.map((doc) => `${doc.name}\n${doc.address}\nRating: ${doc.rating || 'N/A'}${doc.phone ? `\nPhone: ${doc.phone}` : ''}`).join('\n\n') : 'None found'}
`.trim();

    try {
      // Save logic differs for web and native platforms
      if (Platform.OS === 'web') {
        // Web: Create a Blob and a download link
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob); // Create a URL for the blob
        const a = document.createElement('a'); // Create a temporary anchor element
        a.href = url; // Set the URL as the link destination
        a.download = filename; // Set the download filename
        document.body.appendChild(a); // Append to body
        a.click(); // Programmatically click the link to trigger download
        document.body.removeChild(a); // Remove the temporary element
        URL.revokeObjectURL(url); // Release the object URL
        Alert.alert('Success', `Analysis saved as ${filename}`); // Alert user
      } else {
        // Native: Save to the app's document directory using expo-file-system
        const directoryUri = FileSystem.documentDirectory || FileSystem.cacheDirectory; // Get a writable directory URI
         if (!directoryUri) {
            Alert.alert('Error', 'Could not access storage directory.');
            return; // Exit if directory is not available
         }
        const fileUri = `${directoryUri}${filename}`; // Construct the full file URI
        await FileSystem.writeAsStringAsync(fileUri, content, { encoding: FileSystem.EncodingType.UTF8 }); // Write the content to the file
        Alert.alert('Success', `Analysis saved to device storage.`); // Alert user
         // On native, you might want to offer sharing the file using expo-sharing
      }
    } catch (error) {
      // Catch and log any errors during the save process
      console.error('Save Analysis Error:', error);
      Alert.alert('Error', `Failed to save analysis: ${error.message || error}`); // Alert user about the error
    }
  };


  // Function to open a map search for the suggested doctor/specialty
  const openMapSearch = () => {
    // Use the suggested doctor specialty from the response or the explicitly passed specialty
    const searchSpecialty = response?.suggested_doctor || specialty;
    if (searchSpecialty) {
      // Encode the search query for a Google Maps URL
      const query = encodeURIComponent(`${searchSpecialty} doctor near me`);
      // Open Google Maps app or website with the search query
      Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${query}`);
    } else {
      // Alert if no specific specialty was suggested
      Alert.alert("No Specialty", "No specific doctor specialty was suggested for map search.");
    }
  };


  return (
    // Modal component to render the content as a modal overlay
    <Modal
      visible={visible} // Controlled by the 'visible' prop
      animationType="none" // Disable default animation as Reanimated handles it
      transparent // Make the modal background transparent to show content underneath
      onRequestClose={onClose} // Call onClose function when the user requests to close (e.g., back button on Android)
    >
      {/* SafeAreaView for the semi-transparent background, respecting top safe area */}
      <SafeAreaView style={styles.modalSafeArea} edges={['top']}>
         {/* Animated.View applies the sliding animation */}
        <Animated.View style={[styles.modalContainer, animatedStyle]}>
           {/* Modal Header */}
          <View style={styles.modalHeader}>
             {/* Close button */}
            <TouchableOpacity
              onPress={onClose} // Call onClose function on press
              style={styles.modalCloseButton}
              hitSlop={{ top: 20, bottom: 20, left: 20, right: 20 }} // Increase touch area
              accessibilityLabel="Close modal" // Accessibility label for screen readers
            >
              <Ionicons name="close" size={scaleFont(28)} color="#0052cc" /> {/* Close icon */}
            </TouchableOpacity>
            {/* Modal Title */}
            <Text style={styles.modalTitle} numberOfLines={1} ellipsizeMode="tail">
              {/* Title text changes based on the type of analysis displayed */}
              {response?.type === 'lab_report' ? 'Lab Report Analysis' : 'Medical Analysis'}
            </Text>
            {/* Placeholder View to balance the close button and center the title */}
            <View style={styles.menuButtonPlaceholder} /> {/* Reusing placeholder width style */}
          </View>

           {/* ScrollView for the modal content */}
          <ScrollView
            style={styles.modalScrollView} // Styles for the ScrollView itself
            contentContainerStyle={styles.modalContent} // Styles for the content inside the ScrollView
            showsVerticalScrollIndicator={true} // Show vertical scroll indicator
          >
            {/* Conditional rendering based on whether analysis response data is available */}
            {response ? (
               // Conditional rendering based on the type of analysis
              response.type === 'lab_report' ? (
                // --- Display for Lab Report Analysis ---
                <>
                  <Text style={styles.label}>📝 Summary:</Text>
                  <Text style={styles.textBlock}>{response.medical_analysis || 'Not provided'}</Text>

                  {response.good_results?.length > 0 && (
                    <>
                      <Text style={styles.label}>✅ Good Results:</Text>
                      {response.good_results.map((result, i) => (
                        <Text key={`good-${i}`} style={styles.textBlock}>
                          • {result.test}: {result.value} - {result.explanation}
                        </Text>
                      ))}
                    </>
                  )}
                  {response.bad_results?.length > 0 && (
                    <>
                      <Text style={styles.label}>⚠️ Abnormal Results:</Text>
                      {response.bad_results.map((result, i) => (
                        <Text key={`bad-${i}`} style={[styles.textBlock, { color: '#b91c1c' }]}>
                          • {result.test}: {result.value} - {result.explanation} (Potential cause: {result.potential_cause || 'N/A'})
                        </Text>
                      ))}
                    </>
                  )}
                  {response.actionable_advice?.length > 0 && (
                    <>
                      <Text style={styles.label}>🩺 Actionable Advice:</Text>
                      {response.actionable_advice.map((advice, i) => (
                        <Text key={`advice-${i}`} style={styles.textBlock}>• {advice}</Text>
                      ))}
                    </>
                  )}
                  {response.urgency && (
                    <Text
                      style={[
                        styles.textBlock,
                        styles.urgencyLabel,
                         // Apply emergency text style if urgency indicates high or urgent need
                        (response.urgency.toLowerCase().includes('high') || response.urgency.toLowerCase().includes('urgent')) && styles.emergencyText
                      ]}
                    >
                      Urgency Level: {response.urgency}
                    </Text>
                  )}
                  {response.suggested_doctor && (
                    <>
                      <Text style={styles.label}>👨‍⚕️ Suggested Specialist:</Text>
                      <Text style={styles.textBlock}>{response.suggested_doctor}</Text>
                    </>
                  )}
                  {/* Doctors Section */}
                  <Text style={styles.label}>📍 Doctors Nearby {specialty ? `(${specialty})` : ''}:</Text>
                  {isLoadingDoctors ? (
                    <ActivityIndicator size="small" color="#0052cc" style={{ marginVertical: scaleSize(20) }} />
                  ) : doctors.length > 0 ? (
                    doctors.map((doc, i) => <DoctorCard key={`doc-${i}`} doctor={doc} />)
                  ) : (
                    <View style={styles.noDoctorsContainer}>
                      <Text style={styles.textBlock}>
                        No highly-rated doctors found nearby. You can try searching on Google Maps directly.
                      </Text>
                       <GradientButton
                          title={`Search for ${specialty || 'Doctors'} on Maps`}
                          onPress={openMapSearch} // Call the map search function
                          colors={['#0052cc', '#2684ff']}
                           // Disable the button if no specialty is available
                          disabled={!specialty && !response?.suggested_doctor}
                          style={{ marginTop: scaleSize(15) }}
                      />
                    </View>
                  )}
                </>
              ) : (
                 // --- Display for Symptom Analysis ---
                 <>
                  <Text style={styles.label}>📝 Your Query:</Text>
                  <Text style={styles.textBlock}>{response.query || response.symptoms || 'Not provided'}</Text> {/* Show the original query */}
                  <Text style={styles.label}>🧠 Detailed Medical Analysis:</Text>
                  <Text style={styles.textBlock}>{response.medical_analysis || 'Not provided'}</Text>
                  {response.root_cause && (
                    <>
                      <Text style={styles.label}>🧩 Potential Underlying Causes:</Text>
                      <Text style={styles.textBlock}>{response.root_cause}</Text>
                    </>
                  )}
                  {response.remedies?.length > 0 && (
                    <>
                      <Text style={styles.label}>💡 Personalized Suggestions & Remedies:</Text>
                      {response.remedies.map((r, i) => (
                        <Text key={`remedy-${i}`} style={styles.textBlock}>• {r}</Text>
                      ))}
                    </>
                  )}
                  {response.urgency && (
                    <Text
                      style={[
                        styles.textBlock,
                        styles.urgencyLabel,
                        (response.urgency.toLowerCase().includes('high') || response.urgency.toLowerCase().includes('urgent')) && styles.emergencyText
                      ]}
                    >
                      Urgency Level: {response.urgency}
                    </Text>
                  )}
                  {response.medicines?.length > 0 && (
                    <>
                      <Text style={styles.label}>💊 Potential Medications Mentioned:</Text>
                      <Text style={[styles.textBlock, { fontStyle: 'italic', fontSize: scaleFont(14), color: '#475569' }]}>
                        (Note: This is not a prescription. Discuss any medication with your doctor.)
                      </Text>
                      {response.medicines.map((m, i) => (
                        <Text key={`med-${i}`} style={styles.textBlock}>• {m}</Text>
                      ))}
                    </>
                  )}
                  {response.health_risks?.length > 0 && (
                    <>
                      <Text style={styles.healthRiskLabel}>🔍 Health Risk Assessment:</Text>
                      {response.health_risks.map((risk, i) => (
                        <View
                          key={`risk-${i}`}
                          style={[styles.healthRiskCard, { backgroundColor: '#fef3c7' }]}
                        >
                          <Text style={styles.healthRiskTitle}>
                            {risk.type.toUpperCase()} RISK ({risk.level})
                          </Text>
                          <Text style={styles.healthRiskText}>
                            {getRiskDescription(risk.type, risk.level)}
                          </Text>
                        </View>
                      ))}
                    </>
                  )}
                  {response.suggested_doctor && (
                    <>
                      <Text style={styles.label}>👨‍⚕️ Suggested Specialist:</Text>
                      <Text style={styles.textBlock}>{response.suggested_doctor}</Text>
                    </>
                  )}
                   {/* Doctors Section */}
                  <Text style={styles.label}>📍 Doctors Nearby {specialty ? `(${specialty})` : ''}:</Text>
                  {isLoadingDoctors ? (
                    <ActivityIndicator size="small" color="#0052cc" style={{ marginVertical: scaleSize(20) }} />
                  ) : doctors.length > 0 ? (
                    doctors.map((doc, i) => <DoctorCard key={`doc-${i}`} doctor={doc} />)
                  ) : (
                    <View style={styles.noDoctorsContainer}>
                      <Text style={styles.textBlock}>
                        No highly-rated doctors found nearby. You can try searching on Google Maps directly.
                      </Text>
                      <GradientButton
                        title={`Search for ${specialty || 'Doctors'} on Maps`}
                        onPress={openMapSearch}
                        colors={['#0052cc', '#2684ff']}
                        disabled={!specialty && !response?.suggested_doctor}
                        style={{ marginTop: scaleSize(15) }}
                      />
                    </View>
                  )}
                </>
              )
            ) : (
               // Message displayed if no analysis data is available in the response
              <Text style={styles.textBlock}>No analysis data available.</Text>
            )}
            {/* Save Button - Only show if there's actual meaningful analysis content */}
            {(response && (response.medical_analysis || response.bad_results?.length > 0 || response.remedies?.length > 0 || response.health_risks?.length > 0)) && (
               <GradientButton
                 title="Save Analysis to File"
                 onPress={saveAnalysis} // Call the save function
                 colors={['#16a34a', '#22c55e']} // Green gradient
                 style={{ marginTop: scaleSize(20) }}
               />
            )}
          </ScrollView>
        </Animated.View>
      </SafeAreaView>
    </Modal>
  );
};


// --- Part 2: Main Screen Components (Defined once) ---

// Chat Screen (Symptom Analyzer / Home Tab)
const ChatScreen = ({ profile, history, setHistory, chatMedications, setChatMedications, route, navigation }) => {
  const [inputText, setInputText] = useState(''); // State for symptom input text
  const [isLoading, setIsLoading] = useState(false); // Loading state for analysis (symptoms or lab report)
  const [modalVisible, setModalVisible] = useState(false); // State for the analysis modal visibility
  const [analysisResponse, setAnalysisResponse] = useState(null); // State to hold the analysis results for the modal
  const [doctors, setDoctors] = useState([]); // State to hold the list of doctors for the modal
  const [isLoadingDoctors, setIsLoadingDoctors] = useState(false); // Loading state for fetching doctors
  const [imageUri, setImageUri] = useState(null); // State to hold the selected image URI for preview

  // Memoized function to fetch doctors (mocked)
  const fetchDoctors = useCallback(async (specialty, userLocation) => {
    if (!specialty) {
      setDoctors([]);
      setIsLoadingDoctors(false);
      return;
    }
    setIsLoadingDoctors(true);
    setDoctors([]); // Clear previous doctors list

    console.log(`ChatScreen: Fetching doctors for specialty: ${specialty}`);

    try {
      console.warn("ChatScreen: Using MOCK Doctor Search Call! Replace with actual backend endpoint/API.");
      // Simulate network delay for the API call
      await new Promise(resolve => setTimeout(resolve, 1500));

      // Mock data simulating a response from a doctor search API
      const simulatedDoctors = [
        { name: `Simulated Dr. ${specialty} One`, address: '123 Mock Medical St, Anytown', rating: 4.5, phone: '555-1111' },
        { name: `Simulated Dr. ${specialty} Two`, address: '456 Fake Health Ave, Anytown', rating: 4.8, phone: '555-2222' }
        // Add more mock doctors if needed
      ];
      console.log('ChatScreen: Simulated doctors fetched:', simulatedDoctors);
      setDoctors(simulatedDoctors);
    } catch (error) {
      console.error('ChatScreen: Error fetching doctors (simulated):', error);
      // Set doctors to empty array and show an alert on error
      setDoctors([]);
      Alert.alert('Error', 'Could not fetch nearby doctors.');
    } finally {
      setIsLoadingDoctors(false); // Always turn off loading state
    }
  }, []); // Dependencies array for useCallback - add userLocation if it's used in the future

  // Effect to handle incoming navigation parameters, specifically for showing an analysis modal
  // This is used when navigating from the History screen to view a past analysis result.
  useEffect(() => {
    // Check if 'showAnalysis' params exist and are different from the current analysis in state
    // Adding analysisResponse check to prevent re-triggering the modal if the component re-renders
    // with the same params before the modal is closed and params are cleared.
    if (route.params?.showAnalysis && JSON.stringify(route.params.showAnalysis.response) !== JSON.stringify(analysisResponse)) {
      const { response: analysisResp, doctors: analysisDoctors, specialty: analysisSpecialty } = route.params.showAnalysis;

      console.log("ChatScreen: Received showAnalysis params:", route.params.showAnalysis);

      setAnalysisResponse(analysisResp);

      // Handle doctors data: use provided doctors if available, otherwise fetch if specialty is provided
      if (analysisDoctors && analysisDoctors.length > 0) {
        setDoctors(analysisDoctors);
        setIsLoadingDoctors(false); // Assume provided doctors are fully loaded
      } else if (analysisSpecialty) {
        // Fetch doctors based on the suggested specialty
        fetchDoctors(analysisSpecialty, null); // Pass user location if available/needed
      } else {
        setDoctors([]); // No doctors provided and no specialty to search
        setIsLoadingDoctors(false);
      }

      setModalVisible(true); // Show the analysis modal

      // Use a timeout to clear the navigation params shortly after processing them.
      // This prevents the modal from reappearing if you navigate back to this screen.
      const timer = setTimeout(() => {
        // Check if the screen is still focused before clearing params to avoid issues
        // if the user navigates away quickly.
        if (navigation.isFocused()) {
           console.log("ChatScreen: Clearing showAnalysis navigation params.");
           navigation.setParams({ showAnalysis: undefined }); // Use undefined to clear the param
        }
      }, 10); // A very short delay is usually sufficient

      // Cleanup function to clear the timeout if the component unmounts or the effect re-runs
      return () => clearTimeout(timer);
    } else if (route.params?.showAnalysis && JSON.stringify(route.params.showAnalysis.response) === JSON.stringify(analysisResponse)) {
       // If params exist but match the current state, it might be a re-render. Clear params.
       console.log("ChatScreen: showAnalysis params match current state, clearing params.");
       const timer = setTimeout(() => {
         if (navigation.isFocused()) {
            navigation.setParams({ showAnalysis: undefined });
         }
       }, 10);
       return () => clearTimeout(timer);
    }
     // If no route.params?.showAnalysis, do nothing.
  }, [route.params?.showAnalysis, navigation, fetchDoctors, analysisResponse]); // Include analysisResponse in dependencies


    // --- Lab Report Analysis Logic ---
   const pickLabReportImage = async () => {
     setImageUri(null); // Clear any previously selected image
     const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync(); // Request media library permissions
     if (status !== 'granted') {
       Alert.alert('Permission Required', 'Please allow access to your photo library to upload lab reports.');
       return;
     }
     try {
       const result = await ImagePicker.launchImageLibraryAsync({ // Launch the image picker
         mediaTypes: ImagePicker.MediaTypeOptions.Images, // Only allow images
         allowsEditing: false, // Set to true if you want cropping
         base64: true, // Request base64 data, which is needed for many APIs
         quality: 0.7 // Compress image quality to reduce size (0 to 1)
       });

       // Check if the user cancelled the picker or if assets were not selected
       if (!result.canceled && result.assets && result.assets.length > 0) {
         const selectedAsset = result.assets[0];
         setImageUri(selectedAsset.uri); // Set the URI for displaying a preview

         // Ensure base64 data is available before attempting to process
         if (selectedAsset.base64) {
             processLabReportImage(selectedAsset.base64); // Process the image using base64 data
         } else {
             // Alert if base64 data is missing
             Alert.alert('Error', 'Could not get image data. Please try again.');
             setImageUri(null); // Clear the preview if data is bad
         }
       } else {
          console.log("ChatScreen: Image picking cancelled or no asset selected.");
       }
     } catch (error) {
       // Catch and log any errors during the image picking process
       console.error("ChatScreen: Image picker error:", error);
       Alert.alert('Error', `Could not select image: ${error.message || error}`);
       setImageUri(null); // Clear preview on error
     }
   };

   // Function to send lab report image data (base64) to the backend API for analysis
   const processLabReportImage = async (base64Data) => {
     if (!base64Data) {
       Alert.alert('Error', 'No image data to process.');
       setImageUri(null); // Clear preview
       return;
     }
     setIsLoading(true); // Set loading state
     setAnalysisResponse(null); // Clear previous results
     setDoctors([]);
     setIsLoadingDoctors(false);

     try {
       console.log("ChatScreen: Sending lab report image for analysis to backend...");
       const payload = {
         image_base64: base64Data,
         // Include user profile data for personalized analysis if needed by the backend
         profile: profile || DEFAULT_PROFILE
         // Add other relevant data like user ID, location, etc.
       };

       // --- Replace with actual fetch to API_ENDPOINT_LAB_REPORT when integrating backend ---
       console.warn("ChatScreen: Using MOCK Lab Report API Call! Replace with actual backend endpoint.");
       await new Promise(resolve => setTimeout(resolve, 3000)); // Simulate API delay

       // Mock response data structure
       const mockResponseData = {
          interpretation: {
              summary: "Analysis of your lab report indicates a few markers are outside the normal range, potentially suggesting a mild inflammatory response. Your cholesterol levels are within acceptable limits.",
              good_results: [
                  { test: "Total Cholesterol", value: "180 mg/dL", explanation: "Normal range" },
                  { test: "Glucose (Fasting)", value: "95 mg/dL", explanation: "Within normal limits" }
              ],
              bad_results: [
                  { test: "C-Reactive Protein (CRP)", value: "8 mg/L", explanation: "Elevated", potential_cause: "Inflammation or infection" },
                  { test: "Vitamin D", value: "25 ng/mL", explanation: "Slightly low", potential_cause: "Insufficient sun exposure or dietary intake" }
              ],
              actionable_advice: [
                  "Discuss elevated CRP with your doctor to identify potential sources of inflammation.",
                  "Consider Vitamin D supplementation or increased sun exposure (with caution and sunscreen).",
                  "Maintain healthy diet and exercise habits."
              ],
              urgency: "Low to Medium",
              suggested_specialist: "General Practitioner" // Example suggested doctor type
          },
          // Optionally include other fields like raw data, timestamps, etc.
          processed_at: new Date().toISOString()
       };
       const data = mockResponseData; // Use mock data for testing


       // --- Actual Fetch Call (uncomment and replace mock data when backend is ready) ---
       /*
       const response = await fetch(API_ENDPOINT_LAB_REPORT, {
         method: 'POST',
         headers: {
             'Content-Type': 'application/json',
             // Add any necessary authentication headers (e.g., Authorization)
         },
         body: JSON.stringify(payload)
       });

       // Check for HTTP errors
       if (!response.ok) {
         let errorData;
         try {
             // Try to parse error response if it's JSON
             errorData = await response.json();
         } catch {
             // Otherwise, just get the raw text
             errorData = { error: await response.text() };
         }
         console.error("ChatScreen: Lab report API error:", response.status, errorData);
         throw new Error(errorData.error || `HTTP error ${response.status}: Failed to analyze lab report.`);
       }

       const data = await response.json(); // Parse the JSON response from the backend
       */


       console.log("ChatScreen: Lab report analysis received:", data);

       // Format the backend response into a consistent structure for the modal and history
       const formattedResponse = {
         type: 'lab_report', // Indicate the type of analysis
         // Use backend fields, falling back to defaults if needed
         medical_analysis: data.interpretation?.summary || data.interpretation?.overview || 'No summary provided.',
         good_results: data.interpretation?.good_results || [],
         bad_results: data.interpretation?.bad_results || [],
         actionable_advice: data.interpretation?.actionable_advice || [],
         urgency: data.interpretation?.urgency || 'Not specified',
         suggested_doctor: data.interpretation?.suggested_specialist, // Use suggested specialist
         query: 'Lab Report Analysis (Uploaded)' // Text to show in history list
       };

       setAnalysisResponse(formattedResponse); // Set the formatted response for the modal

       // Save the analysis result to history
       const historyItem = {
         id: Date.now().toString() + '_lab', // Generate a unique ID (timestamp + type suffix)
         text: 'Lab Report Analysis (Uploaded)', // Short text for history list
         summary: formattedResponse.medical_analysis.substring(0, 150) + (formattedResponse.medical_analysis.length > 150 ? '...' : ''), // Short summary
         time: new Date().toLocaleString(), // Local date and time string
         response: formattedResponse, // Store the full formatted response object
         type: 'lab_report', // Explicitly mark the type
         // Optionally, you could store the list of fetched doctors here as well:
         // doctors: doctors, // If doctors were fetched *before* saving history
       };
       const userId = profile?.user_id;
       // Use a user-specific key for AsyncStorage
       const historyKey = userId ? `history_${userId}` : 'history';

       const currentHistory = (history || []); // Get current history state
       const updatedHistory = [historyItem, ...currentHistory]; // Add the new item to the beginning

       try {
         // Save the updated history array to AsyncStorage
         await AsyncStorage.setItem(historyKey, JSON.stringify(updatedHistory));
         setHistory(updatedHistory); // Update the history state in the App component
         console.log("ChatScreen: Lab report analysis saved to history.");
       } catch (storageError) {
         console.error("ChatScreen: Error saving lab report history to AsyncStorage:", storageError);
         Alert.alert('Storage Error', 'Failed to save lab report analysis to history.');
         // Decide if failing to save history should stop showing the analysis - probably not critical.
       }

       // Fetch doctors if a specialist was suggested by the analysis
       if (formattedResponse.suggested_doctor) {
         fetchDoctors(formattedResponse.suggested_doctor, null); // Fetch doctors based on specialty
       } else {
         setDoctors([]); // Clear doctors list if no specialist suggested
       }

       setModalVisible(true); // Show the analysis modal
       setImageUri(null); // Clear the image preview after successful analysis
     } catch (error) {
       // Catch any errors during the API call or processing
       console.error('ChatScreen: Error processing lab report:', error);
       Alert.alert('Analysis Error', `Failed to analyze lab report: ${error.message || error}`);
       setAnalysisResponse(null); // Clear response on error
       setImageUri(null); // Clear preview on error
       setIsLoadingDoctors(false); // Ensure doctors loading is off
     } finally {
       setIsLoading(false); // Always turn off main loading state
     }
   };


   // --- Symptom Analysis Logic (Implemented Mock) ---
   // Function to send symptom text to the backend API for analysis
   const handleSymptomAnalysis = async () => {
       const symptoms = inputText.trim(); // Get and trim input text
       if (!symptoms) {
           Alert.alert("Input Required", "Please enter your symptoms to analyze.");
           return;
       }

       setIsLoading(true); // Set loading state
       setAnalysisResponse(null); // Clear previous results
       setDoctors([]);
       setIsLoadingDoctors(false);
        // Clear input text immediately for better UX, results will be in modal
       setInputText('');

       try {
           console.log("ChatScreen: Sending symptoms for analysis to backend...");
            const payload = {
              symptoms: symptoms,
              // Include user profile data for personalized analysis
              profile: profile || DEFAULT_PROFILE
              // Add other relevant data
            };

           // --- Replace with actual fetch to API_ENDPOINT when integrating backend ---
           console.warn("ChatScreen: Using MOCK Symptom Analysis API Call! Replace with actual backend endpoint.");
           await new Promise(resolve => setTimeout(resolve, 3000)); // Simulate API delay

            // Mock response data structure
            const mockResponseData = {
                medical_analysis: `Based on your symptoms ("${symptoms}"), it sounds like you might have a common cold or seasonal allergies. The analysis suggests resting and staying hydrated.`,
                root_cause: "Potential causes include viral infection (cold) or environmental allergens.",
                remedies: [
                    "Get plenty of rest.",
                    "Stay hydrated (water, tea, broth).",
                    "Consider over-the-counter remedies (consult pharmacist).",
                    "Avoid irritants like smoke."
                ],
                urgency: "Low",
                // Example health risks identified
                health_risks: [
                    { type: "cardiac", level: "low" },
                    { type: "diabetic", level: "low" }
                ],
                suggested_doctor: "General Practitioner" // Example suggested doctor type
            };
            const data = mockResponseData;

           // --- Actual Fetch Call (uncomment and replace mock data when backend is ready) ---
            /*
            const response = await fetch(API_ENDPOINT, {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json',
                  // Add any necessary authentication headers
              },
              body: JSON.stringify(payload)
            });

            if (!response.ok) { ... throw error ... }
            const data = await response.json();
            */

           console.log("ChatScreen: Symptom analysis received:", data);

           // Format the backend response into a consistent structure
           const formattedResponse = {
               type: 'symptom_analysis', // Indicate the type
               query: symptoms, // Store the original query text
               medical_analysis: data.medical_analysis || 'No analysis provided.',
               root_cause: data.root_cause,
               remedies: data.remedies || [],
               urgency: data.urgency || 'Not specified',
               medicines: data.medicines || [], // Assuming medicines might be mentioned by the AI
               health_risks: data.health_risks || [],
               suggested_doctor: data.suggested_doctor // Suggested specialist
           };

           setAnalysisResponse(formattedResponse); // Set for modal

           // Save to history
           const historyItem = {
               id: Date.now().toString() + '_symptom', // Unique ID
               text: symptoms, // Text for history list
               summary: formattedResponse.medical_analysis.substring(0, 150) + (formattedResponse.medical_analysis.length > 150 ? '...' : ''), // Summary
               time: new Date().toLocaleString(), // Timestamp
               response: formattedResponse, // Full response object
               type: 'symptom_analysis', // Explicitly mark type
           };
           const userId = profile?.user_id;
           const historyKey = userId ? `history_${userId}` : 'history';

           const currentHistory = (history || []);
           const updatedHistory = [historyItem, ...currentHistory]; // Add the new item to the beginning

           try {
             await AsyncStorage.setItem(historyKey, JSON.stringify(updatedHistory));
             setHistory(updatedHistory); // Update App component state
             console.log("ChatScreen: Symptom analysis saved to history.");

              // Check if medicines were suggested and update chatMedications state in App component
              if (formattedResponse.medicines && formattedResponse.medicines.length > 0) {
                 const medsWithPrefix = formattedResponse.medicines.map(med => `💊 ${med}`);
                 // Use functional update to ensure you get the latest state
                 setChatMedications(prevMeds => {
                    const updatedChatMeds = [...new Set([...prevMeds, ...medsWithPrefix])];
                    // The App component's useEffect reacting to chatMedications changes will handle saving this.
                    console.log("ChatScreen: Chat medications updated from analysis:", updatedChatMeds);
                    return updatedChatMeds;
                 });
              }

           } catch (storageError) {
             console.error("ChatScreen: Error saving symptom history/meds to AsyncStorage:", storageError);
             Alert.alert('Storage Error', 'Failed to save analysis results.');
           }


           // Fetch doctors if a specialist is suggested
           if (formattedResponse.suggested_doctor) {
             fetchDoctors(formattedResponse.suggested_doctor, null);
           } else {
             setDoctors([]);
           }

           setModalVisible(true); // Show the analysis modal

       } catch (error) {
           console.error('ChatScreen: Error processing symptom analysis:', error);
           Alert.alert('Analysis Error', `Failed to analyze symptoms: ${error.message || error}`);
           setAnalysisResponse(null);
           setIsLoadingDoctors(false);
       } finally {
           setIsLoading(false); // Always turn off main loading state
       }
   };


   const labReportHistory = (history || []).filter(item => item.type === 'lab_report');

   // Helper to navigate to History tab and show analysis modal from there if needed
   const viewPastAnalysisFromChat = (item) => {
       if (!item?.response) {
           Alert.alert("Error", "No analysis details found for this entry.");
           return;
       }
       // Navigate to the History tab screen within the HomeTabs navigator
       // Use params to signal the History screen to open the modal
       navigation.navigate('History', {
            showAnalysis: { // Use the same generic param name expected by HistoryScreen's useEffect
                response: item.response,
                 // Pass doctors if saved with the history item, otherwise History screen can fetch
                doctors: item.doctors || [],
                specialty: item.response?.suggested_doctor || ''
            }
       });
       // Note: The modal will actually be displayed by the HistoryScreen's useEffect
       // reacting to these params, or by a shared context if the modal logic
       // were lifted higher. For now, HistoryScreen will handle it.
   };


  return (
    // SafeAreaView for screen content, edges control which sides padding is applied
    <SafeAreaView style={styles.container} edges={['bottom', 'left', 'right']}>
       {/* --- Custom Top Bar with Drawer Icon --- */}
       {/* Added this to provide a visible way to open the drawer */}
        <View style={styles.topBar}>
            <TouchableOpacity onPress={() => navigation.openDrawer()} style={styles.menuButton}>
                <Ionicons name="menu" size={scaleFont(28)} color="#1e3a8a" />
            </TouchableOpacity>
            <Text style={styles.headerTitle}>Home</Text> {/* Title for this tab */}
            <View style={styles.menuButtonPlaceholder}></View> {/* Placeholder to balance title */}
        </View>

       {/* ScrollView wraps content to allow scrolling if content exceeds screen height */}
      <ScrollView contentContainerStyle={styles.scrollContainer} keyboardShouldPersistTaps="handled">
         {/* contentWrapper provides horizontal padding and max width */}
        <View style={styles.contentWrapper}>
          <Text style={styles.sectionTitle}>Analyze Health Data</Text> {/* Main title for the page */}

          {/* --- Symptom Analysis Section --- */}
          <Text style={[styles.sectionSubtitle, { marginTop: scaleSize(10) }]}>Analyze Your Symptoms</Text>
          <Text style={[styles.label, { textAlign: 'center', marginBottom: scaleSize(15), color: '#475569' }]}>
            Describe your symptoms to get insights and suggestions.
          </Text>
          <TextInput
             style={[styles.input, styles.multilineInput, { minHeight: scaleSize(100) }]}
             placeholder="Describe your symptoms here... (e.g., Headache behind the eyes, slight fever, sore throat)"
             placeholderTextColor="#9ca3af"
             multiline
             value={inputText}
             onChangeText={setInputText}
             editable={!isLoading} // Disable input while analysis is loading
             textAlignVertical="top" // Aligns text to the top for multiline input
          />
           <GradientButton
              title={isLoading ? "Analyzing..." : "Analyze Symptoms"}
              onPress={handleSymptomAnalysis} // Call the symptom analysis function
              disabled={isLoading || !inputText.trim()} // Disable if loading or input is empty after trimming
              style={{ marginBottom: scaleSize(30) }} // Space below the button
           />


          {/* --- Lab Report Analysis Section --- */}
          <Text style={[styles.sectionSubtitle]}>Analyze Lab Report</Text> {/* Section title */}
          <Text style={[styles.label, { textAlign: 'center', marginBottom: scaleSize(15), color: '#475569' }]}>
            Upload a photo of your lab report.
          </Text>
          <View style={styles.buttonRow}>
             {/* Button to pick image from library */}
            <GradientButton
              title="Upload Image"
              onPress={pickLabReportImage} // Call image picker function
              style={{ flex: 1, marginRight: scaleSize(8) }} // Takes half width
              disabled={isLoading} // Disable while analysis is running
            />
            {/* Button for taking a photo (placeholder) */}
            <GradientButton
              title="Take Photo"
              onPress={takePhoto} // Call placeholder function
              style={{ flex: 1 }} // Takes half width
              disabled={isLoading} // Disable while analysis is running
              colors={['#6b7280', '#9ca3af']} // Grey out slightly as it's a placeholder
            />
          </View>
          {isLoading && imageUri ? (
             // Show image preview only if an image was selected for lab analysis and loading
            <View style={{ alignItems: 'center', marginTop: scaleSize(30) }}>
              <ActivityIndicator size="large" color="#0052cc" />
              <Text style={styles.loadingText}>Analyzing Report...</Text>
              {imageUri && <Image source={{ uri: imageUri }} style={[styles.labImagePreview, { marginTop: scaleSize(15), opacity: 0.5 }]} />}
            </View>
          ) : imageUri ? (
            // Show static image preview if image is selected but not currently loading
            <View style={{ alignItems: 'center', marginTop: scaleSize(20) }}>
              <Image source={{ uri: imageUri }} style={styles.labImagePreview} resizeMode="contain" />
              <Text style={{ marginTop: scaleSize(10), color: '#475569', fontSize: scaleFont(14), textAlign: 'center' }}>
                Image selected. Analysis initiated automatically.
              </Text>
               {/* Removed the extra button here as processLabReportImage is called on select */}
            </View>
          ) : null}


          {/* --- Recent Lab Report Analyses (Link to full history) --- */}
           {/* Display a section showing only recent lab reports and a link to the full history */}
           <Text style={[styles.sectionSubtitle, { marginTop: scaleSize(40) }]}>Recent Lab Report Analyses</Text>
           {labReportHistory.length > 0 ? (
              <FlatList
                data={labReportHistory.slice(0, 3)} // Show only a few recent ones here (e.g., top 3)
                keyExtractor={(item) => item.id ? item.id.toString() : `lab-recent-${item.time}`} // Use item.id or unique combo for key
                renderItem={({ item }) => (
                   // Use a wrapper View to allow TouchableOpacity inside FlatList item for click area
                  <TouchableOpacity
                    key={item.id ? item.id.toString() : `lab-recent-${item.time}`} // Ensure key is on the outer View
                    style={[styles.historyItem, { backgroundColor: '#e0f2fe' }]} // Distinct color for lab reports
                    onPress={() => viewPastAnalysisFromChat(item)} // Navigate to History tab to view full analysis
                    activeOpacity={0.7}
                  >
                    <View style={styles.historyContent}>
                      <Text style={styles.historyTime}>{item.time}</Text>
                      <Text style={styles.historyQuery} numberOfLines={2}> 📄 {item.text} </Text>
                      <Text style={styles.historySummary} numberOfLines={3}> Summary: {item.summary || 'No summary.'} </Text>
                    </View>
                    <Ionicons name="chevron-forward-outline" size={scaleFont(20)} color="#0052cc" />
                  </TouchableOpacity>
                )}
                contentContainerStyle={{ paddingBottom: scaleSize(10) }}
                showsVerticalScrollIndicator={false}
                scrollEnabled={false} // Disable FlatList scrolling to allow parent ScrollView to scroll
              />
           ) : (
              // Message when no recent lab reports are found
              <View style={styles.emptyView}>
                <Ionicons name="document-text-outline" size={scaleFont(50)} color="#9ca3af" />
                <Text style={[styles.emptyMessage, { marginTop: scaleSize(15) }]}>No recent lab report analyses.</Text>
                <Text style={[styles.emptyMessage, { fontSize: scaleFont(14), marginTop: scaleSize(5) }]}>Upload your first report above.</Text>
              </View>
           )}
           {(history || []).length > 0 && ( // Show link to full history only if there is any history
               <TouchableOpacity
                   style={{ alignSelf: 'center', marginTop: scaleSize(10), padding: scaleSize(8) }}
                   onPress={() => navigation.navigate('History')} // Navigate to the History tab
               >
                  <Text style={{ color: '#0052cc', fontSize: scaleFont(15), textDecorationLine: 'underline' }}>
                     View All History ({history.length})
                  </Text>
               </TouchableOpacity>
           )}

        </View>
      </ScrollView>
      {/* Analysis Modal - Shared component */}
      <AnalysisModal
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        response={analysisResponse}
        doctors={doctors}
        specialty={analysisResponse?.suggested_doctor} // Pass suggested doctor for map search in modal
        isLoadingDoctors={isLoadingDoctors}
      />
    </SafeAreaView>
  );
};


// Medication Screen (Direct Drawer Screen)
const MedicationScreen = ({ medicationsFromChat = [], reminders = [], setReminders, profile }) => {
  const allMedications = [...new Set(medicationsFromChat || [])];
  const [expandedMedIndex, setExpandedMedIndex] = useState(null);
  const [reminderTimeInput, setReminderTimeInput] = useState('');
  const [editingReminder, setEditingReminder] = useState(null);
  const navigation = useNavigation();
  const validateTime = (time) => /^([01]\d|2[0-3]):([0-5]\d)$/.test(time);
  const cleanMedName = (medWithPrefix) => medWithPrefix.replace('💊 ', '').trim();

  const scheduleMedicineNotification = async (medicationName, time, existingId = null) => {
    const permissionsGranted = await requestNotificationPermissions(); if (!permissionsGranted) { Alert.alert("Notification Scheduling Failed", "Notifications permission is required to set reminders."); return null; } if (!medicationName || !time) { console.warn("MedicationScreen: Scheduling failed: Missing medication name or time."); return null; } const [hours, minutes] = time.split(':').map(Number); try { if (existingId) { try { await Notifications.cancelScheduledNotificationAsync(existingId); console.log('MedicationScreen: Cancelled existing notification:', existingId); } catch (cancelError) { console.error("MedicationScreen: Failed to cancel existing notification:", cancelError); } } const identifier = await Notifications.scheduleNotificationAsync({ content: { title: 'Medication Reminder 💊', body: `Time to take your ${medicationName} at ${time}.`, sound: 'default' }, trigger: { hour: hours, minute: minutes, repeats: true } }); console.log('MedicationScreen: Scheduled notification:', identifier, 'for', medicationName, 'at', time); return identifier; } catch (error) { console.error('MedicationScreen: Schedule Notification Error:', error); Alert.alert('Scheduling Error', `Failed to schedule reminder for ${medicationName}.`); return null; } };

  const handleSetOrUpdateReminder = async (medName) => {
    if (!medName) { console.error("MedicationScreen: Internal error: Medication name missing for reminder."); return; } const trimmedTime = reminderTimeInput.trim(); if (!validateTime(trimmedTime)) { Alert.alert('Invalid Time', 'Please use HH:MM format (e.g., 08:00).'); return; } const userId = profile?.user_id; if (!userId) { Alert.alert('Error', 'User not logged in, cannot save reminder.'); return; } const remindersKey = `reminders_${userId}`; const existingReminder = (reminders || []).find(r => r.medication === medName); const isUpdating = !!existingReminder; const notificationId = await scheduleMedicineNotification(medName, trimmedTime, existingReminder?.notificationId); if (!notificationId && !isUpdating) { Alert.alert("Scheduling Failed", "Could not set notification reminder."); return; } if (!notificationId && isUpdating) { console.warn("MedicationScreen: Failed to schedule new notification ID during update. Proceeding to save state without notification link."); } const newOrUpdatedReminder = { medication: medName, time: trimmedTime, notificationId: notificationId || (isUpdating ? existingReminder.notificationId : null) }; let updatedReminders; const currentReminders = reminders || []; if (isUpdating) { updatedReminders = currentReminders.map(r => r.medication === medName ? newOrUpdatedReminder : r ); Alert.alert('Success', 'Reminder updated!'); } else { updatedReminders = [...currentReminders, newOrUpdatedReminder]; Alert.alert('Success', 'Reminder set!'); } try { await AsyncStorage.setItem(remindersKey, JSON.stringify(updatedReminders)); setReminders(updatedReminders); setReminderTimeInput(''); setEditingReminder(null); } catch (error) { console.error('MedicationScreen: Failed to save reminders:', error); Alert.alert('Storage Error', 'Could not save reminder changes.'); } };

  const handleEditReminder = (medName) => { const reminder = (reminders || []).find(r => r.medication === medName); if (!reminder) return; setReminderTimeInput(reminder.time); const medIndexInList = allMedications.findIndex(m => cleanMedName(m) === medName); setEditingReminder({ medName }); setExpandedMedIndex(medIndexInList >= 0 ? medIndexInList : null); };

  const handleDeleteReminder = async (medName) => { const userId = profile?.user_id; if (!userId) { Alert.alert('Error', 'User not logged in.'); return; } const remindersKey = `reminders_${userId}`; const reminderToDelete = (reminders || []).find(r => r.medication === medName); if (!reminderToDelete) { console.error("MedicationScreen: Attempted to delete non-existent reminder for:", medName); return; } Alert.alert( 'Delete Reminder', `Delete reminder for ${reminderToDelete.medication} at ${reminderToDelete.time}?`, [ { text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: async () => { if (reminderToDelete.notificationId) { await Notifications.cancelScheduledNotificationAsync(reminderToDelete.notificationId).catch(e => console.error("MedicationScreen: Error cancelling notification:", e)); } const updatedReminders = (reminders || []).filter(r => r.medication !== medName); try { await AsyncStorage.setItem(remindersKey, JSON.stringify(updatedReminders)); setReminders(updatedReminders); if (editingReminder?.medName === medName) { setEditingReminder(null); setReminderTimeInput(''); } const medIndexInList = allMedications.findIndex(m => cleanMedName(m) === medName); if (expandedMedIndex === medIndexInList) { setExpandedMedIndex(null); } Alert.alert('Success', 'Reminder deleted.'); } catch (error) { console.error('MedicationScreen: Failed to delete reminder:', error); Alert.alert('Storage Error', 'Could not update reminder list.'); } } } ] ); };
  const findReminderByMedName = (name) => (reminders || []).find(r => r.medication === name);

  return (
    <SafeAreaView style={styles.container} edges={['bottom', 'left', 'right']}>
       <View style={styles.topBar}>
           <TouchableOpacity onPress={() => navigation.openDrawer()} style={styles.menuButton}>
               <Ionicons name="menu" size={scaleFont(28)} color="#1e3a8a" />
           </TouchableOpacity>
           <Text style={styles.headerTitle}>Medication Reminders</Text>
           <View style={styles.menuButtonPlaceholder}></View>
       </View>
      <ScrollView contentContainerStyle={styles.scrollContainer}>
        <View style={styles.contentWrapper}>
          <Text style={styles.sectionTitle}>Medication Reminders</Text>
          <Text style={[styles.label, styles.centerText, styles.subtleText, { marginBottom: scaleSize(15) }]}>
            Manage reminders for medications suggested during analysis.
            {'\n'}<Text style={{ fontSize: scaleFont(12), fontStyle: 'italic' }}>(Tap medication to set/edit reminder)</Text>
          </Text>
          {allMedications.length > 0 ? (
            allMedications.map((medWithPrefix, index) => {
              const cleanName = cleanMedName(medWithPrefix); const reminder = findReminderByMedName(cleanName); const isExpanded = expandedMedIndex === index; const isEditingThisMed = editingReminder?.medName === cleanName;
              return (
                <View key={`med-${index}`} style={[styles.medicationItem, { backgroundColor: isExpanded ? '#e0f2fe' : '#f1f5f9' }]}>
                  <TouchableOpacity onPress={() => { const newState = isExpanded ? null : index; setExpandedMedIndex(newState); if(isEditingThisMed && newState !== index) { setEditingReminder(null); setReminderTimeInput(''); } if (!isExpanded && reminder) { setReminderTimeInput(reminder.time); setEditingReminder({ medName: cleanName }); } }} accessibilityLabel={`Toggle details for ${cleanName}`} activeOpacity={0.7}>
                    <View style={styles.medHeader}>
                      <Text style={styles.medicationText} numberOfLines={1}>{medWithPrefix}</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                        {reminder && ( <Ionicons name="alarm-outline" size={scaleFont(18)} color="#0052cc" style={{ marginRight: scaleSize(5) }} /> )}
                        <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={scaleFont(20)} color="#1e3a8a" />
                      </View>
                    </View>
                  </TouchableOpacity>
                  {isExpanded && (
                    <View style={styles.medDetails}>
                      <Text style={styles.detailText}>Always consult your doctor/pharmacist about medications before starting or changing your routine.</Text>
                      {reminder && !isEditingThisMed ? ( <View style={styles.reminderContainer}><Text style={styles.reminderText}>Reminder Set: <Text style={{ fontWeight: 'bold' }}>{reminder.time}</Text> daily</Text><View style={styles.reminderButtons}><GradientButton title="Edit" onPress={() => handleEditReminder(cleanName)} colors={['#f59e0b', '#fbbf24']} style={styles.editButton}/><GradientButton title="Delete" onPress={() => handleDeleteReminder(cleanName)} colors={['#dc2626', '#ef4444']} style={styles.deleteButton}/></View></View> ) : ( <View style={styles.reminderForm}><Text style={styles.label}>{reminder ? 'Update Time (HH:MM)' : 'Set Reminder Time (HH:MM)'}</Text><TextInput style={[styles.input, { marginBottom: scaleSize(12) }]} value={reminderTimeInput} onChangeText={setReminderTimeInput} placeholder="e.g., 08:00" keyboardType="number-pad" maxLength={5} autoCapitalize="none" autoCorrect={false}/><GradientButton onPress={() => handleSetOrUpdateReminder(cleanName)} title={reminder ? 'Update Reminder' : 'Set Reminder'} colors={['#0052cc', '#2684ff']} disabled={!validateTime(reminderTimeInput.trim())}/><TouchableOpacity style={styles.cancelEditButton} onPress={() => { setEditingReminder(null); setReminderTimeInput(''); }}><Text style={styles.cancelEditText}>Cancel Edit</Text></TouchableOpacity></View> )}
                    </View>
                  )}
                </View>
              );
            })
          ) : (
            <View style={styles.emptyView}>
              <Ionicons name="medkit-outline" size={scaleFont(50)} color="#9ca3af" />
              <Text style={[styles.emptyMessage, { marginTop: scaleSize(15) }]}>No medications identified yet.</Text>
              <Text style={[styles.emptyMessage, { fontSize: scaleFont(14), marginTop: scaleSize(5) }]}>Run an analysis on the Home tab to see potential medications.</Text>
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};


// History Screen (Tab within HomeTabs)
const HistoryScreen = ({ history = [], setHistory, profile, route }) => {
  const [modalVisible, setModalVisible] = useState(false);
  const [selectedAnalysis, setSelectedAnalysis] = useState(null);
  const [doctorsForModal, setDoctorsForModal] = useState([]);
  const [isLoadingDoctorsModal, setIsLoadingDoctorsModal] = useState(false);
  const navigation = useNavigation();
  const getHistoryKey = useCallback(() => profile?.user_id ? `history_${profile.user_id}` : 'history', [profile?.user_id]);
   const fetchDoctorsMock = useCallback(async (specialty) => {
     setIsLoadingDoctorsModal(true); setDoctorsForModal([]);
     console.warn("HistoryScreen: Triggering simulated doctor fetch from History screen.");
     await new Promise(resolve => setTimeout(resolve, 1500));
     const simulatedDocs = [{ name: `History Sim. Dr. ${specialty} One`, address: '789 Past Lane, Anytown', rating: 4.2 },{ name: `History Sim. Dr. ${specialty} Two`, address: '101 Old Rd, Anytown', rating: 4.0 }];
     setDoctorsForModal(simulatedDocs);
     setIsLoadingDoctorsModal(false);
   }, []);


  useEffect(() => {
    if (route.params?.showAnalysis && JSON.stringify(route.params.showAnalysis.response) !== JSON.stringify(selectedAnalysis)) {
      const { response: analysisResp, doctors: analysisDoctors, specialty: analysisSpecialty } = route.params.showAnalysis; console.log("HistoryScreen: Received showAnalysis params:", route.params.showAnalysis);
      setSelectedAnalysis(analysisResp);
      if (analysisDoctors && analysisDoctors.length > 0) { setDoctorsForModal(analysisDoctors); setIsLoadingDoctorsModal(false); } else if (analysisSpecialty) { fetchDoctorsMock(analysisSpecialty); } else { setDoctorsForModal([]); setIsLoadingDoctorsModal(false); }
      setModalVisible(true);
      const timer = setTimeout(() => { if (navigation.isFocused()) { console.log("HistoryScreen: Clearing showAnalysis navigation params."); navigation.setParams({ showAnalysis: undefined }); } }, 10);
      return () => clearTimeout(timer);
    } else if (route.params?.showAnalysis && JSON.stringify(route.params.showAnalysis.response) === JSON.stringify(selectedAnalysis)) { console.log("HistoryScreen: showAnalysis params match current state, clearing params."); const timer = setTimeout(() => { if (navigation.isFocused()) { navigation.setParams({ showAnalysis: undefined }); } }, 10); return () => clearTimeout(timer); }
  }, [route.params?.showAnalysis, navigation, selectedAnalysis, fetchDoctorsMock]);


  const clearHistory = () => { const userId = profile?.user_id; if (!userId) { Alert.alert("Error", "Cannot clear history, user not identified."); return; } const historyKey = getHistoryKey(); Alert.alert( "Clear History", "Are you sure you want to delete your entire query history? This action cannot be undone.", [ { text: "Cancel", style: "cancel" }, { text: "Delete All", style: "destructive", onPress: async () => { try { await AsyncStorage.removeItem(historyKey); setHistory([]); Alert.alert('Success', 'History cleared.'); } catch (e) { console.error("HistoryScreen: Failed to clear history:", e); Alert.alert('Error', 'Failed to clear history.'); } } } ] ); };
  const deleteHistoryItem = (itemIdToDelete) => { const userId = profile?.user_id; if (!userId) { Alert.alert('Error', 'User not logged in.'); return; } const historyKey = getHistoryKey(); const itemToDelete = (history || []).find(item => item.id === itemIdToDelete); if (!itemToDelete) { console.error("HistoryScreen: Attempted to delete non-existent history item with id", itemIdToDelete); return; } Alert.alert( "Delete Item", `Delete entry from ${itemToDelete.time} (${itemToDelete.type === 'lab_report' ? 'Lab Report' : 'Query'})?`, [ { text: "Cancel", style: "cancel" }, { text: "Delete", style: "destructive", onPress: async () => { const newHistory = (history || []).filter(item => item.id !== itemIdToDelete); try { await AsyncStorage.setItem(historyKey, JSON.stringify(newHistory)); setHistory(newHistory); Alert.alert('Success', 'Item deleted.'); } catch (e) { console.error("HistoryScreen: Failed to delete history item:", e); Alert.alert('Error', 'Failed to delete item.'); } } } ] ); };
  const viewAnalysis = (item) => { if (!item?.response) { Alert.alert("Error", "No analysis details found for this entry."); return; } setSelectedAnalysis(item.response); setDoctorsForModal(item.doctors || []); setIsLoadingDoctorsModal(false); setModalVisible(true); };

  return (
    <SafeAreaView style={styles.container} edges={['bottom', 'left', 'right']}>
        <View style={styles.topBar}>
            <TouchableOpacity onPress={() => navigation.openDrawer()} style={styles.menuButton}>
                <Ionicons name="menu" size={scaleFont(28)} color="#1e3a8a" />
            </TouchableOpacity>
            <Text style={styles.headerTitle}>History</Text>
             {(history || []).length > 0 ? ( <TouchableOpacity onPress={clearHistory} style={styles.trashButton} accessibilityLabel="Clear entire history"><Ionicons name="trash" size={scaleFont(24)} color="#dc3545" /></TouchableOpacity> ) : ( <View style={styles.menuButtonPlaceholder}></View> )}
        </View>
      <ScrollView contentContainerStyle={styles.scrollContainer}>
        <View style={[styles.contentWrapper, { paddingTop: scaleSize(10), flex: 1 }]}>
          <View style={styles.historyHeader}> <Text style={styles.sectionTitle}>Query History</Text> </View>
          {(history || []).length > 0 ? (
            <FlatList data={history} keyExtractor={(item, index) => item.id ? item.id.toString() : `history-${index}`} renderItem={({ item, index }) => (
                <View key={item.id ? item.id.toString() : `history-${index}`} style={[styles.historyItem, { backgroundColor: item.type === 'lab_report' ? '#e0f2fe' : '#f1f5f9' }]}>
                  <TouchableOpacity onPress={() => viewAnalysis(item)} style={styles.historyContent} activeOpacity={0.7}>
                    <Text style={styles.historyTime}>{item.time}</Text>
                    <Text style={styles.historyQuery} numberOfLines={2}> {item.type === 'lab_report' ? '📄 Lab Report: ' : '💬 Query: '} {item.text} </Text>
                    <Text style={styles.historySummary} numberOfLines={3}> Summary: {item.summary || 'No summary.'} </Text>
                    {/* Add type icon for clarity */}
                     <Text style={{ fontSize: scaleFont(12), color: '#6b7280', marginTop: scaleSize(4) }}>
                        {item.type === 'lab_report' ? 'Lab Report' : 'Symptom Analysis'}
                     </Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.deleteItemButton} onPress={() => deleteHistoryItem(item.id)} accessibilityLabel={`Delete entry from ${item.time}`}>
                    <Ionicons name="trash-outline" size={scaleFont(18)} color="#dc3545" />
                  </TouchableOpacity>
                </View> )} contentContainerStyle={{ paddingBottom: scaleSize(30) }} showsVerticalScrollIndicator={false} scrollEnabled={false}/>
          ) : (
            <View style={styles.emptyView}>
              <Ionicons name="archive-outline" size={scaleFont(50)} color="#9ca3af" />
              <Text style={[styles.emptyMessage, { marginTop: scaleSize(15) }]}> Query history is empty. </Text>
              <Text style={[styles.emptyMessage, { fontSize: scaleFont(14), marginTop: scaleSize(5) }]}> Analyses you perform will appear here. </Text>
            </View> )}
        </View>
      </ScrollView>
      <AnalysisModal visible={modalVisible} onClose={() => setModalVisible(false)} response={selectedAnalysis} doctors={doctorsForModal} specialty={selectedAnalysis?.suggested_doctor} isLoadingDoctors={isLoadingDoctorsModal}/>
    </SafeAreaView>
  );
};


// Health Tips Screen (Tab within HomeTabs)
const HealthTipsScreen = ({ favoriteTips = [], toggleFavoriteTip, profile }) => {
  const [expandedTipIndex, setExpandedTipIndex] = useState(null);
  const [viewMode, setViewMode] = useState('all');
  const navigation = useNavigation();
  const tipsToDisplay = viewMode === 'favorites' ? HEALTH_TIPS.filter(tip => (favoriteTips || []).includes(tip.id)) : HEALTH_TIPS;

  return (
    <SafeAreaView style={styles.container} edges={['bottom', 'left', 'right']}>
       <View style={styles.topBar}>
           <TouchableOpacity onPress={() => navigation.openDrawer()} style={styles.menuButton}>
               <Ionicons name="menu" size={scaleFont(28)} color="#1e3a8a" />
           </TouchableOpacity>
           <Text style={styles.headerTitle}>Health Tips</Text>
            <TouchableOpacity style={[styles.toggleButton, viewMode === 'favorites' && styles.toggleButtonActive]} onPress={() => { setViewMode(viewMode === 'all' ? 'favorites' : 'all'); setExpandedTipIndex(null); }} activeOpacity={0.7} accessibilityLabel={`Show ${viewMode === 'favorites' ? 'All Tips' : 'Favorite Tips'}`}>
              <Ionicons name={viewMode === 'favorites' ? 'star' : 'list'} size={scaleFont(18)} color={viewMode === 'favorites' ? '#ffffff' : '#0052cc'}/>
              <Text style={[styles.toggleButtonText, viewMode === 'favorites' && styles.toggleButtonTextActive]}> {viewMode === 'favorites' ? 'Favorites' : 'All Tips'} </Text>
            </TouchableOpacity>
       </View>
      <View style={[styles.contentWrapper, { paddingTop: scaleSize(10), flex: 1 }]}>
        <View style={styles.tipsHeader}> <Text style={styles.sectionTitle}>Health Tips</Text> </View>
        {tipsToDisplay.length > 0 ? (
            <FlatList data={tipsToDisplay} keyExtractor={item => item.id} renderItem={({ item, index }) => { const isFavorite = (favoriteTips || []).includes(item.id); const isExpanded = expandedTipIndex === index; return ( <View style={[styles.tipItem, { backgroundColor: isExpanded ? '#e0f2fe' : '#f1f5f9' }]}> <TouchableOpacity onPress={() => setExpandedTipIndex(isExpanded ? null : index)} activeOpacity={0.8}> <View style={styles.tipHeader}> <Text style={styles.tipTitle} numberOfLines={2}>{item.title}</Text> <View style={styles.tipIcons}> <TouchableOpacity onPress={() => toggleFavoriteTip(item.id)} style={styles.favoriteButton} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }} accessibilityLabel={isFavorite ? 'Remove from favorites' : 'Add to favorites'}> <Ionicons name={isFavorite ? 'star' : 'star-outline'} size={scaleFont(22)} color={isFavorite ? '#f59e0b' : '#64748b'} /> </TouchableOpacity> <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={scaleFont(20)} color="#1e3a8a" style={{ marginLeft: scaleSize(5) }} /> </View> </View> {!isExpanded && ( <Text style={styles.tipSummary} numberOfLines={2}>{item.summary}</Text> )} </TouchableOpacity> {isExpanded && ( <View style={styles.tipDetails}> <Text style={styles.tipContent}>{item.content}</Text> </View> )} </View> ); }} contentContainerStyle={{ paddingBottom: scaleSize(30) }} showsVerticalScrollIndicator={false} scrollEnabled={false} ListEmptyComponent={ <View style={styles.emptyView}> <Ionicons name={viewMode === 'favorites' ? 'star-outline' : 'information-circle-outline'} size={scaleFont(50)} color="#9ca3af" /> <Text style={[styles.emptyMessage, { marginTop: scaleSize(15) }]}> {viewMode === 'favorites' ? 'No favorite tips yet.' : 'No health tips available.'} </Text> {viewMode === 'favorites' && ( <Text style={[styles.emptyMessage, { fontSize: scaleFont(14), marginTop: scaleSize(5) }]}> Tap the star icon on a tip to add it to your favorites. </Text> )} </View> } />
        ) : ( null )}
      </View>
    </SafeAreaView>
  );
};


// Appointments Screen (Direct Drawer Screen)
const AppointmentsScreen = ({ appointments = [], setAppointments, profile }) => {
  const [dateTimeInput, setDateTimeInput] = useState('');
  const [appointmentTitle, setAppointmentTitle] = useState('');
  const [showForm, setShowForm] = useState(false);
  const navigation = useNavigation();

  const getAppointmentsKey = useCallback(() => profile?.user_id ? `appointments_${profile.user_id}` : 'appointments', [profile?.user_id]);
  const validateDateTime = (input) => { const regex = /^(0?[1-9]|1[0-2])\/(0?[1-9]|[12]\d|3[01])\/(20\d{2})\s([01]\d|2[0-3]):([0-5]\d)$/; const match = input.match(regex); if (!match) return false; try { const [, month, day, year, hour, minute] = match; const appointmentDate = new Date(parseInt(year), parseInt(month) - 1, parseInt(day), parseInt(hour), parseInt(minute), 0); if ( appointmentDate.getFullYear() !== parseInt(year) || appointmentDate.getMonth() !== parseInt(month) - 1 || appointmentDate.getDate() !== parseInt(day) || appointmentDate.getHours() !== parseInt(hour) || appointmentDate.getMinutes() !== parseInt(minute) ) { return false; } return appointmentDate.getTime() > new Date().getTime(); } catch (e) { console.error("AppointmentsScreen: Date validation error:", e); return false; } };

  const scheduleAppointmentNotification = async (title, dateTimeString) => { const permissionsGranted = await requestNotificationPermissions(); if (!permissionsGranted) { Alert.alert("Notification Scheduling Failed", "Notifications permission is required to set reminders."); return null; } if (!title || !dateTimeString) { console.warn("AppointmentsScreen: Scheduling failed: Missing title or date/time string."); return null; } try { const regex = /^(\d{1,2})\/(\d{1,2})\/(\d{4})\s(\d{2}):(\d{2})$/; const match = dateTimeString.match(regex); if (!match) { console.warn("AppointmentsScreen: Scheduling failed: Invalid date/time format provided."); return null; } const [, month, day, year, hour, minute] = match; const appointmentDate = new Date(parseInt(year), parseInt(month) - 1, parseInt(day), parseInt(hour), parseInt(minute), 0); const reminderTime = new Date(appointmentDate.getTime() - 60 * 60 * 1000); if (reminderTime.getTime() <= new Date().getTime()) { console.log("AppointmentsScreen: Reminder time is in the past, skipping notification for:", title); return null; } const identifier = await Notifications.scheduleNotificationAsync({ content: { title: 'Upcoming Appointment 🗓️', body: `Your appointment "${title}" is coming up soon! It's scheduled for ${dateTimeString}.`, sound: 'default' }, trigger: reminderTime }); console.log("AppointmentsScreen: Scheduled appointment notification:", identifier, "for", title, "at", dateTimeString); return identifier; } catch (error) { console.error("AppointmentsScreen: Error scheduling appointment notification:", error); Alert.alert("Notification Error", "Could not schedule reminder notification for the appointment."); return null; } };
  const cancelAppointmentNotification = async (identifier) => { if (identifier) { try { await Notifications.cancelScheduledNotificationAsync(identifier); console.log("AppointmentsScreen: Cancelled notification:", identifier); } catch (error) { console.error("AppointmentsScreen: Error cancelling notification:", error); } } };

  const bookAppointment = async () => { const userId = profile?.user_id; if (!userId) { Alert.alert('Error', 'User not logged in.'); return; } const appointmentsKey = getAppointmentsKey(); const trimmedTitle = appointmentTitle.trim(); const trimmedDateTime = dateTimeInput.trim(); if (!trimmedTitle) { Alert.alert('Input Required', 'Please enter a title for the appointment.'); return; } if (!validateDateTime(trimmedDateTime)) { Alert.alert('Invalid Input', 'Please enter a valid future date and time in MM/DD/YYYY HH:MM format.'); return; } const notificationId = await scheduleAppointmentNotification(trimmedTitle, trimmedDateTime); const newAppointment = { id: Date.now().toString(), date: trimmedDateTime, title: trimmedTitle, notificationId: notificationId || null }; const updatedAppointments = [...(appointments || []), newAppointment].sort((a, b) => { const parseDateString = (dateStr) => { const match = dateStr.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})\s(\d{2}):(\d{2})$/); if (!match) return new Date(0); const [, month, day, year, hour, minute] = match; return new Date(parseInt(year), parseInt(month) - 1, parseInt(day), parseInt(hour), parseInt(minute)); }; const dateA = parseDateString(a.date); const dateB = parseDateString(b.date); return dateA.getTime() - dateB.getTime(); }); try { await AsyncStorage.setItem(appointmentsKey, JSON.stringify(updatedAppointments)); setAppointments(updatedAppointments); Alert.alert('Success', 'Appointment added!'); setDateTimeInput(''); setAppointmentTitle(''); setShowForm(false); } catch (error) { console.error("AppointmentsScreen: Failed to save appointment:", error); Alert.alert('Storage Error', 'Could not save appointment.'); } };

  const cancelAppointment = (idToCancel) => { const userId = profile?.user_id; if (!userId) { Alert.alert('Error', 'User not logged in.'); return; } const appointmentsKey = getAppointmentsKey(); const apptToCancel = (appointments || []).find(a => a.id === idToCancel); if (!apptToCancel) { console.error("AppointmentsScreen: Attempted to cancel non-existent appointment with id", idToCancel); return; } Alert.alert( "Cancel Appointment", `Cancel "${apptToCancel.title}" on ${apptToCancel.date}?`, [ { text: "Keep", style: "cancel" }, { text: "Cancel It", style: "destructive", onPress: async () => { if (apptToCancel.notificationId) { await Notifications.cancelScheduledNotificationAsync(apptToCancel.notificationId).catch(e => console.error("AppointmentsScreen: Error cancelling notification:", e)); } const updated = (appointments || []).filter(a => a.id !== idToCancel); try { await AsyncStorage.setItem(appointmentsKey, JSON.stringify(updated)); setAppointments(updated); Alert.alert('Success', 'Appointment cancelled.'); } catch (e) { console.error("AppointmentsScreen: Failed to delete appointment:", e); Alert.alert('Storage Error', 'Could not update list.'); } } } ] ); };

  const renderAppointment = ({ item }) => ( <View style={styles.appointmentItem}> <View style={styles.appointmentDetails}> <Ionicons name="calendar-outline" size={scaleFont(20)} color="#0052cc" style={{ marginRight: scaleSize(10) }}/> <View style={{ flex: 1 }}> <Text style={styles.appointmentTitle}>{item.title}</Text> <Text style={styles.appointmentDate}>{item.date}</Text> </View> </View> <TouchableOpacity style={styles.cancelButton} onPress={() => cancelAppointment(item.id)} accessibilityLabel={`Cancel appointment "${item.title}" on ${item.date}`}> <Ionicons name="trash-outline" size={scaleFont(20)} color="#dc3545" /> </TouchableOpacity> </View> );

  return (
    <SafeAreaView style={styles.container} edges={['bottom', 'left', 'right']}>
       <View style={styles.topBar}>
           <TouchableOpacity onPress={() => navigation.openDrawer()} style={styles.menuButton}>
               <Ionicons name="menu" size={scaleFont(28)} color="#1e3a8a" />
           </TouchableOpacity>
           <Text style={styles.headerTitle}>Appointments</Text>
           <View style={styles.menuButtonPlaceholder}></View>
       </View>
      <View style={[styles.contentWrapper, { paddingTop: scaleSize(10), flex: 1 }]}>
        <Text style={styles.sectionTitle}>Upcoming Appointments</Text>
        {!showForm && ( <GradientButton title="Add New Appointment" onPress={() => setShowForm(true)} style={{ marginBottom: scaleSize(20) }} /> )}
        {showForm && (
          <View style={styles.datePickerContainer}>
            <Text style={styles.label}>Appointment Title:</Text>
            <TextInput style={styles.input} value={appointmentTitle} onChangeText={setAppointmentTitle} placeholder="e.g., Doctor Checkup"/>
            <Text style={styles.label}>Date and Time (MM/DD/YYYY HH:MM):</Text>
            <TextInput style={styles.input} value={dateTimeInput} onChangeText={setDateTimeInput} placeholder="e.g., 12/31/2024 14:30" keyboardType="numbers-and-punctuation" autoCapitalize="none" autoCorrect={false} maxLength={16}/>
            <View style={styles.datePickerButtons}>
              <GradientButton title="Cancel" onPress={() => { setShowForm(false); setAppointmentTitle(''); setDateTimeInput(''); }} colors={['#6b7280', '#9ca3af']} style={{ flex: 1, marginRight: scaleSize(8) }}/>
              <GradientButton title="Confirm & Add" onPress={bookAppointment} colors={['#16a34a', '#22c55e']} style={{ flex: 1 }} disabled={!validateDateTime(dateTimeInput.trim()) || !appointmentTitle.trim()}/>
            </View>
          </View> )}
        {(appointments || []).length > 0 ? ( <FlatList data={appointments} renderItem={renderAppointment} keyExtractor={item => item.id.toString()} style={styles.appointmentList} contentContainerStyle={{ paddingBottom: scaleSize(20) }} showsVerticalScrollIndicator={false} scrollEnabled={false}/> ) : ( <View style={styles.emptyView}> <Ionicons name="calendar-outline" size={scaleFont(50)} color="#9ca3af" /> <Text style={[styles.emptyMessage, { marginTop: scaleSize(15) }]}> No upcoming appointments. </Text> {!showForm && ( <Text style={[styles.emptyMessage, { fontSize: scaleFont(14), marginTop: scaleSize(5) }]}> Click "Add New Appointment" to add one. </Text> )} </View> )}
      </View>
    </SafeAreaView>
  );
};


// Symptom Progress Screen (Direct Drawer Screen)
const SymptomProgressScreen = ({ symptomProgress = [], setSymptomProgress, profile }) => {
  const [newEntrySymptoms, setNewEntrySymptoms] = useState('');
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState('ongoing');
  const navigation = useNavigation();

  const getSymptomProgressKey = useCallback(() => profile?.user_id ? `symptomProgress_${profile.user_id}` : 'symptomProgress', [profile?.user_id]);
  const getStatusDetails = (s) => { const statusMap = { ongoing: { icon: '📝', color: '#0ea5e9', label: 'Ongoing' }, improving: { icon: '👍', color: '#22c55e', label: 'Improving' }, recovered: { icon: '🎉', color: '#f59e0b', label: 'Recovered' }, escalate: { icon: '🚑', color: '#dc2626', label: 'Escalate / Worsening' } }; return statusMap[s?.toLowerCase()] || statusMap['ongoing']; };

  const addEntry = async () => { const userId = profile?.user_id; if (!userId) { Alert.alert('Error', 'User not logged in.'); return; } const symptomProgressKey = getSymptomProgressKey(); const sym = newEntrySymptoms.trim(); if (!sym) { Alert.alert('Input Required', 'Please describe your current symptoms for the entry.'); return; } const now = new Date(); const entry = { id: now.toISOString() + Math.random().toString(36).substring(2, 8), date: now.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' }), time: now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true }), symptoms: sym, notes: notes.trim(), status: status.toLowerCase(), timestamp: now.toISOString() }; const updated = [entry, ...(symptomProgress || [])].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime() ); try { await AsyncStorage.setItem(symptomProgressKey, JSON.stringify(updated)); setSymptomProgress(updated); setNewEntrySymptoms(''); setNotes(''); setStatus('ongoing'); Alert.alert('Success', 'Symptom entry added.'); if (status === 'escalate') { Alert.alert( 'Urgent Action Recommended', 'Your symptoms status is marked as escalating. It is recommended to consider contacting a healthcare provider soon.', [{ text: 'OK' }] ); } } catch (e) { console.error("SymptomProgressScreen: Failed to save symptom entry:", e); Alert.alert('Storage Error', 'Could not save symptom entry.'); } };
  const deleteEntry = (idToDelete) => { const userId = profile?.user_id; if (!userId) { Alert.alert('Error', 'User not logged in.'); return; } const symptomProgressKey = getSymptomProgressKey(); const entryToDelete = (symptomProgress || []).find(e => e.id === idToDelete); if (!entryToDelete) { console.error("SymptomProgressScreen: Attempted to delete non-existent entry with id", idToDelete); return; } Alert.alert( "Delete Entry", `Delete the symptom entry from ${entryToDelete.date} at ${entryToDelete.time}?`, [ { text: "Cancel", style: "cancel" }, { text: "Delete", style: "destructive", onPress: async () => { const updated = (symptomProgress || []).filter(e => e.id !== idToDelete); try { await AsyncStorage.setItem(symptomProgressKey, JSON.stringify(updated)); setSymptomProgress(updated); Alert.alert('Success', 'Entry deleted.'); } catch (e) { console.error("SymptomProgressScreen: Failed to delete symptom entry:", e); Alert.alert('Storage Error', 'Could not delete entry.'); } } } ] ); };

  return (
    <SafeAreaView style={styles.container} edges={['bottom', 'left', 'right']}>
       <View style={styles.topBar}>
           <TouchableOpacity onPress={() => navigation.openDrawer()} style={styles.menuButton}>
               <Ionicons name="menu" size={scaleFont(28)} color="#1e3a8a" />
           </TouchableOpacity>
           <Text style={styles.headerTitle}>Symptom Progress</Text>
           <View style={styles.menuButtonPlaceholder}></View>
       </View>
      <ScrollView contentContainerStyle={styles.scrollContainer} keyboardShouldPersistTaps="handled">
        <View style={[styles.contentWrapper, { paddingTop: scaleSize(10) }]}>
          <Text style={styles.sectionTitle}>Symptom Progress Tracker</Text>
          <View style={styles.symptomInputForm}>
            <Text style={styles.label}>Add New Entry:</Text>
            <TextInput style={[styles.input, styles.multilineInput, { minHeight: scaleSize(80) }]} placeholder="Describe current symptoms... (e.g., Headache is mild today, fever is gone)" placeholderTextColor="#9ca3af" multiline value={newEntrySymptoms} onChangeText={setNewEntrySymptoms} textAlignVertical="top" editable={!isLoading}/>
            <Text style={styles.label}>Additional Notes (Optional):</Text>
            <TextInput style={[styles.input, styles.multilineInput, { minHeight: scaleSize(60) }]} placeholder="e.g., Took medication, temperature reading 99.5°F" placeholderTextColor="#9ca3af" multiline value={notes} onChangeText={setNotes} textAlignVertical="top" editable={!isLoading}/>
            <Text style={styles.label}>Current Status:</Text>
            <View style={styles.radioGroup}>
              {['ongoing', 'improving', 'recovered', 'escalate'].map(option => { const { icon, color, label } = getStatusDetails(option); const isActive = status === option; return ( <TouchableOpacity key={option} style={[ styles.radioOption, isActive && { backgroundColor: `${color}20`, borderColor: color, borderWidth: 1 } ]} onPress={() => setStatus(option)} activeOpacity={0.7} accessibilityLabel={`Set status to ${label}`} disabled={isLoading} > <Ionicons name={isActive ? 'radio-button-on' : 'radio-button-off'} size={scaleFont(20)} color={isActive ? color : '#64748b'}/> <Text style={[styles.radioLabel, isActive && { color: color, fontWeight: 'bold' }]}> {icon} {label} </Text> </TouchableOpacity> ); })}
            </View>
            <GradientButton title={isLoading ? "Adding..." : "Add Symptom Entry"} onPress={addEntry} disabled={!newEntrySymptoms.trim() || isLoading}/>
          </View>
          <Text style={[styles.sectionSubtitle, { marginTop: scaleSize(40) }]}>Progress Timeline</Text>
          {(symptomProgress || []).length > 0 ? ( <FlatList data={symptomProgress} keyExtractor={item => item.id.toString()} renderItem={({ item }) => { const { icon, color, label } = getStatusDetails(item.status); return ( <View key={item.id} style={[styles.historyItem, { borderLeftWidth: 4, borderLeftColor: color }]}> <View style={styles.historyContent}> <Text style={styles.historyTime}>{item.date} at {item.time}</Text> <Text style={[styles.historyQuery, { color: color, fontWeight: 'bold', marginBottom: scaleSize(8) }]}> {icon} Status: {label} </Text> <Text style={styles.historyQuery}> Symptoms: {item.symptoms} </Text> {item.notes && ( <Text style={[styles.historySummary, { marginTop: scaleSize(5), fontStyle: 'italic' }]}> Notes: {item.notes} </Text> )} </View> <TouchableOpacity style={styles.deleteItemButton} onPress={() => deleteEntry(item.id)} accessibilityLabel={`Delete symptom entry from ${item.date}`}> <Ionicons name="trash-outline" size={scaleFont(18)} color="#dc3545" /> </TouchableOpacity> </View> ); }} contentContainerStyle={{ paddingBottom: scaleSize(30) }} showsVerticalScrollIndicator={false} scrollEnabled={false}/> ) : ( <View style={styles.emptyView}> <Ionicons name="reader-outline" size={scaleFont(50)} color="#9ca3af" /> <Text style={[styles.emptyMessage, { marginTop: scaleSize(15) }]}> No symptom entries yet. </Text> <Text style={[styles.emptyMessage, { fontSize: scaleFont(14), marginTop: scaleSize(5) }]}> Use the form above to track your symptoms over time. </Text> </View> )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};


// Profile Screen (Direct Drawer Screen)
const ProfileScreen = ({ profile, setProfile, navigation }) => {
    const [name, setName] = useState(profile?.name || '');
    const [dob, setDob] = useState(profile?.dob || '');
    const [gender, setGender] = useState(profile?.gender || '');
    const [isSaving, setIsSaving] = useState(false);

    useEffect(() => { console.log("ProfileScreen: Profile prop updated, updating local state."); setName(profile?.name || ''); setDob(profile?.dob || ''); setGender(profile?.gender || ''); }, [profile]);

    const handleSaveProfile = async () => { const userId = profile?.user_id; if (!userId) { Alert.alert("Error", "User not logged in."); return; } setIsSaving(true); const updatedProfile = { ...profile, name: name.trim(), dob: dob.trim(), gender: gender.trim(), }; const profileKey = `profile_${userId}`; try { await AsyncStorage.setItem(profileKey, JSON.stringify(updatedProfile)); console.log("ProfileScreen: Profile saved to AsyncStorage."); setProfile(updatedProfile); Alert.alert("Success", "Profile saved!"); } catch (e) { console.error("ProfileScreen: Error saving profile to AsyncStorage:", e); Alert.alert("Storage Error", "Could not save profile locally."); setIsSaving(false); return; } try { const supabaseUpdateData = { name: updatedProfile.name, dob: updatedProfile.dob, gender: updatedProfile.gender, }; const { error } = await supabase .from('profiles') .upsert([ { id: userId, ...supabaseUpdateData } ], { onConflict: 'id' }) .select(); if (error) throw error; console.log("ProfileScreen: Profile saved to Supabase."); } catch (supabaseError) { console.error("ProfileScreen: Error saving profile to Supabase:", supabaseError); Alert.alert("Database Error", `Failed to save profile to database: ${supabaseError.message || supabaseError}`); } finally { setIsSaving(false); } };

    return (
        <SafeAreaView style={styles.container} edges={['bottom', 'left', 'right']}>
            <View style={styles.topBar}>
                <TouchableOpacity onPress={() => navigation.openDrawer()} style={styles.menuButton}>
                    <Ionicons name="menu" size={scaleFont(28)} color="#1e3a8a" />
                </TouchableOpacity>
                <Text style={styles.headerTitle}>Profile</Text>
                <View style={styles.menuButtonPlaceholder}></View>
            </View>
            <ScrollView contentContainerStyle={styles.scrollContainer}>
                <View style={[styles.contentWrapper, { paddingTop: scaleSize(10) }]}>
                    <Text style={styles.sectionTitle}>My Profile</Text>
                    <Text style={styles.label}>Name:</Text>
                    <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="Enter your name" editable={!isSaving}/>
                    <Text style={styles.label}>Date of Birth (MM/DD/YYYY):</Text>
                    <TextInput style={styles.input} value={dob} onChangeText={setDob} placeholder="e.g., 01/15/1990" editable={!isSaving} keyboardType="numbers-and-punctuation" maxLength={10}/>
                    <Text style={styles.label}>Gender:</Text>
                    <TextInput style={styles.input} value={gender} onChangeText={setGender} placeholder="Enter your gender" editable={!isSaving}/>
                    <GradientButton title={isSaving ? "Saving..." : "Save Profile"} onPress={handleSaveProfile} disabled={isSaving || !name.trim()} style={{ marginTop: scaleSize(20) }}/>
                     {!profile?.name && ( <Text style={[styles.subtleText, { textAlign: 'center', marginTop: scaleSize(15), fontSize: scaleFont(13) }]}> Completing your profile helps provide more personalized analysis. </Text> )}
                </View>
            </ScrollView>
        </SafeAreaView>
    );
};


// --- Part 3: Navigation Structure (Defined once) ---

// Drawer Content Component
const DrawerContent = (props) => {
  const { navigation } = props;
  const state = navigation.getState() || { routes: [], index: -1 };
  let focusedRouteName = null; let currentState = state;
  while (currentState && currentState.routes && currentState.routes.length > currentState.index && currentState.index >= 0) { const route = currentState.routes[currentState.index]; if (route.state && route.state.routes) { currentState = route.state; } else { focusedRouteName = route.name; break; } }
  const drawerItems = [ { name: 'Home', icon: 'home', screen: 'HomeTabs' }, { name: 'Medication Reminders', icon: 'alarm', screen: 'MedicationScreen' }, { name: 'History', icon: 'archive', screen: 'HomeTabs' }, { name: 'Health Tips', icon: 'information-circle', screen: 'HomeTabs' }, { name: 'Appointments', icon: 'calendar', screen: 'AppointmentsScreen' }, { name: 'Symptom Progress', icon: 'trending-up', screen: 'SymptomProgressScreen' }, { name: 'Profile', icon: 'person', screen: 'ProfileScreen' }, { name: 'Logout', icon: 'log-out', action: async () => { await supabase.auth.signOut(); } } ];

  return (
    <SafeAreaView style={styles.drawerContainer}>
      <View style={styles.drawerHeader}>
        <Image source={{ uri: 'https://via.placeholder.com/60?text=User' }} style={styles.drawerAvatar} resizeMode="contain"/>
        <Text style={styles.drawerHeaderText}>Health Assistant</Text>
        <Text style={styles.drawerSubText}>Your Personal Care Companion</Text>
      </View>
      <ScrollView style={{ flex: 1 }}>
        {drawerItems.map((item, idx) => { const isFocused = focusedRouteName === item.name; return (
              <TouchableOpacity key={idx} style={[ styles.drawerItem, isFocused && { backgroundColor: '#e0f2fe' } ]} onPress={() => { if (item.action) { item.action(); } else { if (item.screen === 'HomeTabs') { navigation.navigate(item.screen, { screen: item.name }); } else { navigation.navigate(item.screen); } navigation.closeDrawer(); } }} activeOpacity={0.7} >
                <Ionicons name={item.icon} size={scaleFont(24)} color={isFocused ? '#0052cc' : '#1e3a8a'}/>
                <Text style={[ styles.drawerItemText, isFocused && { color: '#0052cc' } ]}> {item.name} </Text>
              </TouchableOpacity> ); })}
      </ScrollView>
    </SafeAreaView>
  );
};


// Tab Navigator for Home, History, and Health Tips
const HomeTabs = (props) => {
  const { profile, history, setHistory, chatMedications, setChatMedications, favoriteTips, toggleFavoriteTip } = props;
  return (
    <Tab.Navigator screenOptions={({ route }) => ({ headerShown: false, tabBarIcon: ({ focused, color, size }) => { let iconName; if (route.name === 'Home') { iconName = focused ? 'home' : 'home-outline'; } else if (route.name === 'History') { iconName = focused ? 'archive' : 'archive-outline'; } else if (route.name === 'Health Tips') { iconName = focused ? 'information-circle' : 'information-circle-outline'; } return <Ionicons name={iconName} size={scaleFont(size)} color={color} />; }, tabBarActiveTintColor: '#0052cc', tabBarInactiveTintColor: '#64748b', tabBarStyle: { backgroundColor: '#ffffff', borderTopColor: '#e5e7eb', borderTopWidth: 1, paddingBottom: scaleSize(5), paddingTop: scaleSize(5), height: scaleSize(Platform.OS === 'ios' ? 80 : 60) }, tabBarLabelStyle: { fontSize: scaleFont(12), marginBottom: scaleSize(5) } })}>
      <Tab.Screen name="Home"> {(tabProps) => ( <ChatScreen {...tabProps} profile={profile} history={history} setHistory={setHistory} chatMedications={chatMedications} setChatMedications={setChatMedications}/> )}</Tab.Screen>
      <Tab.Screen name="History"> {(tabProps) => ( <HistoryScreen {...tabProps} history={history} setHistory={setHistory} profile={profile}/> )}</Tab.Screen>
      <Tab.Screen name="Health Tips"> {(tabProps) => ( <HealthTipsScreen {...tabProps} favoriteTips={favoriteTips} toggleFavoriteTip={toggleFavoriteTip} profile={profile}/> )}</Tab.Screen>
    </Tab.Navigator>
  );
}


// Main App Navigator with Drawer
const MainApp = ({
  profile, setProfile,
  history, setHistory,
  chatMedications, setChatMedications,
  favoriteTips, setFavoriteTips,
  reminders, setReminders,
  appointments, setAppointments,
  symptomProgress, setSymptomProgress,
  toggleFavoriteTip
}) => (
  <Drawer.Navigator drawerContent={(props) => <DrawerContent {...props} />} screenOptions={{ headerShown: false, drawerStyle: { width: width * 0.75 }, drawerType: 'slide', swipeEdgeWidth: 50 }}>
    <Drawer.Screen name="HomeTabs"> {(props) => ( <HomeTabs {...props} profile={profile} history={history} setHistory={setHistory} chatMedications={chatMedications} setChatMedications={setChatMedications} favoriteTips={favoriteTips} toggleFavoriteTip={toggleFavoriteTip}/> )}</Drawer.Screen>
    <Drawer.Screen name="MedicationScreen"> {(props) => ( <MedicationScreen {...props} medicationsFromChat={chatMedications} reminders={reminders} setReminders={setReminders} profile={profile}/> )}</Drawer.Screen>
     <Drawer.Screen name="ProfileScreen"> {(props) => ( <ProfileScreen {...props} profile={profile} setProfile={setProfile}/> )}</Drawer.Screen>
    <Drawer.Screen name="AppointmentsScreen"> {(props) => ( <AppointmentsScreen {...props} appointments={appointments} setAppointments={setAppointments} profile={profile}/> )}</Drawer.Screen>
    <Drawer.Screen name="SymptomProgressScreen"> {(props) => ( <SymptomProgressScreen {...props} symptomProgress={symptomProgress} setSymptomProgress={setSymptomProgress} profile={profile}/> )}</Drawer.Screen>
  </Drawer.Navigator>
);


// --- Part 4: Authentication and Onboarding Screens (Defined once) ---

// Login Screen
const LoginScreen = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleLogin = async () => { setLoading(true); setError(null); if (!email || !password) { setError("Please enter both email and password."); setLoading(false); return; } try { const { error: signInError } = await supabase.auth.signInWithPassword({ email, password }); if (signInError) throw signInError; console.log('LoginScreen: User logged in successfully'); } catch (err) { console.error('LoginScreen: Login error:', err.message); setError(err.message || 'Login failed. Please try again.'); if (err.message.includes('Invalid login credentials')) { setError('Invalid email or password.'); } } finally { setLoading(false); } };

  const handleSignUp = async () => { setLoading(true); setError(null); if (!email || !password) { setError("Please enter both email and password for sign up."); setLoading(false); return; } if (password.length < 6) { setError("Password should be at least 6 characters."); setLoading(false); return; } try { const { data: { user }, error: signUpError } = await supabase.auth.signUp({ email, password }); if (signUpError) throw signUpError; if (user) { console.log('LoginScreen: User signed up successfully:', user.id); Alert.alert('Sign Up Successful', 'Account created successfully! Please log in.'); } else { console.log('LoginScreen: Sign up successful, email confirmation likely required.'); Alert.alert('Sign Up Successful', 'Account created! Please check your email for a confirmation link, then log in.'); } } catch (err) { console.error('LoginScreen: Sign-up error:', err.message); setError(err.message || 'Sign-up failed. Please try again.'); if (err.message.includes('already registered')) { setError('An account with this email already exists. Please log in instead.'); } else if (err.message.includes('Password should be')) { setError(err.message); } } finally { setLoading(false); } };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContainer}>
        <View style={styles.contentWrapper}>
          <Image source={{ uri: 'https://via.placeholder.com/120?text=Logo' }} style={styles.logo} resizeMode="contain"/>
          <Text style={styles.tagline}>Your Health, Our Priority</Text>
          <Text style={styles.sectionTitle}>Welcome Back</Text>
          {error && ( <Text style={[styles.errorText, { marginBottom: scaleSize(15) }]}> {error} </Text> )}
          <Text style={styles.label}>Email</Text>
          <TextInput style={styles.input} value={email} onChangeText={setEmail} placeholder="Enter your email" keyboardType="email-address" autoCapitalize="none" autoCorrect={false} editable={!loading}/>
          <Text style={styles.label}>Password</Text>
          <TextInput style={styles.input} value={password} onChangeText={setPassword} placeholder="Enter your password" secureTextEntry autoCapitalize="none" autoCorrect={false} editable={!loading}/>
          <GradientButton title={loading ? "Loading..." : "Log In"} onPress={handleLogin} disabled={loading || !email || !password} style={{ marginTop: scaleSize(20) }}/>
          <GradientButton title={loading ? "Loading..." : "Sign Up"} onPress={handleSignUp} colors={['#16a34a', '#22c55e']} disabled={loading || !email || !password || password.length < 6} style={{ marginTop: scaleSize(15) }}/>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};


// Warning Screen
const WarningScreen = ({ onContinue }) => (
  <SafeAreaView style={styles.container}>
    <ScrollView contentContainerStyle={styles.scrollContainer}>
      <View style={styles.contentWrapper}>
        <Image source={{ uri: 'https://via.placeholder.com/120?text=Logo' }} style={styles.logo} resizeMode="contain"/>
        <Text style={styles.tagline}>Important Information</Text>
        <View style={styles.introContainer}>
          <Text style={styles.sectionTitle}>Disclaimer</Text>
          <Text style={styles.warningText}> This app provides general health information and analysis based on user input. It is not a substitute for professional medical advice, diagnosis, or treatment. </Text>
          <Text style={styles.warningText}> Always seek the advice of your physician or other qualified health provider with any questions you may have regarding a medical condition. </Text>
          <Text style={styles.warningText}> In case of a medical emergency, call your local emergency services immediately. </Text>
          <GradientButton title="I Understand, Continue" onPress={onContinue} style={styles.introButton}/>
        </View>
      </View>
    </ScrollView>
  </SafeAreaView>
);


// Intro Screen
const IntroScreen = ({ onComplete }) => {
  const [step, setStep] = useState(1);
  const steps = [ { title: 'Welcome to Health Assistant', description: 'Your personal companion for health analysis and wellness tracking. Let\'s get started with a quick tour.' }, { title: 'Analyze Symptoms & Reports', description: 'Easily analyze your symptoms or upload lab reports to get detailed medical insights and suggestions.' }, { title: 'Track Your Health', description: 'Set medication reminders, book appointments, track symptom progress, and access personalized health tips.' } ];
  const handleNext = () => { if (step < steps.length) { setStep(step + 1); } else { onComplete(); } };
  const handleSkip = () => { onComplete(); };
  const currentStepData = steps[step - 1];

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContainer}>
        <View style={styles.contentWrapper}>
          <Image source={{ uri: 'https://via.placeholder.com/120?text=Logo' }} style={styles.logo} resizeMode="contain"/>
          <Text style={styles.tagline}>Health Assistant</Text>
          <View style={styles.introContainer}>
            <Text style={styles.sectionTitle}>{currentStepData.title}</Text>
            <View style={styles.introContainer}>
              <Text style={styles.introText}>{currentStepData.description}</Text>
              <View style={styles.buttonRow}>
                {step < steps.length ? ( <> <GradientButton title="Skip" onPress={handleSkip} colors={['#6b7280', '#9ca3af']} style={{ flex: 1, marginRight: scaleSize(8) }}/> <GradientButton title="Next" onPress={handleNext} style={{ flex: 1 }}/> </> ) : ( <GradientButton title="Get Started" onPress={handleNext} style={styles.introButton}/> )}
              </View>
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: scaleSize(20) }}>
              {steps.map((_, index) => ( <View key={index} style={{ width: scaleSize(8), height: scaleSize(8), borderRadius: scaleSize(4), backgroundColor: step === index + 1 ? '#0052cc' : '#d1d5db', marginHorizontal: scaleSize(5) }} /> ))}
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};


// --- Part 5: Main App Component and Styles ---

// Main App Component
// This is the top-level component that manages global state, authentication,
// data loading, and orchestrates the primary navigation flow.
const App = () => {
  // --- Top-Level State Management ---
  // Authentication State
  const [session, setSession] = useState(null); // Stores the current Supabase session (null if logged out)
  const [authLoading, setAuthLoading] = useState(true); // Indicates if the initial auth check is in progress (true on first app launch)

  // User Data State (loaded after authentication)
  const [profile, setProfile] = useState(DEFAULT_PROFILE); // User profile data. Initial state is the default structure.
  const [history, setHistory] = useState([]); // User's analysis history. Initial state is an empty array.
  const [reminders, setReminders] = useState([]); // Medication reminders. Initial state is an empty array.
  const [chatMedications, setChatMedications] = useState([]); // Medications identified in chat/analysis. Initial state is an empty array.
  const [favoriteTips, setFavoriteTips] = useState([]); // User's favorite health tips. Initial state is an empty array.
  const [appointments, setAppointments] = useState([]); // User's appointments. Initial state is an empty array.
  const [symptomProgress, setSymptomProgress] = useState([]); // User's symptom progress entries. Initial state is an empty array.

  // Onboarding State (Determines which initial screen to show after login)
  const [hasSeenWarning, setHasSeenWarning] = useState(false); // Flag for the medical disclaimer screen
  const [hasSeenIntro, setHasSeenIntro] = useState(false); // Flag for the app introduction tour screen

  // Data Loading State (after authentication, for user-specific data)
  const [appLoading, setAppLoading] = useState(false); // Indicates if user data is currently being loaded (true when `initializeApp` is running)
  const [loadingError, setLoadingError] = useState(null); // Stores any error that occurred during data loading
  const [isInitializing, setIsInitializing] = useState(false); // Internal flag to prevent multiple concurrent `initializeApp` calls


  // --- Initial Setup Effects ---

  // Effect 1: Request notification permissions once on mount.
  useEffect(() => {
    if (__DEV__) {
      console.log('App: Environment: Development');
    }
    requestNotificationPermissions();
  }, []); // Empty dependency array means run once on mount


  // Effect 2: Load user preference flags (seen warning/intro) from AsyncStorage once on mount.
  useEffect(() => {
    const checkInitialPreferences = async () => {
      try {
        const [warningSeen, introSeen] = await Promise.all([
          AsyncStorage.getItem('hasSeenWarning'),
          AsyncStorage.getItem('hasSeenIntro')
        ]);

        setHasSeenWarning(warningSeen === 'true');
        setHasSeenIntro(introSeen === 'true');
        console.log(`App: Initial preferences loaded: Warning Seen: ${warningSeen === 'true'}, Intro Seen: ${introSeen === 'true'}`);
      } catch (error) {
        console.error('App: Error loading preferences from AsyncStorage:', error);
      }
    };

    checkInitialPreferences();
  }, []); // Empty dependency array means run once on mount


  // --- Core Data Loading Logic (initializeApp function) ---

  // initializeApp function (memoized with useCallback)
  // This function is responsible for ASYNCHRONOUSLY loading ALL user-specific data
  // from AsyncStorage and/or Supabase for a given userId.
  // IMPORTANT: It DOES NOT SET STATE DIRECTLY within its async logic.
  // It returns an object containing all the loaded data, which the calling effect
  // will then use to update the state.
  // It uses the `isInitializing` flag internally to prevent multiple concurrent calls.
  const initializeApp = useCallback(async (userId) => {
    if (!userId) {
      console.error("App: initializeApp called without userId");
      throw new Error("User ID missing for initialization.");
    }
    if (isInitializing) {
       console.log("App: initializeApp already in progress for user:", userId, "skipping redundant call.");
       return null;
    }

    setIsInitializing(true);
    console.log("App: Starting initializeApp for user:", userId);

    let loadError = null;

    try {
      // --- Profile Loading Logic ---
      let loadedProfile = { ...DEFAULT_PROFILE, user_id: userId };
      const profileKey = `profile_${userId}`;

      const storedProfileJson = await AsyncStorage.getItem(profileKey);
      if (storedProfileJson) {
        try {
          const parsedProfile = JSON.parse(storedProfileJson);
          if (parsedProfile && typeof parsedProfile === 'object' && parsedProfile.user_id === userId) {
            console.log(`App: Loaded profile from AsyncStorage for user ${userId}.`);
            loadedProfile = {
               ...DEFAULT_PROFILE,
               ...parsedProfile,
               user_id: userId,
               lifestyle: { ...DEFAULT_PROFILE.lifestyle, ...(parsedProfile.lifestyle || {}) },
               biometrics: { ...DEFAULT_PROFILE.biometrics, ...(parsedProfile.biometrics || {}) },
               emergencyContact: { ...DEFAULT_PROFILE.emergencyContact, ...(parsedProfile.emergencyContact || {}) },
               conditions: Array.isArray(parsedProfile.conditions) ? parsedProfile.conditions : [],
               allergies: Array.isArray(parsedProfile.allergies) ? parsedProfile.allergies : [],
               medications: Array.isArray(parsedProfile.medications) ? parsedProfile.medications : [],
               medicalHistory: Array.isArray(parsedProfile.medicalHistory) ? parsedProfile.medicalHistory : [],
               familyHistory: Array.isArray(parsedProfile.familyHistory) ? parsedProfile.familyHistory : [],
               name: parsedProfile.name || '',
               gender: parsedProfile.gender || '',
               vaccinationHistory: parsedProfile.vaccinationHistory || '',
               bloodType: parsedProfile.bloodType || '',
               state: parsedProfile.state || '',
               dob: parsedProfile.dob || null,
               age: parsedProfile.age != null ? String(parsedProfile.age) : '',
             };
          } else {
            console.warn(`App: Invalid or outdated stored profile for user ${userId}, ignoring and removing.`);
            await AsyncStorage.removeItem(profileKey).catch(e => console.error("App: Error removing invalid profile:", e));
          }
        } catch (e) {
          console.error(`App: Parse profile error for user ${userId}:`, e);
          await AsyncStorage.removeItem(profileKey).catch(e => console.error("App: Error removing corrupted profile:", e));
        }
      }

       console.log(`App: Fetching profile from Supabase for user ${userId}...`);
       let supabaseProfile = null;
       let supabaseFetchError = null;
       let attempts = 0;
       const maxAttempts = 3;

       while (attempts < maxAttempts && supabaseProfile === null && !supabaseFetchError) {
         try {
           const { data, error } = await supabase.from('profiles').select('*').eq('id', userId).maybeSingle();
           if (error) throw error;
           supabaseProfile = data;
           console.log(`App: Supabase profile fetch successful (attempt ${attempts + 1}). Data exists: ${!!supabaseProfile}`);
           break;
         } catch (supabaseError) {
           attempts++;
           console.error(`App: Supabase profile fetch attempt ${attempts} failed for user ${userId}:`, supabaseError.message || supabaseError);
           if (attempts >= maxAttempts) {
              supabaseFetchError = supabaseError;
              console.error('App: Max Supabase fetch attempts reached.');
           } else {
              console.log(`App: Retrying Supabase profile fetch in 2 seconds...`);
              await new Promise(resolve => setTimeout(resolve, 2000));
           }
         }
       }

       if (supabaseProfile) {
         console.log(`App: Profile fetched from Supabase for user ${userId}. Mapping and merging.`);
         const mappedProfile = {
           ...DEFAULT_PROFILE,
           user_id: userId,
           name: supabaseProfile.name || '',
           dob: supabaseProfile.dob || null,
           gender: supabaseProfile.gender || '',
           age: supabaseProfile.age != null ? String(supabaseProfile.age) : '',
           conditions: supabaseProfile.conditions ? supabaseProfile.conditions.split(',').map(s => s.trim()).filter(Boolean) : [],
           allergies: supabaseProfile.allergies ? supabaseProfile.allergies.split(',').map(s => s.trim()).filter(Boolean) : [],
           medications: supabaseProfile.medications ? supabaseProfile.medications.split(',').map(s => s.trim()).filter(Boolean) : [],
           medicalHistory: supabaseProfile.medical_history ? supabaseProfile.medical_history.split(',').map(s => s.trim()).filter(Boolean) : [],
           familyHistory: supabaseProfile.family_history ? supabaseProfile.family_history.split(',').map(s => s.trim()).filter(Boolean) : [],
           vaccinationHistory: supabaseProfile.vaccination_history || '',
           bloodType: supabaseProfile.blood_type || '',
           lifestyle: {
             ...DEFAULT_PROFILE.lifestyle,
             smoker: supabaseProfile.lifestyle_smoker ?? false,
             alcohol: supabaseProfile.lifestyle_alcohol || '',
             exercise: supabaseProfile.lifestyle_exercise || '',
             dietaryNotes: supabaseProfile.lifestyle_dietary_notes || ''
           },
           biometrics: {
             ...DEFAULT_PROFILE.biometrics,
             height: supabaseProfile.biometrics_height || '',
             weight: supabaseProfile.biometrics_weight || ''
           },
           emergencyContact: {
             ...DEFAULT_PROFILE.emergencyContact,
             name: supabaseProfile.emergency_contact_name || '',
             relationship: supabaseProfile.emergency_contact_relationship || '',
             phone: supabaseProfile.emergency_contact_phone || ''
           },
           state: supabaseProfile.state || '',
         };
         loadedProfile = mappedProfile;
         await AsyncStorage.setItem(profileKey, JSON.stringify(loadedProfile)).catch(e => console.error("App: Error saving Supabase profile to AsyncStorage:", e));
         console.log('App: Fetched/Merged profile saved to AsyncStorage.');

       } else if (storedProfileJson) {
          console.warn(`App: No profile found in Supabase for user ${userId} but one exists in AsyncStorage. Using AsyncStorage data.`);
       } else {
           console.log(`App: No profile found in Supabase or AsyncStorage for user ${userId}. Using default structure.`);
           loadedProfile = { ...DEFAULT_PROFILE, user_id: userId };
       }

       if(supabaseFetchError) {
            console.error("App: Supabase profile could not be fetched. Proceeding with local/default profile.");
            loadError = (loadError ? loadError + '; ' : '') + `Profile fetch failed: ${supabaseFetchError.message || supabaseFetchError}`;
       }


      // --- Load other persisted data using local variables ---
      const loadPersistedDataLocal = async (key, defaultValue = [], customMapper = null) => {
        const userKey = `${key}_${userId}`;
        let dataLoadError = null;
        try {
          const storedData = await AsyncStorage.getItem(userKey);
          let parsedData = storedData !== null ? JSON.parse(storedData) : defaultValue;

          if (Array.isArray(defaultValue) && !Array.isArray(parsedData)) {
            console.warn(`App: Invalid data format for ${key} for user ${userId}, resetting to default.`);
            parsedData = defaultValue;
            await AsyncStorage.removeItem(userKey).catch(e => console.error(`App: Error removing invalid ${key} data:`, e));
             dataLoadError = `Invalid data for ${key}`;
          }

          if (customMapper && Array.isArray(parsedData)) {
              parsedData = parsedData.map(item => customMapper(item));
          }
          console.log(`App: Loaded ${key} for user ${userId}.`);
          return { data: parsedData, error: dataLoadError };
        } catch (e) {
          console.error(`App: Load/parse error for ${key} for user ${userId}:`, e);
          await AsyncStorage.removeItem(userKey).catch(e => console.error(`App: Error removing corrupted ${key} data:`, e));
           dataLoadError = `Load error for ${key}: ${e.message || e}`;
          return { data: defaultValue, error: dataLoadError };
        }
      };

      const results = await Promise.all([
        loadPersistedDataLocal('history', []),
        loadPersistedDataLocal('chatMedications', []),
        loadPersistedDataLocal('favoriteTips', []),
        loadPersistedDataLocal('reminders', []),
        loadPersistedDataLocal('appointments', []),
        loadPersistedDataLocal('symptomProgress', []),
      ]);

      const loadedHistory = results[0].data;
      const loadedChatMedications = results[1].data;
      const loadedFavoriteTips = results[2].data;
      const loadedReminders = results[3].data;
      const loadedAppointments = results[4].data;
      const loadedSymptomProgress = results[5].data;

       const dataErrors = results.map(r => r.error).filter(Boolean);
       if (dataErrors.length > 0) {
           loadError = (loadError ? loadError + '; ' : '') + 'Data loading issues: ' + dataErrors.join(', ');
       }


      console.log(`App: initializeApp data loading complete for user ${userId}. Final loadError: ${loadError}`);

      return {
          profile: loadedProfile,
          history: loadedHistory,
          chatMedications: loadedChatMedications,
          favoriteTips: loadedFavoriteTips,
          reminders: loadedReminders,
          appointments: loadedAppointments,
          symptomProgress: loadedSymptomProgress,
          loadError: loadError
      };

    } catch (error) {
      console.error(`App: UNEXPECTED CRITICAL initializeApp error for user ${userId}:`, error);
      return {
          profile: { ...DEFAULT_PROFILE, user_id: userId },
          history: [],
          chatMedications: [],
          favoriteTips: [],
          reminders: [],
          appointments: [],
          symptomProgress: [],
          loadError: `Critical initialization error: ${error.message || error}`
      };
    } finally {
      setIsInitializing(false);
      console.log("App: initializeApp finished execution.");
    }
  }, [isInitializing]); // Dependency: isInitializing to control re-entry


  // --- Authentication State Handling and Data Loading Effect ---

  // Effect 3: Handle initial Supabase session check and listen for auth state changes.
  // Runs once on mount to set up session state and listener.
  useEffect(() => {
    console.log("App: --- Effect 3: Initial auth check useEffect running ---");
    setAuthLoading(true);

    supabase.auth.getSession().then(({ data: { session: currentSession } }) => {
      console.log("App: Effect 3: Initial getSession completed. Session:", currentSession ? `Exists for user ${currentSession.user.id}` : "None");
      setSession(currentSession);
    }).catch(err => {
      console.error("App: Effect 3: Error getting initial session:", err);
      setSession(null);
    }).finally(() => {
      console.log("App: Effect 3: Initial getSession finally block. Setting authLoading(false).");
      setAuthLoading(false);
    });

    const { data: authListener } = supabase.auth.onAuthStateChange((_event, currentSession) => {
      console.log("App: Effect 3: Auth state changed listener event:", _event, currentSession ? `User ${currentSession.user.id}` : "No user");
      setSession(currentSession);
    });

    return () => {
      console.log("App: Effect 3: useEffect cleanup.");
       if (authListener?.subscription) {
           console.log("App: Effect 3: Unsubscribing Supabase auth listener.");
           authListener.subscription.unsubscribe();
       }
    };
  }, []); // Empty dependency array = runs once


  // Effect 4: Handle actions *after* authentication state is known (when `session` changes).
  // Responsible for triggering data loading or state reset.
  useEffect(() => {
      const currentUserId = session?.user?.id;
      const previousUserId = profile?.user_id;
      console.log(`App: --- Effect 4: handleAuthAndLoadData effect running ---. session user: ${currentUserId}, profile user: ${previousUserId}, isInitializing: ${isInitializing}, appLoading: ${appLoading}`);


      const resetUserDataStates = () => {
          console.log("App: Effect 4: Resetting user data states.");
          setProfile(DEFAULT_PROFILE);
          setHistory([]);
          setReminders([]);
          setChatMedications([]);
          setFavoriteTips([]);
          setAppointments([]);
          setSymptomProgress([]);
          setLoadingError(null);
      };

      // --- Case 1: User is logged in (session is not null) ---
      if (currentUserId) {
         // Trigger data initialization if:
         // a) New user logged in (currentUserId !== previousUserId) OR
         // b) Profile data seems missing for the current user (e.g., on initial load after auth) AND
         // c) Initialization is not already in progress (`!isInitializing`)
         if ((currentUserId !== previousUserId || !profile?.name) && !isInitializing) { // Added !profile?.name check
            console.log(`App: Effect 4: User ${currentUserId} logged in or changed from ${previousUserId}. Resetting state and initiating data initialization.`);
            resetUserDataStates(); // Reset states *before* loading new data

            setAppLoading(true); // Indicate data loading is starting
            initializeApp(currentUserId)
                .then(loadedData => {
                    if (loadedData !== null) {
                        console.log("App: Effect 4: initializeApp promise resolved. Updating states.");
                        setProfile(loadedData.profile);
                        setHistory(loadedData.history);
                        setReminders(loadedData.reminders);
                        setChatMedications(loadedData.chatMedications);
                        setFavoriteTips(loadedData.favoriteTips);
                        setAppointments(loadedData.appointments);
                        setSymptomProgress(loadedData.symptomProgress);
                        setLoadingError(loadedData.loadError || null);

                    } else {
                         console.log("App: Effect 4: initializeApp promise resolved but returned null (was skipped). Waiting for existing init to finish.");
                    }
                })
                .catch(err => {
                    console.error("App: Effect 4: initializeApp promise rejected unexpectedly:", err);
                    setLoadingError(`Critical error during data initialization: ${err.message || err}`);
                })
                .finally(() => {
                    console.log("App: Effect 4: initializeApp promise chain finished. Setting appLoading(false).");
                    setAppLoading(false);
                });

         } else if (currentUserId === previousUserId) {
             console.log(`App: Effect 4: User ${currentUserId} is the same as current profile user (${previousUserId}).`);
             if (!isInitializing && appLoading) {
                console.log("App: Effect 4: Same user, initialization not running, appLoading stuck true? Forcing appLoading(false).");
                setAppLoading(false);
                setLoadingError(null);
             } else if (!isInitializing && !appLoading) {
                console.log("App: Effect 4: Same user, initialization not running, app is already loaded and ready.");
             } else if (isInitializing) {
                console.log("App: Effect 4: Same user, initialization is already in progress. Waiting for it to finish.");
             }
         }

      }
      // --- Case 2: User is logged out (session is null) ---
      else { // session is null
         console.log("App: Effect 4: Session is null. Handling logged out state.");
         if (previousUserId !== null) {
            console.log(`App: Effect 4: User was logged in (${previousUserId}), now logged out. Resetting app state to default.`);
            resetUserDataStates();
         }

       if (appLoading || isInitializing) {
           console.log("App: Effect 4: Logged out, ensuring app is not loading data.");
           setAppLoading(false);
           setIsInitializing(false);
           setLoadingError(null);
       }
       console.log("App: Effect 4: App state is default (logged out).");
      }

  }, [session, profile?.user_id, isInitializing, appLoading, initializeApp, setProfile, setHistory, setReminders, setChatMedications, setFavoriteTips, setAppointments, setSymptomProgress, setLoadingError]); // Dependencies


   // Helper function to toggle favorite status of a health tip.
   const toggleFavoriteTip = useCallback((tipId) => {
     setFavoriteTips(prevFavorites => {
       const userId = session?.user?.id;
       if (!userId) {
         Alert.alert('Error', 'User not logged in, cannot update favorites.');
         return prevFavorites;
       }
       const favoritesKey = `favoriteTips_${userId}`;
       let updatedFavorites;
       if (prevFavorites.includes(tipId)) {
         updatedFavorites = prevFavorites.filter(id => id !== tipId);
       } else {
         updatedFavorites = [...prevFavorites, tipId];
       }
       AsyncStorage.setItem(favoritesKey, JSON.stringify(updatedFavorites)).catch(e => {
         console.error('App: Failed to save favorite tips:', e);
       });
       return updatedFavorites;
     });
   }, [session?.user?.id, setFavoriteTips]);


  // --- Render Logic ---
  // This section determines which top-level screen/navigator to render based on the current state.

  // Render the loading screen if:
  // 1. The initial authentication check is in progress (`authLoading` is true).
  // 2. A user is logged in (`session` exists) AND user data is being loaded (`appLoading` is true).
  if (authLoading || (session && appLoading)) {
    console.log(`App: Deciding Render: SHOWING LOADING SCREEN. authLoading: ${authLoading}, session: ${session ? 'Exists' : 'None'}, appLoading: ${appLoading}, isInitializing: ${isInitializing}`);
    return (
      <GestureHandlerRootView style={{ flex: 1 }}>
        <SafeAreaProvider>
          <SafeAreaView style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#0052cc" />
            <Text style={styles.loadingText}>
               {authLoading ? 'Authenticating...' : (session ? 'Loading your health data...' : 'Loading...')}
            </Text>
            {loadingError && <Text style={styles.errorText}>{loadingError}</Text>}
          </SafeAreaView>
        </SafeAreaProvider>
      </GestureHandlerRootView>
    );
  }

   // If `authLoading` is false and there is no active `session`, render the Login screen.
   if (!session) {
      console.log(`App: Deciding Render: SHOWING LOGIN SCREEN. session: ${session ? 'Exists' : 'None'}, authLoading: ${authLoading}, appLoading: ${appLoading}`);
       return (
         <GestureHandlerRootView style={{ flex: 1 }}>
           <SafeAreaProvider>
              <LoginScreen />
           </SafeAreaProvider>
         </GestureHandlerRootView>
       );
   }

   // If a session exists (user is logged in), AND auth/app loading is complete, check onboarding.
   console.log(`App: Deciding Render: LOGGED IN, DATA LOADED. hasSeenWarning: ${hasSeenWarning}, hasSeenIntro: ${hasSeenIntro}`);

   // Render the Warning screen if the user hasn't seen it.
   if (!hasSeenWarning) {
       return (
         <GestureHandlerRootView style={{ flex: 1 }}>
           <SafeAreaProvider>
              <WarningScreen onContinue={async () => {
                try {
                  await AsyncStorage.setItem('hasSeenWarning', 'true');
                  setHasSeenWarning(true);
                } catch (e) {
                  console.error("App: Error saving warning preference to AsyncStorage:", e);
                  Alert.alert("Error", "Failed to save preference locally. You may see this screen again.");
                  setHasSeenWarning(true);
                }
              }} />
           </SafeAreaProvider>
         </GestureHandlerRootView>
       );
   }

   // Render the Intro screen if the user hasn't seen it yet (and has seen the warning).
   if (!hasSeenIntro) {
       return (
         <GestureHandlerRootView style={{ flex: 1 }}>
           <SafeAreaProvider>
              <IntroScreen onComplete={async () => {
                try {
                  await AsyncStorage.setItem('hasSeenIntro', 'true');
                  setHasSeenIntro(true);
                } catch (e) {
                  console.error("App: Error saving intro preference to AsyncStorage:", e);
                  Alert.alert("Error", "Failed to save preference locally. You may see this screen again.");
                  setHasSeenIntro(true);
                }
              }} />
           </SafeAreaProvider>
         </GestureHandlerRootView>
       );
   }

   // If the user is logged in AND has completed both onboarding steps, render the main application navigator.
   console.log("App: Deciding Render: SHOWING MAIN APP NAVIGATION.");
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <NavigationContainer>
          <Stack.Navigator screenOptions={{ headerShown: false }}>
             <Stack.Screen name="MainApp">
                {() => (
                  <MainApp
                    profile={profile}
                    setProfile={setProfile}
                    history={history}
                    setHistory={setHistory}
                    chatMedications={chatMedications}
                    setChatMedications={setChatMedications}
                    favoriteTips={favoriteTips}
                    setFavoriteTips={setFavoriteTips}
                    reminders={reminders}
                    setReminders={setReminders}
                    appointments={appointments}
                    setAppointments={setAppointments}
                    symptomProgress={symptomProgress}
                    setSymptomProgress={setSymptomProgress}
                    toggleFavoriteTip={toggleFavoriteTip}
                  />
                )}
              </Stack.Screen>
           </Stack.Navigator>
        </NavigationContainer>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
};


// --- Complete Stylesheet (Defined once at the end) ---
const styles = StyleSheet.create({
  // Overall container style for screens
  container: {
    flex: 1,
    backgroundColor: '#f8fafc', // Light grey background
  },
  // Styles for the loading screen container
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f8fafc', // Light grey background
  },
  // Styles for the text message on the loading screen
  loadingText: {
    marginTop: scaleSize(16),
    fontSize: scaleFont(16),
    color: '#1e3a8a', // Dark blue text
  },
  // Styles for displaying error messages
  errorText: {
    color: '#dc2626', // Red text color
    marginTop: scaleSize(20),
    textAlign: 'center',
    fontSize: scaleFont(16),
    fontWeight: '600',
    paddingHorizontal: scaleSize(20),
  },
  // Styles for the content container of ScrollViews
  scrollContainer: {
    flexGrow: 1, // Allows content to grow and enable scrolling
    paddingBottom: scaleSize(30), // Add padding at the bottom of the scrollable content
  },
  // Styles for the main wrapper View that contains screen content (provides padding and optional max-width)
  contentWrapper: {
    paddingHorizontal: scaleSize(20), // Horizontal padding
    paddingVertical: scaleSize(10), // Vertical padding
    maxWidth: 700, // Optional max width for larger screens
    alignSelf: 'center', // Center the wrapper if max width is used
    width: '100%', // Take full width up to max width
  },
  // Styles for the Drawer container itself
  drawerContainer: {
    flex: 1,
    backgroundColor: '#ffffff', // White background
  },
  // Styles for the header section inside the Drawer
  drawerHeader: {
    paddingVertical: scaleSize(30),
    paddingHorizontal: scaleSize(20),
    backgroundColor: '#0052cc', // Blue background
    alignItems: 'flex-start', // Align items to the start (left)
  },
  // Styles for the user avatar image in the drawer header
  drawerAvatar: {
    width: scaleSize(60),
    height: scaleSize(60),
    borderRadius: scaleSize(30), // Make it round
    marginBottom: scaleSize(15),
    backgroundColor: '#e0e7ff', // Light blue placeholder background color
  },
  // Styles for the main text (App name) in the Drawer header
  drawerHeaderText: {
    fontSize: scaleFont(20),
    fontWeight: 'bold',
    color: '#ffffff', // White text color
  },
  // Styles for the subtext (tagline) in the Drawer header
  drawerSubText: {
    fontSize: scaleFont(14),
    color: '#e0e7ff', // Lighter blue text color
    marginTop: scaleSize(4),
  },
  // Styles for individual touchable items within the Drawer menu
  drawerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: scaleSize(15),
    paddingHorizontal: scaleSize(20),
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9', // Light grey bottom border
  },
  // Styles for the text label of a Drawer menu item
  drawerItemText: {
    fontSize: scaleFont(16),
    color: '#1e3a8a', // Dark blue text color
    marginLeft: scaleSize(20), // Space between icon and text
    fontWeight: '500',
  },
  // Styles for the container used for introduction and warning boxes
  introContainer: {
    backgroundColor: '#ffffff', // White background
    padding: scaleSize(24), // Internal padding
    borderRadius: scaleSize(16), // Rounded corners
    marginHorizontal: scaleSize(15), // Horizontal margin
    marginTop: scaleSize(20),
    shadowColor: '#9ca3af', // Grey shadow color
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.15,
    shadowRadius: scaleSize(10),
    elevation: 5, // Android elevation for shadow
    alignItems: 'center', // Center content horizontally
  },
  // Styles for the disclaimer text on the Warning screen
  warningText: {
    fontSize: scaleFont(15),
    marginBottom: scaleSize(16),
    lineHeight: scaleSize(22), // Space between lines
    textAlign: 'center',
  },
  // Styles for the description text on the Intro screen
  introText: {
    fontSize: scaleFont(16),
    color: '#334155', // Darker grey text
    marginBottom: scaleSize(24),
    lineHeight: scaleSize(24),
    textAlign: 'center',
  },
  // Styles for the main button on Intro and Warning screens
  introButton: {
    width: '100%', // Make the button full width
    marginTop: scaleSize(10),
  },
  // Styles for the app logo image on login/intro/warning screens
  logo: {
    width: scaleSize(120),
    height: scaleSize(120),
    alignSelf: 'center', // Center the logo horizontally
    marginBottom: scaleSize(20),
    marginTop: scaleSize(10),
  },
  // Styles for the app tagline text
  tagline: {
    fontSize: scaleFont(22),
    textAlign: 'center',
    color: '#1e3a8a', // Dark blue text
    marginBottom: scaleSize(25),
    fontWeight: '600',
  },
  // Styles for primary section titles within screens
  sectionTitle: {
    fontSize: scaleFont(24),
    fontWeight: 'bold',
    marginBottom: scaleSize(20),
    color: '#1e3a8a', // Dark blue text
    textAlign: 'center', // Center the title
  },
  // Styles for secondary section titles within screens
  sectionSubtitle: {
    fontSize: scaleFont(20),
    fontWeight: '600',
    marginTop: scaleSize(30), // Space above the subtitle
    marginBottom: scaleSize(15), // Space below the subtitle
    color: '#1e3a8a',
  },
  // Styles for labels above input fields or text blocks
  label: {
    fontSize: scaleFont(16),
    marginBottom: scaleSize(8),
    color: '#374151', // Grey text
    fontWeight: '500',
  },
  // Styles for general text blocks used for displaying information
  textBlock: {
    fontSize: scaleFont(15),
    lineHeight: scaleSize(23),
    marginBottom: scaleSize(12),
    color: '#334155', // Darker grey text
  },
  // Styles for general text input fields
  input: {
    backgroundColor: '#ffffff', // White background
    borderWidth: 1,
    borderColor: '#d1d5db', // Light grey border color
    borderRadius: scaleSize(8),
    paddingHorizontal: scaleSize(14),
    paddingVertical: scaleSize(12),
    marginBottom: scaleSize(16),
    fontSize: scaleFont(16),
    color: '#1f2937', // Dark grey text color
  },
  // Additional styles for multiline text input fields
  multilineInput: {
    minHeight: scaleSize(100), // Minimum height
    textAlignVertical: 'top', // Align text to the top (especially important for Android)
  },
  // Styles for a row container used for buttons or other inline elements
  buttonRow: {
    flexDirection: 'row',
    justifyContent: 'space-between', // Space items evenly
    alignItems: 'center', // Align items vertically
  },
  // Styles for a cancel button typically used in forms
  cancelEditButton: {
    marginTop: scaleSize(10),
    alignSelf: 'center', // Center the button horizontally
    padding: scaleSize(8), // Increase touch area
  },
  // Styles for the text label of a cancel button
  cancelEditText: {
    fontSize: scaleFont(14),
    color: '#6b7280', // Grey text
    textDecorationLine: 'underline', // Underline the text
  },
  // Styles for containers displaying doctor information
  doctorCard: {
    padding: scaleSize(16),
    borderRadius: scaleSize(12),
    marginBottom: scaleSize(12),
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#e5e7eb',
    shadowColor: "#a3a3a3",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.18,
    shadowRadius: 2.22,
    elevation: 3, // Android shadow
  },
  // Styles for the doctor's name text within a DoctorCard
  doctorName: {
    fontWeight: '600',
    fontSize: scaleFont(17),
    marginBottom: scaleSize(6),
    color: '#1e3a8a',
  },
  // Styles for general text within a DoctorCard (address, rating, phone)
  doctorText: {
    fontSize: scaleFont(14),
    marginBottom: scaleSize(4),
    color: '#4b5563', // Grey text
  },
  // Styles for the semi-transparent background view behind the modal
  modalSafeArea: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)', // Semi-transparent black background
    justifyContent: 'flex-end', // Align the modal container to the bottom
  },
  // Styles for the modal container (the sliding panel)
  modalContainer: {
    backgroundColor: '#f8fafc', // Light grey background
    borderTopLeftRadius: scaleSize(20), // Rounded top-left corner
    borderTopRightRadius: scaleSize(20), // Rounded top-right corner
    maxHeight: height * 0.9, // Maximum height of the modal (90% of screen height)
    minHeight: height * 0.5, // Minimum height of the modal (50% of screen height)
    paddingBottom: scaleSize(20), // Padding at the bottom
    overflow: 'hidden', // Clip content that goes outside the rounded corners
    shadowColor: "#000", // Black shadow
    shadowOffset: { width: 0, height: -5 }, // Shadow positioned above the modal
    shadowOpacity: 0.25,
    shadowRadius: 15,
    elevation: 20, // Android elevation for shadow
  },
  // Styles for the header area within the modal
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: scaleSize(12),
    paddingHorizontal: scaleSize(15),
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb', // Light grey bottom border
  },
  // Styles for the close button in the modal header
  modalCloseButton: {
    padding: scaleSize(10), // Increase touch area around the icon
  },
  // Styles for the title text in the modal header
  modalTitle: {
    fontSize: scaleFont(18),
    fontWeight: '600',
    color: '#1e3a8a', // Dark blue text
    textAlign: 'center', // Center the title text
    flex: 1, // Allow title to take available space, pushing buttons to edges
    marginHorizontal: scaleSize(10),
  },
  // Styles for the ScrollView containing the modal content
  modalScrollView: {
    flex: 1, // Allows the content inside the modal to be scrollable
  },
  // Styles for the content area within the modal ScrollView
  modalContent: {
    paddingHorizontal: scaleSize(20), // Horizontal padding
    paddingTop: scaleSize(15), // Padding at the top
    paddingBottom: scaleSize(40), // Padding at the bottom
  },
  // Styles for the label indicating urgency level
  urgencyLabel: {
    fontWeight: '600',
    marginTop: scaleSize(5),
  },
  // Additional styles for high/urgent text, making it red and bold
  emergencyText: {
    color: '#dc2626', // Red color
    fontWeight: 'bold',
  },
  // Styles for the label indicating the health risk assessment section
  healthRiskLabel: {
    color: '#ca8a04', // Orange color
    fontWeight: 'bold',
    fontSize: scaleFont(17),
    marginVertical: scaleSize(15), // Vertical margin
    borderBottomWidth: 1,
    borderBottomColor: '#fde68a', // Light orange bottom border
    paddingBottom: scaleSize(5), // Padding below the text and above the border
  },
  // Styles for cards displaying health risk information
  healthRiskCard: {
    padding: scaleSize(14),
    marginBottom: scaleSize(12),
    borderRadius: scaleSize(8),
    borderLeftWidth: 5, // Thick left border for visual emphasis
    borderLeftColor: '#f59e0b', // Orange border color
    backgroundColor: '#fffbeb', // Light yellow background color
  },
  // Styles for the title text within a health risk card
  healthRiskTitle: {
    color: '#b45309', // Dark orange text color
    fontWeight: 'bold',
    marginBottom: scaleSize(6),
    fontSize: scaleFont(16),
  },
  // Styles for the main text within a health risk card
  healthRiskText: {
    color: '#334155', // Darker grey text color
    fontSize: scaleFont(15),
    lineHeight: scaleSize(22), // Space between lines
  },
  // Styles for the container displaying the message when no doctors are found
  noDoctorsContainer: {
    backgroundColor: '#fffbeb', // Light yellow background
    padding: scaleSize(20),
    borderRadius: scaleSize(12),
    marginBottom: scaleSize(16),
    borderWidth: 1,
    borderColor: '#fde68a', // Light orange border
    alignItems: 'center', // Center content horizontally
  },
  // Styles for the header area in the History screen
  historyHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between', // Space items horizontally
    alignItems: 'center', // Align items vertically
    marginBottom: scaleSize(15),
    paddingHorizontal: scaleSize(5), // Small horizontal padding
  },
  // Styles for individual items in the history list (symptom analysis or lab report)
  historyItem: {
    flexDirection: 'row',
    justifyContent: 'space-between', // Space items horizontally
    alignItems: 'center', // Align items vertically
    padding: scaleSize(15), // Internal padding
    borderRadius: scaleSize(12), // Rounded corners
    marginBottom: scaleSize(12), // Space below each item
    backgroundColor: '#ffffff', // White background
    borderWidth: 1,
    borderColor: '#e5e7eb', // Light grey border
    shadowColor: "#a3a3a3",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.18,
    shadowRadius: 2.00,
    elevation: 2, // Android elevation for shadow
  },
  // Styles for the content area within a history item (text)
  historyContent: {
    flex: 1, // Take available space
    marginRight: scaleSize(10), // Space between text and delete button/chevron
  },
  // Styles for the timestamp text in a history item
  historyTime: {
    fontSize: scaleFont(12),
    color: '#6b7280', // Grey text color
    marginBottom: scaleSize(5),
  },
  // Styles for the query/report text in a history item
  historyQuery: {
    fontSize: scaleFont(15),
    fontWeight: '500',
    color: '#1f2937', // Dark grey text color
    marginBottom: scaleSize(4),
  },
  // Styles for the summary text in a history item
  historySummary: {
    fontSize: scaleFont(14),
    color: '#4b5563', // Grey text color
    lineHeight: scaleSize(20),
  },
  // Styles for the delete button within a history item
  deleteItemButton: {
    padding: scaleSize(8), // Increase touch area
    marginLeft: scaleSize(10), // Space between content and button
    justifyContent: 'center',
    alignItems: 'center',
  },
  // Styles for the clear history trash button
  trashButton: {
    padding: scaleSize(8), // Increase touch area
  },
  // Styles for messages displayed when lists or sections are empty
  emptyMessage: {
    fontSize: scaleFont(15),
    color: '#6b7280', // Grey text color
    textAlign: 'center',
    marginTop: scaleSize(20),
  },
  // Styles for the container wrapping empty messages and icons
  emptyView: {
    flex: 1, // Allows it to take up space if needed
    justifyContent: 'center',
    alignItems: 'center',
    padding: scaleSize(20),
    marginTop: scaleSize(50), // Space above the empty state view
  },
  // Utility style to center text horizontally
  centerText: { textAlign: 'center' },
  // Utility style for slightly faded text color
  subtleText: { color: '#475569' },
  // Styles for individual medication items in the Medication Reminders screen
  medicationItem: {
    padding: scaleSize(15),
    borderRadius: scaleSize(12),
    marginBottom: scaleSize(12),
    borderWidth: 1,
    borderColor: '#e5e7eb',
    shadowColor: "#a3a3a3",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.18,
    shadowRadius: 2.00,
    elevation: 2,
  },
  // Styles for the header area of a medication item (name and icons)
  medHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  // Styles for the medication name text
  medicationText: {
    fontSize: scaleFont(17),
    fontWeight: '600',
    color: '#1e3a8a',
    flex: 1, // Allow text to take space
    marginRight: scaleSize(10), // Space between text and icons
  },
  // Styles for the details section of a medication item (when expanded)
  medDetails: {
    marginTop: scaleSize(15),
    paddingTop: scaleSize(15),
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
  },
  // Styles for explanatory text in medication details
  detailText: {
    fontSize: scaleFont(14),
    color: '#4b5563',
    lineHeight: scaleSize(20),
    marginBottom: scaleSize(15),
  },
  // Styles for the container displaying a reminder
  reminderContainer: {
    marginTop: scaleSize(10),
    padding: scaleSize(14),
    backgroundColor: '#dbeafe', // Light blue background
    borderRadius: scaleSize(8),
    borderWidth: 1,
    borderColor: '#bfdbfe', // Lighter blue border
  },
  // Styles for the reminder time text
  reminderText: {
    fontSize: scaleFont(14),
    color: '#1e3a8a',
    marginBottom: scaleSize(12),
  },
  // Styles for the row of buttons within the reminder view
  reminderButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: scaleSize(5),
  },
  // Styles for the form used to set or edit reminders
  reminderForm: {
    marginTop: scaleSize(10),
  },
  // Styles for the "Edit" button within reminders
  editButton: {
    flex: 0.48, // Take approximately half the width
    marginRight: scaleSize(8),
    paddingVertical: scaleSize(10),
  },
  // Styles for the "Delete" button within reminders
  deleteButton: {
    flex: 0.48, // Take approximately half the width
    paddingVertical: scaleSize(10),
  },
  // Styles for the header area in the Health Tips screen
  tipsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: scaleSize(15),
    paddingHorizontal: scaleSize(5),
  },
  // Styles for the toggle button (All Tips / Favorites)
  toggleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: scaleSize(8),
    paddingHorizontal: scaleSize(12),
    borderRadius: scaleSize(20), // Pill shape
    borderWidth: 1,
    borderColor: '#0052cc',
    backgroundColor: '#ffffff',
  },
  // Styles for the active state of the toggle button
  toggleButtonActive: {
    backgroundColor: '#0052cc',
    borderColor: '#0052cc',
  },
  // Styles for the text within the toggle button
  toggleButtonText: {
    marginLeft: scaleSize(6),
    fontSize: scaleFont(14),
    color: '#0052cc',
    fontWeight: '500',
  },
  // Styles for the text within the active toggle button
  toggleButtonTextActive: {
    color: '#ffffff',
  },
  // Styles for individual health tip items
  tipItem: {
    padding: scaleSize(15),
    borderRadius: scaleSize(12),
    marginBottom: scaleSize(12),
    borderWidth: 1,
    borderColor: '#e5e7eb',
    shadowColor: "#a3a3a3",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.18,
    shadowRadius: 2.00,
    elevation: 2,
  },
  // Styles for the header area of a tip item
  tipHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: scaleSize(8),
  },
  // Styles for the title text of a health tip
  tipTitle: {
    fontSize: scaleFont(16),
    fontWeight: '600',
    color: '#1e3a8a',
    flex: 1, // Allow text to take space
    marginRight: scaleSize(10),
  },
  // Styles for the container of icons (favorite + chevron) in a tip item
  tipIcons: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  // Styles for the favorite star icon button
  favoriteButton: {
    padding: scaleSize(5), // Increase touch area
  },
  // Styles for the summary text of a health tip
  tipSummary: {
    fontSize: scaleFont(14),
    color: '#4b5563',
    lineHeight: scaleSize(20),
  },
  // Styles for the details section of a health tip (when expanded)
  tipDetails: {
    marginTop: scaleSize(10),
    paddingTop: scaleSize(10),
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
  },
  // Styles for the full content text of a health tip
  tipContent: {
    fontSize: scaleFont(14),
    color: '#334155',
    lineHeight: scaleSize(22),
  },
  // Styles for the container of the Add Appointment form
  datePickerContainer: {
    backgroundColor: '#ffffff',
    padding: scaleSize(20),
    borderRadius: scaleSize(12),
    marginBottom: scaleSize(20),
    borderWidth: 1,
    borderColor: '#e5e7eb',
    shadowColor: "#a3a3a3",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.18,
    shadowRadius: 2.00,
    elevation: 2,
  },
  // Styles for the row of buttons within the Add Appointment form
  datePickerButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: scaleSize(10),
  },
  // Styles for the FlatList container in the Appointments screen
  appointmentList: {
    flex: 1,
  },
  // Styles for individual appointment items in the list
  appointmentItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: scaleSize(15),
    borderRadius: scaleSize(12),
    marginBottom: scaleSize(12),
    backgroundColor: '#f1f5f9', // Light grey background
    borderWidth: 1,
    borderColor: '#e5e7eb',
    shadowColor: "#a3a3a3",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.18,
    shadowRadius: 2.00,
    elevation: 2,
  },
  // Styles for the details section within an appointment item (title and date)
  appointmentDetails: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  // Styles for the appointment title text
  appointmentTitle: {
    fontSize: scaleFont(16),
    fontWeight: '600',
    color: '#1e3a8a',
    marginBottom: scaleSize(4),
  },
  // Styles for the appointment date/time text
  appointmentDate: {
    fontSize: scaleFont(14),
    color: '#4b5563',
  },
  // Styles for the cancel button within an appointment item
  cancelButton: {
    padding: scaleSize(8),
    marginLeft: scaleSize(10),
  },
  // Styles for the form container in the Symptom Progress screen
  symptomInputForm: {
    backgroundColor: '#ffffff',
    padding: scaleSize(20),
    borderRadius: scaleSize(12),
    marginBottom: scaleSize(20),
    borderWidth: 1,
    borderColor: '#e5e7eb',
    shadowColor: "#a3a3a3",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.18,
    shadowRadius: 2.00,
    elevation: 2,
  },
  // Styles for the group of status radio buttons
  radioGroup: {
    marginBottom: scaleSize(20),
  },
  // Styles for individual status radio button options
  radioOption: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: scaleSize(10),
    paddingHorizontal: scaleSize(15),
    borderRadius: scaleSize(8),
    marginBottom: scaleSize(8),
    backgroundColor: '#f1f5f9',
  },
  // Styles for the label text of a status radio button option
  radioLabel: {
    marginLeft: scaleSize(10),
    fontSize: scaleFont(15),
    color: '#1f2937',
  },
  // Styles for the wrapper around GradientButton
  gradientButton: {
    borderRadius: scaleSize(10),
    overflow: 'hidden', // Ensures gradient stays within bounds
    marginVertical: scaleSize(5), // Vertical margin above/below button
  },
  // Styles for the disabled state of GradientButton
  disabledButton: {
    opacity: 0.6, // Reduce opacity
  },
  // Styles for the LinearGradient element inside the button
  gradient: {
    paddingVertical: scaleSize(14), // Vertical padding inside the gradient
    paddingHorizontal: scaleSize(20), // Horizontal padding inside the gradient
    alignItems: 'center', // Center text horizontally
  },
  // Styles for the text inside the GradientButton
  buttonText: {
    color: '#ffffff', // White text
    fontSize: scaleFont(16),
    fontWeight: '600',
  },
  // Styles for the preview image of a lab report
  labImagePreview: {
    width: scaleSize(200),
    height: scaleSize(200),
    borderRadius: scaleSize(10),
    marginTop: scaleSize(10),
  },
  // Styles for the custom top bar displayed on each main screen
  topBar: {
     flexDirection: 'row',
     justifyContent: 'space-between', // Space items horizontally
     alignItems: 'center', // Align items vertically
     paddingHorizontal: scaleSize(15), // Horizontal padding
     paddingVertical: scaleSize(10), // Vertical padding
     backgroundColor: '#ffffff', // White background
     borderBottomWidth: 1,
     borderBottomColor: '#e5e7eb', // Light grey bottom border
  },
  // Styles for the menu button (drawer icon) in the top bar
  menuButton: {
     padding: scaleSize(5), // Increase touch area around the icon
  },
  // Styles for the screen title text in the top bar
  headerTitle: {
     fontSize: scaleFont(18),
     fontWeight: 'bold',
     color: '#1e3a8a', // Dark blue text
  },
   // Placeholder View to help center the title when a button is only on one side
  menuButtonPlaceholder: {
     width: scaleFont(28) + scaleSize(10), // Match the approximate width of the menu button + its padding
  }
});


// Export the main App component as the default export
export default App;
