import React from 'react';
import { View, Text, Button } from 'react-native';
import { supabase } from './supabaseClient';

const MainApp = ({ setUserId }) => {
  const handleLogout = async () => {
    await supabase.auth.signOut();
    setUserId(null);
  };

  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
      <Text>Welcome to the Main App!</Text>
      <Button title="Logout" onPress={handleLogout} />
    </View>
  );
};

export default MainApp;
