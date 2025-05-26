// --- START OF FILE ProfileScreen.js ---

// ProfileScreen.js
// ----- START OF COMPLETE ProfileScreen.js FILE (with debugging logs) -----

import React, { useState, useEffect, useCallback } from 'react';
import {
    View, Text, TextInput, StyleSheet, TouchableOpacity, ScrollView, Switch, Alert,
    KeyboardAvoidingView, Platform, FlatList, Dimensions, PixelRatio
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Picker } from '@react-native-picker/picker';
import DateTimePicker from '@react-native-community/datetimepicker';
import GradientButton from './GradientButton.js'; // Import the separate GradientButton component

// --- Scaling Utilities ---
const { width } = Dimensions.get('window');
const scaleFont = (size) => PixelRatio.roundToNearestPixel(size * (width / 375));
const scaleSize = (size) => Math.min(size * (width / 375), size * 1.2);

// --- Main Profile Screen Component ---
// Added navigation prop here
const ProfileScreen = ({ profile, setProfile, navigation }) => {
    const [localProfile, setLocalProfile] = useState(profile || {});
    const [isEditing, setIsEditing] = useState(false);

    // State for list item inputs
    const [newCondition, setNewCondition] = useState('');
    const [newAllergy, setNewAllergy] = useState('');
    const [newMedication, setNewMedication] = useState('');
    const [newMedicalHistory, setNewMedicalHistory] = useState('');
    const [newFamilyHistory, setNewFamilyHistory] = useState('');

    // State for Date Picker
    const [showDatePicker, setShowDatePicker] = useState(false);
    // Initialize dateOfBirth state correctly from localProfile (which is derived from profile prop)
    const [dateOfBirth, setDateOfBirth] = useState(
        (profile?.dob && !isNaN(new Date(profile.dob).getTime())) ? new Date(profile.dob) : new Date() // Ensure date is valid
    );

    // Effect to update local state when profile prop changes (e.g., after saving)
    // or when cancelling edit mode
    useEffect(() => {
        console.log('[ProfileScreen] profile prop changed or isEditing changed:', profile); // Debug log
        if (!isEditing) {
            const currentProfile = profile || {};
            console.log('[ProfileScreen] Resetting local state to profile prop:', currentProfile); // Debug log
            setLocalProfile(currentProfile);
            // Ensure dateOfBirth state also resets/updates based on profile prop
            const profileDob = (currentProfile?.dob && !isNaN(new Date(currentProfile.dob).getTime())) ? new Date(currentProfile.dob) : new Date();
            console.log('[ProfileScreen] Setting dateOfBirth state to:', profileDob); // Debug log
            setDateOfBirth(profileDob);
        } else {
            console.log('[ProfileScreen] In editing mode, skipping reset from prop.'); // Debug log
        }
    }, [profile, isEditing]); // Rerun when profile prop or isEditing changes


    // --- Handlers for nested objects ---
    const handleLifestyleChange = useCallback((key, value) => {
        setLocalProfile(prev => ({ ...prev, lifestyle: { ...(prev.lifestyle || {}), [key]: value } }));
    }, []);
    const handleBiometricsChange = useCallback((key, value) => {
        setLocalProfile(prev => ({ ...prev, biometrics: { ...(prev.biometrics || {}), [key]: value } }));
    }, []);
    const handleEmergencyContactChange = useCallback((key, value) => {
        setLocalProfile(prev => ({ ...prev, emergencyContact: { ...(prev.emergencyContact || {}), [key]: value } }));
    }, []);


    // --- Handlers for list items ---
    const addItemToList = useCallback((listKey, newItem, setNewItemState) => {
        const trimmedItem = newItem.trim();
        if (!trimmedItem) return;
         // Prevent duplicates
        setLocalProfile(prev => {
             const currentList = prev[listKey] || [];
             if (currentList.includes(trimmedItem)) {
                  Alert.alert("Duplicate Entry", `${trimmedItem} is already in the list.`);
                  return prev;
             }
             return { ...prev, [listKey]: [...currentList, trimmedItem] };
        });
        setNewItemState(''); // Clear the specific input field
    }, []);

    const removeItemFromList = useCallback((listKey, indexToRemove) => {
         Alert.alert( "Remove Item", "Are you sure you want to remove this item?", [ { text: "Cancel", style: "cancel" }, { text: "Remove", style: "destructive", onPress: () => {
            setLocalProfile(prev => ({ ...prev, [listKey]: (prev[listKey] || []).filter((_, index) => index !== indexToRemove) }));
         } } ] );
    }, []);

    // --- Date Picker Handler (Corrected) ---
    const onDateChange = (event, selectedDate) => {
         console.log('[ProfileScreen] onDateChange event:', event, 'selectedDate:', selectedDate); // Debug log
        const currentDate = selectedDate || dateOfBirth; // Use selected or fallback to current

        if (Platform.OS === 'android') { // On Android, picker closes automatically
             setShowDatePicker(false);
             if (event.type === 'set' && selectedDate) { // Check event type for confirmation on Android
                  setDateOfBirth(currentDate); // Update local state for the picker
                  const year = currentDate.getFullYear();
                  const month = (currentDate.getMonth() + 1).toString().padStart(2, '0');
                  const day = currentDate.getDate().toString().padStart(2, '0');
                  const formattedDate = `${year}-${month}-${day}`; // Format consistently YYYY-MM-DD
                  console.log('[ProfileScreen] Setting DOB in localProfile (Android):', formattedDate); // Add log to check
                  setLocalProfile(prev => ({ ...prev, dob: formattedDate })); // Update the profile draft
             }
        } else { // On iOS, picker is inline or modal, doesn't close automatically unless display='compact'
             setDateOfBirth(currentDate); // Update local state for the picker preview
             const year = currentDate.getFullYear();
             const month = (currentDate.getMonth() + 1).toString().padStart(2, '0');
             const day = currentDate.getDate().toString().padStart(2, '0');
             const formattedDate = `${year}-${month}-${day}`; // Format consistently YYYY-MM-DD
             console.log('[ProfileScreen] Updating DOB in localProfile (iOS):', formattedDate); // Add log to check
             setLocalProfile(prev => ({ ...prev, dob: formattedDate })); // Update the profile draft immediately
             // You might want a "Done" button to hide the picker on iOS if display is not 'compact'
        }
    };

    // --- Save Handler (WITH DEBUG LOGS) ---
    const handleSaveChanges = () => {
        console.log('[ProfileScreen] handleSaveChanges called'); // Log start

        // --- Input Validation ---
        if (!localProfile.name?.trim()) {
            Alert.alert('Error', 'Please enter your name.');
            console.log('[ProfileScreen] Validation failed: Name missing');
            return;
        }
         // Validate Age if provided
        if (localProfile.age) {
             const parsedAge = parseInt(localProfile.age, 10);
             if (isNaN(parsedAge) || parsedAge < 0 || parsedAge > 120) { // Basic age range check
                  Alert.alert('Error', 'Please enter a valid age (0-120).');
                  console.log('[ProfileScreen] Validation failed: Invalid age');
                  return;
             }
        }

        // Validate DOB format if provided (assuming YYYY-MM-DD string)
        if (localProfile.dob) {
             if (isNaN(new Date(localProfile.dob).getTime())) {
                  Alert.alert('Error', 'Please select a valid Date of Birth.');
                   console.log('[ProfileScreen] Validation failed: Invalid DOB format');
                  return;
             }
        }


        console.log("[ProfileScreen] Validation passed. Saving profile data:", localProfile);

        // --- Call the update function passed from App.js ---
        // This triggers handleSetProfile in App.js which attempts the Supabase save
        try {
             // Pass the local state (which is the updated draft) up to the parent
             setProfile(localProfile);
             console.log("[ProfileScreen] setProfile function called successfully.");
        } catch (error) {
             console.error("[ProfileScreen] Error calling setProfile:", error);
             Alert.alert('Error', 'Failed to initiate profile update.');
             return; // Don't proceed if the state update fails
        }

        // Give immediate feedback and transition UI
        Alert.alert('Profile Updated', 'Your profile changes have been saved.');
        setIsEditing(false); // Exit editing mode

        // --- Navigation Logic ---
        console.log("[ProfileScreen] Attempting navigation...");
        if (navigation) { // Check if navigation prop exists
            console.log("[ProfileScreen] Navigation prop exists. Can go back?", navigation.canGoBack());
             // Navigate back to the previous screen (likely the Drawer screen)
            if (navigation.canGoBack()) {
                 console.log("[ProfileScreen] Calling navigation.goBack()");
                 navigation.goBack();
            } else {
                 // Fallback: Navigate explicitly to your main tabs screen
                 console.log("[ProfileScreen] Cannot go back, calling navigation.navigate('HomeTabs')");
                 navigation.navigate('HomeTabs'); // Ensure 'HomeTabs' is the correct name of your Drawer screen containing the tabs
            }
        } else {
            console.warn("[ProfileScreen] Navigation prop not available!");
            // Alert.alert("Navigation Error", "Could not navigate back automatically."); // Inform user - maybe too much?
        }
    };

    // --- Cancel Edit Handler ---
    const handleCancelEdit = () => {
         Alert.alert( "Discard Changes", "Discard changes and return to profile?", [ { text: "Cancel", style: "cancel" }, { text: "Discard", style: "destructive", onPress: () => {
             console.log('[ProfileScreen] handleCancelEdit called. Resetting local state.'); // Debug log
             const currentProfile = profile || {}; // Get the latest profile from props
             setLocalProfile(currentProfile); // Reset local state to original profile
             const profileDob = (currentProfile?.dob && !isNaN(new Date(currentProfile.dob).getTime())) ? new Date(currentProfile.dob) : new Date();
             setDateOfBirth(profileDob); // Reset date picker state
             setIsEditing(false); // Exit editing mode
             // Clear temporary input states
             setNewCondition(''); setNewAllergy(''); setNewMedication('');
             setNewMedicalHistory(''); setNewFamilyHistory('');
         } } ] );
    };

    // --- Render List Item Function ---
    const renderEditableListItem = ({ item, index, listKey, removeItemHandler }) => (
        <View style={profileStyles.listItemContainer}>
            <Text style={profileStyles.listItemText}>• {item}</Text>
            {isEditing && (
                <TouchableOpacity onPress={() => removeItemHandler(listKey, index)} style={profileStyles.removeButton}>
                    <Ionicons name="trash-outline" size={scaleFont(18)} color="#dc2626" />
                </TouchableOpacity>
            )}
        </View>
    );

    // --- Render Input for Adding List Item ---
    const renderListInput = (listKey, value, setValue, addItemHandler, placeholder) => (
        <View style={profileStyles.listInputContainer}>
            <TextInput
                style={profileStyles.listInput} placeholder={placeholder} placeholderTextColor="#9ca3af"
                value={value} onChangeText={setValue}
                onSubmitEditing={() => { if (value.trim()) addItemHandler(listKey, value, setValue); }} // Only add on submit if not empty
                returnKeyType="done" blurOnSubmit={false} // Keep keyboard open for adding more
            />
            <TouchableOpacity onPress={() => addItemHandler(listKey, value, setValue)} style={profileStyles.addButton} disabled={!value.trim()}>
                <Ionicons name="add-circle" size={scaleFont(26)} color={value.trim() ? "#16a34a" : "#9ca3af"} />
            </TouchableOpacity>
        </View>
    );

    // --- ProfileScreen Render ---
    return (
        <SafeAreaView style={profileStyles.container} edges={['bottom', 'left', 'right']}>
            {/* Use KeyboardAvoidingView for better input handling */}
            <KeyboardAvoidingView
                 behavior={Platform.OS === "ios" ? "padding" : undefined} // 'height' might also work, 'padding' is common
                 style={{ flex: 1 }}
                 keyboardVerticalOffset={Platform.OS === "ios" ? scaleSize(64) : 0} // Adjust offset if header height changes
            >
                <ScrollView
                    contentContainerStyle={profileStyles.scrollContainer}
                    keyboardShouldPersistTaps="handled" // Allows taps on buttons while keyboard is up
                >
                    {/* Header */}
                    <View style={profileStyles.header}>
                        <Text style={profileStyles.title}>My Profile</Text>
                        <TouchableOpacity onPress={isEditing ? handleCancelEdit : () => setIsEditing(true)}>
                            <Text style={profileStyles.editButtonText}>{isEditing ? 'Cancel' : 'Edit'}</Text>
                        </TouchableOpacity>
                    </View>

                    {/* Basic Information Card */}
                    <View style={profileStyles.card}>
                        <Text style={profileStyles.cardTitle}>Basic Information</Text>
                        <ProfileField label="Name" value={localProfile.name} onChange={(val) => setLocalProfile(p => ({...p, name: val}))} isEditing={isEditing} />
                        <ProfileField label="Age" value={localProfile.age?.toString()} onChange={(val) => setLocalProfile(p => ({...p, age: val}))} isEditing={isEditing} keyboardType="numeric" />

                        {/* Date of Birth Field */}
                        <View style={profileStyles.fieldContainer}>
                            <Text style={profileStyles.fieldLabel}>Date of Birth:</Text>
                            {isEditing ? (
                                <>
                                    {/* Make the whole area touchable */}
                                    <TouchableOpacity onPress={() => setShowDatePicker(true)} style={profileStyles.dateDisplay}>
                                       <Text style={profileStyles.fieldValueText}>
                                           {(dateOfBirth && !isNaN(dateOfBirth.getTime())) ? dateOfBirth.toLocaleDateString() : 'Select Date'}
                                       </Text>
                                       <Ionicons name="calendar-outline" size={scaleFont(20)} color="#0052cc" />
                                    </TouchableOpacity>
                                    {/* The DateTimePicker component - visibility controlled by showDatePicker */}
                                    {/* On Android, picker is a dialog; on iOS it can be inline or modal. display='spinner' is common for date */}
                                    {(showDatePicker || Platform.OS === 'ios') && ( // Show always on iOS (if using default display), only when toggled on Android
                                         <DateTimePicker
                                            testID="dateTimePicker"
                                            value={dateOfBirth || new Date()} // Use state variable, default to now if state is null/invalid
                                            mode="date"
                                            display={Platform.OS === 'ios' ? 'spinner' : 'default'} // 'spinner' on iOS, default on Android
                                            onChange={onDateChange} // Use the corrected handler
                                            maximumDate={new Date()} // Prevent selecting future dates
                                            // On iOS, if not using 'compact', picker stays open. You might need a "Done" button.
                                            // Our current onDateChange updates localProfile.dob immediately on iOS spinner.
                                        />
                                    )}
                                </>
                            ) : (
                                <Text style={profileStyles.fieldValueText}>
                                    {(profile?.dob && !isNaN(new Date(profile.dob).getTime())) ? new Date(profile.dob).toLocaleDateString() : 'Not Set'}
                                </Text>
                            )}
                        </View>

                        <ProfilePickerField label="Gender" selectedValue={localProfile.gender} onValueChange={(val) => setLocalProfile(p => ({...p, gender: val}))}
                            items={[ { label: 'Select...', value: '' }, { label: 'Female', value: 'female' }, { label: 'Male', value: 'male' }, { label: 'Non-binary', value: 'non-binary' }, { label: 'Other', value: 'other' }, { label: 'Prefer not to say', value: 'prefer_not_say' } ]} isEditing={isEditing} />
                        <ProfileField label="State/Region" value={localProfile.state} onChange={(val) => setLocalProfile(p => ({...p, state: val}))} isEditing={isEditing} />
                        <ProfileField label="Blood Type" value={localProfile.bloodType} onChange={(val) => setLocalProfile(p => ({...p, bloodType: val}))} isEditing={isEditing} placeholder="e.g., O+, AB-" />
                    </View>

                     {/* Biometrics Card */}
                    <View style={profileStyles.card}>
                        <Text style={profileStyles.cardTitle}>Biometrics</Text>
                        <ProfileField label="Height (cm/inches)" value={localProfile.biometrics?.height} onChange={(val) => handleBiometricsChange('height', val)} isEditing={isEditing} placeholder={`e.g., 175 cm or 5' 9"`} />
                        <ProfileField label="Weight (kg/lbs)" value={localProfile.biometrics?.weight} onChange={(val) => handleBiometricsChange('weight', val)} isEditing={isEditing} placeholder={`e.g., 70 kg or 154 lbs`} keyboardType="numeric"/>
                    </View>

                    {/* Lifestyle Card */}
                    <View style={profileStyles.card}>
                        <Text style={profileStyles.cardTitle}>Lifestyle</Text>
                        <ProfileSwitchField label="Smoker" value={localProfile.lifestyle?.smoker} onValueChange={(val) => handleLifestyleChange('smoker', val)} isEditing={isEditing} />
                        <ProfilePickerField label="Alcohol Consumption" selectedValue={localProfile.lifestyle?.alcohol} onValueChange={(val) => handleLifestyleChange('alcohol', val)}
                            items={[ { label: 'Select...', value: '' }, { label: 'None', value: 'none' }, { label: 'Occasionally', value: 'occasionally' }, { label: 'Moderately', value: 'moderately' }, { label: 'Frequently', value: 'frequently' } ]} isEditing={isEditing} />
                        <ProfilePickerField label="Exercise Frequency" selectedValue={localProfile.lifestyle?.exercise} onValueChange={(val) => handleLifestyleChange('exercise', val)}
                            items={[ { label: 'Select...', value: '' }, { label: 'Sedentary', value: 'sedentary' }, { label: 'Light (1-3 days/wk)', value: 'light' }, { label: 'Moderate (3-5 days/wk)', value: 'moderate' }, { label: 'Active (6-7 days/wk)', value: 'active' }, { label: 'Very Active (Daily+)', value: 'very_active' } ]} isEditing={isEditing} />
                        <ProfileField label="Dietary Notes" value={localProfile.lifestyle?.dietaryNotes} onChange={(val) => handleLifestyleChange('dietaryNotes', val)} isEditing={isEditing} multiline placeholder="e.g., Vegetarian, low-carb, allergies..." />
                    </View>

                    {/* Medical Information Card */}
                    <View style={profileStyles.card}>
                        <Text style={profileStyles.cardTitle}>Medical Information</Text>
                        {/* Conditions List */}
                        <Text style={profileStyles.listLabel}>Existing Conditions:</Text>
                        <FlatList data={localProfile.conditions || []} renderItem={({ item, index }) => renderEditableListItem({ item, index, listKey: 'conditions', removeItemHandler: removeItemFromList })} keyExtractor={(item, index) => `condition-${index}-${item}`} ListEmptyComponent={!isEditing && <Text style={profileStyles.emptyField}>No conditions listed.</Text>} />
                        {isEditing && renderListInput('conditions', newCondition, setNewCondition, addItemToList, 'Add condition...')}
                        {/* Allergies List */}
                        <Text style={profileStyles.listLabel}>Allergies:</Text>
                        <FlatList data={localProfile.allergies || []} renderItem={({ item, index }) => renderEditableListItem({ item, index, listKey: 'allergies', removeItemHandler: removeItemFromList })} keyExtractor={(item, index) => `allergy-${index}-${item}`} ListEmptyComponent={!isEditing && <Text style={profileStyles.emptyField}>No allergies listed.</Text>} />
                        {isEditing && renderListInput('allergies', newAllergy, setNewAllergy, addItemToList, 'Add allergy...')}
                        {/* Medications List */}
                        <Text style={profileStyles.listLabel}>Current Medications:</Text>
                        <FlatList data={localProfile.medications || []} renderItem={({ item, index }) => renderEditableListItem({ item, index, listKey: 'medications', removeItemHandler: removeItemFromList })} keyExtractor={(item, index) => `medication-${index}-${item}`} ListEmptyComponent={!isEditing && <Text style={profileStyles.emptyField}>No medications listed.</Text>} />
                        {isEditing && renderListInput('medications', newMedication, setNewMedication, addItemToList, 'Add medication & dose...')}
                        {/* Medical History List */}
                        <Text style={profileStyles.listLabel}>Past Medical History:</Text>
                        <FlatList data={localProfile.medicalHistory || []} renderItem={({ item, index }) => renderEditableListItem({ item, index, listKey: 'medicalHistory', removeItemHandler: removeItemFromList })} keyExtractor={(item, index) => `medhistory-${index}-${item}`} ListEmptyComponent={!isEditing && <Text style={profileStyles.emptyField}>No past history listed.</Text>} />
                        {isEditing && renderListInput('medicalHistory', newMedicalHistory, setNewMedicalHistory, addItemToList, 'Add past condition/surgery...')}
                        {/* Family History List */}
                        <Text style={profileStyles.listLabel}>Family Medical History:</Text>
                        <FlatList data={localProfile.familyHistory || []} renderItem={({ item, index }) => renderEditableListItem({ item, index, listKey: 'familyHistory', removeItemHandler: removeItemFromList })} keyExtractor={(item, index) => `familyhist-${index}-${item}`} ListEmptyComponent={!isEditing && <Text style={profileStyles.emptyField}>No family history listed.</Text>} />
                        {isEditing && renderListInput('familyHistory', newFamilyHistory, setNewFamilyHistory, addItemToList, 'Add family condition...')}
                        {/* Vaccination Notes */}
                        <ProfileField label="Vaccination Notes" value={localProfile.vaccinationHistory} onChange={(val) => setLocalProfile(p => ({...p, vaccinationHistory: val}))} isEditing={isEditing} multiline placeholder="e.g., Up to date, Flu shot 2023" />
                    </View>

                     {/* Emergency Contact Card */}
                    <View style={profileStyles.card}>
                        <Text style={profileStyles.cardTitle}>Emergency Contact</Text>
                        <ProfileField label="Contact Name" value={localProfile.emergencyContact?.name} onChange={(val) => handleEmergencyContactChange('name', val)} isEditing={isEditing}/>
                        <ProfileField label="Relationship" value={localProfile.emergencyContact?.relationship} onChange={(val) => handleEmergencyContactChange('relationship', val)} isEditing={isEditing}/>
                        <ProfileField label="Phone Number" value={localProfile.emergencyContact?.phone} onChange={(val) => handleEmergencyContactChange('phone', val)} isEditing={isEditing} keyboardType="phone-pad"/>
                    </View>

                    {/* Save Button - Make sure GradientButton is imported */}
                    {isEditing && <GradientButton title="Save Changes" onPress={handleSaveChanges} style={profileStyles.saveButtonContainer} />}

                </ScrollView>
            </KeyboardAvoidingView>
        </SafeAreaView>
    );
};

// --- Helper Components for Profile Fields ---
// These were included in your original App.js structure,
// but are logically part of ProfileScreen. They are defined here
// to make ProfileScreen.js a self-contained unit.

const ProfileField = ({ label, value, onChange, isEditing, keyboardType = 'default', placeholder = '', multiline = false }) => (
    <View style={profileStyles.fieldContainer}>
        <Text style={profileStyles.fieldLabel}>{label}:</Text>
        {isEditing ? (
            <TextInput
                style={[profileStyles.input, multiline && profileStyles.multilineInput]}
                value={value || ''}
                onChangeText={onChange}
                placeholder={placeholder || `Enter ${label.toLowerCase()}`}
                placeholderTextColor="#9ca3af"
                keyboardType={keyboardType}
                multiline={multiline}
                textAlignVertical={multiline ? 'top' : 'center'}
            />
        ) : (
            <Text style={profileStyles.fieldValueText}>
                {(value !== null && value !== undefined && value !== '') ? value : 'Not Set'}
            </Text>
        )}
    </View>
);

const ProfileSwitchField = ({ label, value, onValueChange, isEditing }) => (
    <View style={profileStyles.switchContainer}>
        <Text style={profileStyles.switchLabel}>{label}</Text>
        <Switch
            value={value || false}
            onValueChange={onValueChange}
            disabled={!isEditing}
            trackColor={{ false: "#d1d5db", true: "#86efac" }} // Example colors
            thumbColor={value ? "#16a34a" : "#f4f3f4"}
            ios_backgroundColor="#d1d5db"
        />
    </View>
);

const ProfilePickerField = ({ label, selectedValue, onValueChange, items, isEditing }) => (
    <View style={profileStyles.fieldContainer}>
        <Text style={profileStyles.fieldLabel}>{label}:</Text>
        {isEditing ? (
            <View style={profileStyles.pickerWrapper}>
                <Picker
                    selectedValue={selectedValue || ''}
                    onValueChange={(itemValue) => itemValue !== '' ? onValueChange(itemValue) : null} // Prevent selecting the placeholder
                    style={profileStyles.picker}
                    enabled={isEditing}
                    dropdownIconColor="#0052cc"
                    mode="dropdown" // Or "dialog" on Android
                >
                    {items.map(item => (
                        <Picker.Item key={item.value} label={item.label} value={item.value} style={profileStyles.pickerItem}/>
                    ))}
                </Picker>
            </View>
        ) : (
            <Text style={profileStyles.fieldValueText}>
                 {items.find(item => item.value === selectedValue)?.label || 'Not Set'}
            </Text>
        )}
    </View>
);


// --- Local Styles for ProfileScreen ---
// These styles were included in your original App.js structure.
// Defining them here makes ProfileScreen.js self-contained.
const profileStyles = StyleSheet.create({
    container: { flex: 1, backgroundColor: '#f8fafc' }, // Match main app background
    scrollContainer: { paddingHorizontal: scaleSize(15), paddingBottom: scaleSize(40) },
    header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: scaleSize(10), paddingBottom: scaleSize(15) },
    title: { fontSize: scaleFont(26), fontWeight: 'bold', color: '#1e3a8a' },
    editButtonText: { fontSize: scaleFont(16), color: '#0052cc', fontWeight: '600', padding: scaleSize(5) },
    card: { backgroundColor: '#ffffff', borderRadius: scaleSize(12), padding: scaleSize(18), marginBottom: scaleSize(18), shadowColor: "#9ca3af", shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: scaleSize(4), elevation: 3, borderWidth: 1, borderColor: '#e5e7eb' },
    cardTitle: { fontSize: scaleFont(18), fontWeight: '600', color: '#1e3a8a', marginBottom: scaleSize(15), borderBottomWidth: 1, borderBottomColor: '#e5e7eb', paddingBottom: scaleSize(8) },
    fieldContainer: { marginBottom: scaleSize(16) },
    fieldLabel: { fontSize: scaleFont(14), color: '#374151', fontWeight: '500', marginBottom: scaleSize(6) },
    listLabel: { fontSize: scaleFont(16), color: '#1e3a8a', fontWeight: '600', marginTop: scaleSize(10), marginBottom: scaleSize(8) },
    fieldValueText: { fontSize: scaleFont(16), color: '#1f2937', paddingVertical: Platform.OS === 'ios' ? scaleSize(4) : scaleSize(8), minHeight: scaleSize(30) }, // Ensure minimum height for display text
    input: { backgroundColor: '#f8fafc', borderWidth: 1, borderColor: '#d1d5db', borderRadius: scaleSize(8), paddingHorizontal: scaleSize(12), paddingVertical: Platform.OS === 'ios' ? scaleSize(10) : scaleSize(8), fontSize: scaleFont(16), color: '#1f2937', minHeight: scaleSize(44) },
    multilineInput: { minHeight: scaleSize(80), textAlignVertical: 'top', paddingVertical: scaleSize(10) },
    emptyField: { fontSize: scaleFont(14), color: '#6b7280', fontStyle: 'italic', marginLeft: scaleSize(5), paddingVertical: Platform.OS === 'ios' ? scaleSize(4) : scaleSize(8) },
    // List Styles
    listItemContainer: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: scaleSize(6), marginLeft: scaleSize(5), borderBottomWidth: 1, borderBottomColor: '#f1f5f9' },
    listItemText: { fontSize: scaleFont(15), color: '#1f2937', flex: 1, paddingRight: scaleSize(5) }, // Added scaleSize
    removeButton: { padding: scaleSize(5), marginLeft: scaleSize(10) },
    listInputContainer: { flexDirection: 'row', alignItems: 'center', marginTop: scaleSize(10), marginBottom: scaleSize(10) },
    listInput: { flex: 1, backgroundColor: '#f8fafc', borderWidth: 1, borderColor: '#d1d5db', borderRadius: scaleSize(8), paddingHorizontal: scaleSize(10), paddingVertical: scaleSize(8), fontSize: scaleFont(15), color: '#1f2937', marginRight: scaleSize(10) },
    addButton: { padding: scaleSize(5) },
    // Switch Styles
    switchContainer: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: scaleSize(8), marginBottom: scaleSize(8) },
    switchLabel: { fontSize: scaleFont(16), color: '#1f2937', flex: 1, marginRight: scaleSize(10) },
    // Picker Styles
    pickerWrapper: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: scaleSize(8), backgroundColor: '#f8fafc', justifyContent: 'center', minHeight: scaleSize(44), marginBottom: scaleSize(5) }, // Added scaleSize
    picker: { color: '#1f2937', width: '100%' },
    pickerItem: { fontSize: scaleFont(16), color: '#1f2937' },
    // Date Picker Display
    dateDisplay: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: scaleSize(12), paddingVertical: Platform.OS === 'ios' ? scaleSize(12) : scaleSize(10), borderWidth: 1, borderColor: '#d1d5db', borderRadius: scaleSize(8), backgroundColor: '#f8fafc', minHeight: scaleSize(44) },
    // Save Button
    saveButtonContainer: { marginTop: scaleSize(25), marginBottom: scaleSize(20) },
});

export default ProfileScreen;

// ----- END OF COMPLETE ProfileScreen.js FILE (with debugging logs) -----